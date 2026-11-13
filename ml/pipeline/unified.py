#!/usr/bin/env python3
"""Run one ROCKY song through transcription, arrangement, PDF and MP3 publication.

The script runs in the common model Python environment. Guitar and bass TAB
use their isolated Python 3.10 environment via subprocess. Every completed
stage has a checked output and is recorded in manifest.json for --resume.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Callable

import pretty_midi
from rule_gates import GateConfig, InputRejected, check_input, gate_stem, guitar_stereo
from separate_bs_roformer import (CHECKPOINT_SHA256, CONFIG_SHA256, NONVOCAL_STEMS,
                                  PACKAGE_VERSION, STEMS, valid_stems)


TRANSCRIBE_STEMS = ("drums", "bass", "guitar", "piano")
HINTS = {
    "drums": "drums",
    "bass": "acoustic_bass,electric_bass",
    "guitar": "acoustic_guitar,clean_electric_guitar,distorted_electric_guitar",
    "piano": "acoustic_piano,electric_piano,organ",
}
TARGETS = ("piano", "guitar", "bass", "drums")
PIANO_STEM_PROGRAM = 0  # one acoustic-grand track for piano/electric-piano/organ labels
SAME_NOTE_WINDOW = 0.05  # cross-track copies within 50 ms represent one onset
REJECTED_EXIT = 3  # input_check refused the song; manifest.json has `rejection`


def parse_lineup(raw: str | list[str], *, original: bool) -> tuple[set[str], int, bool]:
    """Parse the app's instrument selection; guitar1/guitar2 are counts."""
    tokens = [s.strip().lower() for s in (raw.split(",") if isinstance(raw, str) else raw) if s.strip()]
    if original and tokens in (["unknown"], ["모름"]):
        return set(), 0, True
    aliases = {"keyboard": "piano", "piano": "piano", "bass": "bass",
               "drums": "drums", "guitar": "guitar1", "guitar1": "guitar1",
               "guitar2": "guitar2"}
    if any(token not in aliases for token in tokens) or len(tokens) != len(set(tokens)):
        raise ValueError("Select keyboard,bass,guitar1 or guitar2,drums; original may be unknown")
    selected = {aliases[token] for token in tokens}
    if len(selected) != len(tokens) or {"guitar1", "guitar2"} <= selected:
        raise ValueError("Select exactly one guitar count: guitar1 or guitar2")
    guitars = 2 if "guitar2" in selected else 1 if "guitar1" in selected else 0
    parts = {"guitar" if token.startswith("guitar") else token for token in selected}
    return parts, guitars, False


def guitar_case(original_guitars: int, requested_guitars: int) -> tuple[str | None, bool]:
    """Return skyline split mode and whether one new guitar must be generated."""
    if original_guitars == 0 and requested_guitars == 2:
        raise ValueError("Generating two guitars from zero original guitars is not supported")
    if requested_guitars == 0 or original_guitars == 0:
        return None, requested_guitars > original_guitars
    split = "always" if original_guitars == requested_guitars == 2 else "never"
    return split, requested_guitars > original_guitars


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def atomic_json(path: Path, value: dict | list) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def valid_midi(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        pretty_midi.PrettyMIDI(str(path))
    except (OSError, ValueError, EOFError):
        return False
    return True


def family(inst: pretty_midi.Instrument) -> str | None:
    if inst.is_drum:
        return "drums"
    if 0 <= inst.program <= 7 or 16 <= inst.program <= 23:
        return "piano"
    if 24 <= inst.program <= 31:
        return "guitar"
    if 32 <= inst.program <= 39:
        return "bass"
    return None


def present_parts(midi: pretty_midi.PrettyMIDI) -> set[str]:
    return {part for inst in midi.instruments
            if inst.notes
            if (part := family(inst)) is not None}


def tab_ready(directory: Path, midi_names: tuple[str, ...]) -> bool:
    return (any((directory / name).is_file() and (directory / name).stat().st_size > 0
                for name in midi_names)
            and any(p.is_file() and p.stat().st_size > 0 for p in directory.glob("*.gp5")))


def merge_tracks(tracks: list[pretty_midi.Instrument], program: int, name: str) -> pretty_midi.Instrument:
    """Join piano-label tracks, deduplicating near-identical cross-track notes.

    A later end and stronger velocity win for duplicate onsets. Separate
    same-pitch onsets truncate the preceding note to avoid overlapping note
    pairs in the resulting MIDI.
    """
    events = sorted(((index, copy.copy(note)) for index, track in enumerate(tracks)
                     for note in track.notes),
                    key=lambda item: (item[1].pitch, item[1].start, -item[1].end))
    notes: list[pretty_midi.Note] = []
    sources: list[set[int]] = []
    for source, note in events:
        previous = notes[-1] if notes and notes[-1].pitch == note.pitch else None
        if (previous is not None and note.start - previous.start < SAME_NOTE_WINDOW
                and (source not in sources[-1] or note.start == previous.start)):
            previous.end = max(previous.end, note.end)
            previous.velocity = max(previous.velocity, note.velocity)
            sources[-1].add(source)
            continue
        if previous is not None and previous.end > note.start:
            previous.end = note.start
        notes.append(note)
        sources.append({source})
    merged = pretty_midi.Instrument(program=program, name=name)
    merged.notes = sorted(notes, key=lambda note: (note.start, note.pitch))
    return merged


def merge_stem_midis(paths: dict[str, Path], output: Path,
                     selected: tuple[str, ...] = TRANSCRIBE_STEMS) -> pretty_midi.PrettyMIDI:
    """Keep selected original instruments and combine piano-stem keyboard labels."""
    merged = pretty_midi.PrettyMIDI(initial_tempo=120, resolution=480)
    for stem in selected:
        midi = pretty_midi.PrettyMIDI(str(paths[stem]))
        tracks = [inst for inst in midi.instruments if inst.notes and family(inst) == stem]
        if stem == "piano" and tracks:
            merged.instruments.append(merge_tracks(tracks, PIANO_STEM_PROGRAM, "piano: piano"))
            continue
        for inst in tracks:
            track = copy.deepcopy(inst)
            track.name = f"{stem}: {inst.name or pretty_midi.program_to_instrument_name(inst.program)}"
            merged.instruments.append(track)
    if not merged.instruments:
        raise ValueError("Selected original instrument MuScriptor outputs are empty")
    merged.write(str(output))
    return merged


def generated_only(output_dir: Path, aligned: Path, target: str) -> Path:
    return output_dir / f"{aligned.stem}__+{target}_only.mid"


def describe_tracks(score: pretty_midi.PrettyMIDI) -> list[dict]:
    """Return JSON-safe track metadata (model outputs may use NumPy scalars)."""
    return [dict(name=str(i.name), program=int(i.program),
                 is_drum=bool(i.is_drum), notes=int(len(i.notes)))
            for i in score.instruments]


def normalize_generated(source: Path, target: str, aligned: pretty_midi.PrettyMIDI,
                        duration: float, output: Path, snap: Callable | None = None) -> dict:
    """Keep only the requested generated part within the input song's length.

    snap: beat_align.align.snap_to_reference. When given, the generated notes are first put on the
    aligned MIDI's 16th grid (MIDI-GPT output skips beat alignment)."""
    original = pretty_midi.PrettyMIDI(str(source))
    snap_stats = None
    if snap is not None:
        original, snap_stats = snap(original, aligned)
    result = pretty_midi.PrettyMIDI(initial_tempo=float(aligned.get_tempo_changes()[1][0]),
                                   resolution=aligned.resolution)
    result.time_signature_changes = copy.deepcopy(aligned.time_signature_changes)
    result.key_signature_changes = copy.deepcopy(aligned.key_signature_changes)
    kept = dropped = clipped = 0
    for inst in original.instruments:
        if family(inst) != target:
            raise ValueError(f"Unexpected track in generated {target} MIDI: {source}")
        new = copy.deepcopy(inst)
        new.notes = []
        for note in inst.notes:
            if note.start >= duration:
                dropped += 1
                continue
            n = copy.deepcopy(note)
            if n.end > duration:
                n.end = duration
                clipped += 1
            if n.end <= n.start:
                dropped += 1
                continue
            new.notes.append(n)
            kept += 1
        if new.notes:
            result.instruments.append(new)
    if not kept:
        raise ValueError(f"Generated {target} has no notes inside the song duration")
    output.parent.mkdir(parents=True, exist_ok=True)
    result.write(str(output))
    return {"raw_notes": sum(len(i.notes) for i in original.instruments),
            "kept_notes": kept, "dropped_after_end": dropped,
            "clipped_at_end": clipped, "duration_sec": round(duration, 3),
            **({"snap": snap_stats} if snap_stats is not None else {})}


def combine_for_tab(aligned: pretty_midi.PrettyMIDI, parts: list[Path], output: Path) -> None:
    combined = copy.deepcopy(aligned)
    for path in parts:
        combined.instruments.extend(copy.deepcopy(pretty_midi.PrettyMIDI(str(path)).instruments))
    combined.write(str(output))


def assemble(aligned_path: Path, guitar_dir: Path, bass_dir: Path,
             generated: dict[str, Path], output: Path, guitar_code: Path,
             requested: set[str] | None = None,
             generated_guitar_dir: Path | None = None) -> pretty_midi.PrettyMIDI:
    """Replace raw string tracks and add only generated tracks, not GPT band copies."""
    aligned = pretty_midi.PrettyMIDI(str(aligned_path))
    sys.path.insert(0, str(guitar_code))
    from full_score import build, guitar_tracks  # imported in the common env

    guitars = guitar_tracks(guitar_dir) if any((guitar_dir / n).is_file()
                                           for n in ("guitar.mid", "skyline_lead_rhythm.mid")) else []
    if generated_guitar_dir is not None:
        extra = guitar_tracks(generated_guitar_dir)
        for inst in extra:
            inst.name = f"Guitar {len(guitars) + 1} (AI generated)"
            guitars.append(inst)
    bass_file = bass_dir / "bass.mid"
    basses = pretty_midi.PrettyMIDI(str(bass_file)).instruments if bass_file.is_file() else []
    result = build(aligned, guitars, basses)
    for target in ("guitar", "bass"):
        if target in generated and not (target == "guitar" and generated_guitar_dir is not None):
            for inst in result.instruments:
                if family(inst) == target:
                    inst.name = f"AI generated {target}: {inst.name}"
    additions = []
    for target, path in generated.items():
        if target in {"guitar", "bass"}:
            continue  # the processed TAB MIDI replaced this generated part
        part_midi = pretty_midi.PrettyMIDI(str(path))
        if target == "piano":
            # generated keyboard skips build(): give it the same two-hand limits as a transcribed one
            import piano_playable  # ml/guitar_tab, next to full_score
            part_midi, _ = piano_playable.process(part_midi)
        for inst in part_midi.instruments:
            if inst.notes:
                if family(inst) != target:
                    raise ValueError(f"Generated {target} track has unexpected GM program: {path}")
                new = copy.deepcopy(inst)
                new.name = f"AI generated {target}: {inst.name}"
                additions.append(new)
    result.instruments = ([i for i in result.instruments if not i.is_drum]
                          + [i for i in additions if not i.is_drum]
                          + [i for i in result.instruments if i.is_drum]
                          + [i for i in additions if i.is_drum])
    if requested is not None:
        result.instruments = [i for i in result.instruments if family(i) in requested and i.notes]
        missing = requested - present_parts(result)
        if missing:
            raise ValueError(f"Requested instruments missing from final score: {sorted(missing)}")
    output.parent.mkdir(parents=True, exist_ok=True)
    result.write(str(output))
    return result


class Runner:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.original_parts, self.original_guitars, self.original_unknown = parse_lineup(
            getattr(args, "original", "unknown"), original=True)
        self.requested_parts, self.requested_guitars, _ = parse_lineup(args.requested, original=False)
        if not self.original_unknown and not self.original_parts:
            raise ValueError("Known original needs at least one band instrument for Beat This! and MIDI-GPT")
        if not self.original_unknown:
            guitar_case(self.original_guitars, self.requested_guitars)
        # Solo practice (--personal): one requested instrument and an unknown
        # original. A bass, keyboard or drums solo transcribes its stem (and drums)
        # first; see probe_requested. Guitar solos and band runs transcribe every
        # stem as before, so the app's guitar-count redo gets the whole band.
        self.personal = bool(getattr(args, "personal", False))
        if self.personal and (not self.original_unknown or len(self.requested_parts) != 1):
            raise ValueError("--personal takes an unknown original and exactly one requested instrument")
        self.audio = args.audio.resolve(strict=True)
        self.out = args.output_dir.resolve()
        self.pipeline = Path(__file__).resolve().parent
        self.modules = args.modules_root.resolve()
        # Do not resolve venv/bin/python symlinks: their location is how Python
        # discovers the virtual environment and its installed packages.
        self.model_python = args.model_python.absolute()
        self.tab_python = args.tab_python.absolute()
        self.gates = GateConfig(
            min_band_ratio=getattr(args, "min_band_ratio", GateConfig.min_band_ratio),
            note_floor_db=getattr(args, "note_floor_db", GateConfig.note_floor_db),
            min_notes_per_minute=getattr(args, "min_notes_per_minute", GateConfig.min_notes_per_minute))
        self.config = {
            "pipeline_contract": 14,
            "audio": str(self.audio), "audio_sha256": digest(self.audio),
            "original": "unknown" if self.original_unknown else sorted(self.original_parts),
            "original_guitars": self.original_guitars,
            "requested": sorted(self.requested_parts), "requested_guitars": self.requested_guitars,
            "personal": self.personal,
            "model": args.model,
            "transcription_workers": getattr(args, "transcription_workers", 2),
            "midigpt_model": args.midigpt_model, "device": args.device,
            "beat_checkpoint": args.beat_checkpoint, "seed": args.seed,
            "separator": PACKAGE_VERSION + "/BS-RoFormer-SW-6stem",
            "separator_checkpoint_sha256": CHECKPOINT_SHA256,
            "separator_config_sha256": CONFIG_SHA256,
            "separator_models_dir": str(args.bsroformer_models_dir.absolute()),
            "beat_mix_stems": list(NONVOCAL_STEMS),
            "rule_gates": self.gates.as_dict(),
        }
        self.manifest_path = self.out / "manifest.json"
        if self.manifest_path.exists():
            if not args.resume:
                raise FileExistsError(f"{self.manifest_path} exists; pass --resume for the same input/config")
            self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
            if self.manifest.get("config") != self.config:
                raise ValueError("Existing manifest input or configuration differs; use a new output directory")
        else:
            if self.out.exists() and any(self.out.iterdir()):
                raise FileExistsError(f"{self.out} is not empty")
            self.out.mkdir(parents=True, exist_ok=True)
            self.manifest = {"config": self.config, "completed": [], "status": "running"}
            atomic_json(self.manifest_path, self.manifest)
        (self.out / "logs").mkdir(exist_ok=True)

    def command(self, stage: str, cmd: list[str], env: dict | None = None) -> None:
        log_path = self.out / "logs" / f"{stage}.log"
        with log_path.open("a", encoding="utf-8") as log:
            log.write("$ " + " ".join(cmd) + "\n")
            log.flush()
            completed = subprocess.run(cmd, env=env, stdout=log, stderr=subprocess.STDOUT, check=False)
        if completed.returncode:
            raise RuntimeError(f"{stage} exited {completed.returncode}; see {log_path}")

    def stage(self, name: str, outputs: list[Path], action: Callable[[], None],
              validate: Callable[[], bool] | None = None) -> None:
        def ready() -> bool:
            return (all(p.is_file() and p.stat().st_size > 0 for p in outputs)
                    and (validate is None or validate()))

        if self.args.resume and name in self.manifest["completed"] and ready():
            print(f"skip {name}: validated saved output", flush=True)
            return
        print(f"run {name}", flush=True)
        started = time.perf_counter()
        try:
            action()
            if not ready():
                raise RuntimeError(f"{name}: outputs are missing, empty, or invalid: {outputs}")
        except Exception as exc:
            self.manifest.setdefault("stage_seconds", {})[name] = round(time.perf_counter() - started, 2)
            if isinstance(exc, InputRejected):
                # Not a pipeline failure: the input is refused. The server reads
                # `rejection.code` and tells the user; a retry gives the same answer.
                self.manifest["status"] = "rejected"
                self.manifest["rejection"] = exc.as_dict()
            else:
                self.manifest["status"] = "failed"
            self.manifest["error"] = f"{type(exc).__name__}: {exc}"
            atomic_json(self.manifest_path, self.manifest)
            raise
        if name not in self.manifest["completed"]:
            self.manifest["completed"].append(name)
        self.manifest.setdefault("stage_seconds", {})[name] = round(time.perf_counter() - started, 2)
        self.manifest["status"] = "running"
        self.manifest.pop("error", None)
        self.manifest.pop("rejection", None)
        atomic_json(self.manifest_path, self.manifest)

    def publish_outputs(self) -> None:
        from publish_scores import publication_ready, publish

        def action() -> None:
            publish(self.out, self.args.musescore, self.args.node,
                    self.args.gp5_converter, self.args.pdfinfo, force=False,
                    render_workers=getattr(self.args, "render_workers", 1))

        self.stage("publish_outputs", [self.out / "scores" / "score_outputs.json"],
                   action, validate=lambda: publication_ready(self.out))
        self.manifest["score_outputs"] = "scores/score_outputs.json"
        self.manifest["score_publication"] = "complete"
        self.manifest["status"] = "complete"
        atomic_json(self.manifest_path, self.manifest)

    def stereo_check(self, stems_dir: Path) -> dict:
        """Two guitars panned apart? Run once; the probe and the guitar TAB both use it."""
        stereo_file = self.out / "guitar_stereo.json"
        if not ("guitar_stereo" in self.manifest["completed"] and stereo_file.is_file()):
            self.stage("guitar_stereo", [stereo_file], lambda: atomic_json(
                stereo_file, guitar_stereo(stems_dir / "guitar.wav", self.gates)))
        return json.loads(stereo_file.read_text(encoding="utf-8"))

    def probe_requested(self, stems_dir: Path, midi_dir: Path, no_vocals: Path,
                        transcribe_set: Callable[[tuple[str, ...], Path], None]
                        ) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Bass, keyboard or drums solo: transcribe that stem (and drums) first and gate it.

        Drums are always transcribed because drum sync aligns the score to them.
        A stem with notes left after the note gate (the sparse-stem rule of an
        unknown original) is in the song. Then nothing is generated, so only
        these stems are transcribed. Otherwise the other stems are transcribed
        too: MIDI-GPT always gets the whole band as context.
        Guitar solos never come here: the app's guitar-count redo builds a known
        original from the instruments the first run found, so that run must
        transcribe every stem.
        Returns (stems to transcribe, stems the probe already transcribed).
        """
        requested = tuple(s for s in TRANSCRIBE_STEMS if s in self.requested_parts)
        wanted = tuple(s for s in TRANSCRIBE_STEMS if s in self.requested_parts or s == "drums")
        probe_file = self.out / "focus_probe.json"
        # The server shows transcription progress for these stems.
        self.manifest["transcribe_stems"] = list(wanted)
        atomic_json(self.manifest_path, self.manifest)

        def probe():
            import soundfile as sf
            transcribe_set(wanted, midi_dir / "probe_jobs.json")
            duration = float(sf.info(str(no_vocals)).duration)
            found = {}
            for stem in requested:
                report = gate_stem(midi_dir / f"{stem}.mid", stems_dir / f"{stem}.wav", stem,
                                   self.out / "focus_probe" / f"{stem}.mid", self.gates, family,
                                   declared=False, original_unknown=True, duration_sec=duration)
                found[stem] = {"in_song": report["notes_final"] > 0, "gate": report}
            atomic_json(probe_file, {"stems": found})
        self.stage("focus_probe", [probe_file, *(midi_dir / f"{s}.mid" for s in wanted)], probe,
                   validate=lambda: all(valid_midi(midi_dir / f"{s}.mid") for s in wanted))
        found = json.loads(probe_file.read_text(encoding="utf-8"))["stems"]
        in_song = {stem: bool(found[stem]["in_song"]) for stem in requested}
        stems = wanted if all(in_song.values()) else TRANSCRIBE_STEMS
        self.manifest["probe"] = {"in_song": in_song, "all_found": all(in_song.values())}
        self.manifest["transcribe_stems"] = list(stems)
        atomic_json(self.manifest_path, self.manifest)
        return stems, wanted

    def run(self) -> Path:
        stems_dir = self.out / "stems"
        stem_files = [stems_dir / f"{s}.wav" for s in STEMS]
        no_vocals = stems_dir / "no_vocals.wav"
        transcribe_stems = tuple(s for s in TRANSCRIBE_STEMS
                                 if self.original_unknown or s in self.original_parts)
        stems_dir.mkdir(exist_ok=True)
        self.stage("bs_roformer", stem_files + [no_vocals], lambda: self.command(
            "bs_roformer", [str(self.model_python), str(self.pipeline / "separate_bs_roformer.py"),
                            str(self.audio), str(stems_dir),
                            "--models-dir", str(self.args.bsroformer_models_dir),
                            "--lib-dir", str(self.args.bsroformer_lib_dir)]),
                   validate=lambda: valid_stems(stems_dir))

        # Rule 1: refuse audio that is not a band song before any GPU-heavy stage.
        input_report = self.out / "input_check.json"
        def input_check():
            report = {}
            try:
                report = check_input(stems_dir, self.gates)
            except InputRejected as exc:
                report = {"rejected": exc.code, **exc.detail}
                raise
            finally:
                atomic_json(input_report, report)
        self.stage("input_check", [input_report], input_check)

        midi_dir = self.out / "stem_midi"
        midi_dir.mkdir(exist_ok=True)
        base = [str(self.model_python), str(self.pipeline / "transcribe_with_progress.py")]

        def stem_command(stem: str) -> list[str]:
            return base + [str(stems_dir / f"{stem}.wav"), str(midi_dir / f"{stem}.mid"),
                           "--model", self.args.model, "--device", self.args.device,
                           "--instruments", HINTS[stem], "--progress",
                           str(midi_dir / f"{stem}.progress.jsonl"), "--resume-existing"]

        def transcribe_set(todo: tuple[str, ...], jobs_file: Path) -> None:
            atomic_json(jobs_file, [{"stem": stem, "audio": str(stems_dir / f"{stem}.wav"),
                                     "output": str(midi_dir / f"{stem}.mid"),
                                     "instruments": HINTS.get(stem),
                                     "progress": str(midi_dir / f"{stem}.progress.jsonl")}
                                    for stem in todo])
            if not todo:
                return
            if getattr(self.args, "transcription_workers", 2) == 1:
                self.command("muscriptor_batch", base + [
                    "--jobs-file", str(jobs_file), "--model", self.args.model,
                    "--device", self.args.device, "--resume-existing",
                ])
            else:
                with ThreadPoolExecutor(max_workers=self.args.transcription_workers) as pool:
                    futures = []
                    # Longest stems first reduces tail idle time with two workers.
                    for stem in (s for s in ("guitar", "bass", "piano", "drums") if s in todo):
                        futures.append(pool.submit(self.command, f"muscriptor_{stem}", stem_command(stem)))
                    for future in futures:
                        future.result()

        probed: tuple[str, ...] = ()
        if self.personal and not self.requested_guitars:
            transcribe_stems, probed = self.probe_requested(stems_dir, midi_dir, no_vocals, transcribe_set)
        stem_midis = {s: midi_dir / f"{s}.mid" for s in transcribe_stems}
        todo = tuple(s for s in transcribe_stems if s not in probed)
        jobs_file = midi_dir / "transcription_jobs.json"
        def transcribe():
            transcribe_set(todo, jobs_file)
        if transcribe_stems:
            self.stage("muscriptor_batch", list(stem_midis.values()), transcribe,
                       validate=lambda: all(valid_midi(path) for path in stem_midis.values()))

        # Rule 2: drop notes MuScriptor wrote from the residue of a resting stem,
        # and (original unknown only) treat a stem with very few notes as absent.
        gated_dir = self.out / "stem_midi_gated"
        gated_midis = {s: gated_dir / f"{s}.mid" for s in transcribe_stems}
        gate_report = self.out / "note_gate.json"
        def note_gate():
            import soundfile as sf
            duration = float(sf.info(str(no_vocals)).duration)
            reports = {stem: gate_stem(stem_midis[stem], stems_dir / f"{stem}.wav", stem,
                                       gated_midis[stem], self.gates, family,
                                       declared=not self.original_unknown,
                                       original_unknown=self.original_unknown,
                                       duration_sec=duration)
                       for stem in transcribe_stems}
            atomic_json(gate_report, {"duration_sec": round(duration, 2), "stems": reports})
            if self.original_unknown and not any(r["notes_final"] for r in reports.values()):
                raise InputRejected("not_band_audio",
                                    "No band instrument has enough notes after the note gate.",
                                    {"note_gate": "note_gate.json"})
        if transcribe_stems:
            self.stage("note_gate", [gate_report, *gated_midis.values()], note_gate,
                       validate=lambda: all(valid_midi(path) for path in gated_midis.values()))
            # Declared and requested parts whose stem barely sounds (app shows a warning).
            gate_stems = json.loads(gate_report.read_text(encoding="utf-8"))["stems"]
            self.manifest["faint_parts"] = sorted(
                stem for stem, report in gate_stems.items()
                if report.get("faint") and stem in self.requested_parts)
            atomic_json(self.manifest_path, self.manifest)

        raw = self.out / "stems_merged.mid"
        self.stage("merge_stems", [raw], lambda: merge_stem_midis(gated_midis, raw, transcribe_stems))

        beats_file = self.out / "beats.json"
        def beat_this():
            sys.path.insert(0, str(self.modules / "beat_align"))
            from align import detect_beats, save_beats
            beats, downbeats = detect_beats(no_vocals, device=self.args.device,
                                            checkpoint=self.args.beat_checkpoint)
            if len(beats) < 2:
                raise ValueError("Beat This returned fewer than two beats")
            save_beats(beats_file, beats, downbeats)
        self.stage("beat_this", [beats_file], beat_this)

        aligned = self.out / "aligned.mid"
        def align():
            sys.path.insert(0, str(self.modules / "beat_align"))
            from align import align_midi, load_beats
            beats, downbeats = load_beats(beats_file)
            result = align_midi(raw, aligned, beats=beats, downbeats=downbeats, drum_sync=True)
            self.manifest["alignment"] = {"bpm": result.bpm, "meter": result.meter,
                                           "notes": result.note_count,
                                           "drum_sync_moved": result.drum_sync.moved_notes if result.drum_sync else 0}
        self.stage("align", [aligned], align)

        presence = present_parts(pretty_midi.PrettyMIDI(str(aligned)))
        if not self.original_unknown:
            lost = (self.original_parts & self.requested_parts) - presence
            if lost:
                raise ValueError(f"Declared original instruments produced no notes: {sorted(lost)}")
        self.manifest["transcribed_parts"] = sorted(presence)
        self.manifest["beat_mix_stems"] = list(NONVOCAL_STEMS)
        atomic_json(self.manifest_path, self.manifest)

        guitar_code = self.modules / "guitar_tab"
        guitar_dir = self.out / "guitar"
        bass_dir = self.out / "bass"
        source_guitars = self.original_guitars if not self.original_unknown else 0
        if "guitar" in presence and self.requested_guitars:
            split = "auto" if self.original_unknown else guitar_case(
                self.original_guitars, self.requested_guitars)[0]
            if self.original_unknown:
                # Two guitars panned apart can play the same register and chords
                # (21 Guns), which the chord rule in skyline_tab cannot see.
                stereo = self.stereo_check(stems_dir)
                self.manifest["guitar_stereo"] = stereo
                if stereo.get("two_guitars"):
                    split = "always"
            def guitar():
                guitar_dir.mkdir(exist_ok=True)
                command = [str(self.tab_python), str(guitar_code / "skyline_tab.py"),
                           str(aligned), str(guitar_dir), "--no-merged"]
                if split != "auto":
                    command += ["--split", split]
                self.command("guitar_tab", command)
                atomic_json(self.out / "guitar_done.json", {"done": True})
            self.stage("guitar_tab", [self.out / "guitar_done.json"], guitar,
                       validate=lambda: tab_ready(guitar_dir, ("guitar.mid", "skyline_lead_rhythm.mid")))
            if self.original_unknown:
                source_guitars = 2 if (guitar_dir / "skyline_lead_rhythm.mid").is_file() else 1
                if source_guitars == 2 and self.requested_guitars == 1:
                    guitar_dir = self.out / "guitar_compressed"
                    def compress_guitar():
                        guitar_dir.mkdir(exist_ok=True)
                        self.command("guitar_compressed", [str(self.tab_python),
                                     str(guitar_code / "skyline_tab.py"), str(aligned), str(guitar_dir),
                                     "--no-merged", "--split", "never"])
                    self.stage("guitar_compressed", [guitar_dir / "guitar.mid"], compress_guitar,
                               validate=lambda: tab_ready(guitar_dir, ("guitar.mid",)))
        _, generate_guitar = guitar_case(source_guitars, self.requested_guitars)
        self.manifest["original_parts"] = sorted(presence if self.original_unknown else self.original_parts)
        self.manifest["original_guitars_inferred"] = (
            None if self.original_unknown and not self.requested_guitars else source_guitars)
        self.manifest["guitar_score_dir"] = guitar_dir.relative_to(self.out).as_posix()

        if "bass" in presence and "bass" in self.requested_parts:
            def bass():
                bass_dir.mkdir(exist_ok=True)
                self.command("bass_tab", [str(self.tab_python), str(guitar_code / "bass_tab.py"),
                                          str(aligned), str(bass_dir)])
            self.stage("bass_tab", [bass_dir / "bass.mid"], bass,
                       validate=lambda: tab_ready(bass_dir, ("bass.mid",)))

        original_parts = presence if self.original_unknown else self.original_parts
        missing = [part for part in TARGETS if part in self.requested_parts
                   and (part not in original_parts if part != "guitar"
                        else generate_guitar)]
        self.manifest["generated_targets"] = missing
        atomic_json(self.manifest_path, self.manifest)
        gen_dir = self.out / "generated"
        raw_generated = {part: generated_only(gen_dir, aligned, part) for part in missing}
        gen_record = self.out / "generation.json"
        def generate():
            gen_dir.mkdir(exist_ok=True)
            if missing:
                env = dict(os.environ, ROCKY_MODEL=self.args.midigpt_model,
                           ROCKY_DEVICE=self.args.device, ROCKY_SEED=str(self.args.seed))
                self.command("midigpt", [str(self.model_python),
                            str(self.modules / "midigpt/generate_missing.py"), str(aligned),
                            *missing, "--out", str(gen_dir), "--work", str(self.out / "generation_work")], env)
                for target, path in raw_generated.items():
                    if not path.is_file() or path.stat().st_size == 0:
                        raise RuntimeError(f"MIDI-GPT did not produce {target}: {path}")
                    tracks = pretty_midi.PrettyMIDI(str(path)).instruments
                    if not any(i.notes and family(i) == target for i in tracks):
                        raise RuntimeError(f"MIDI-GPT {target} output has no matching notes: {path}")
            atomic_json(gen_record, {"requested": sorted(self.requested_parts),
                                     "requested_guitars": self.requested_guitars, "missing": missing,
                                     "generated_only": {k: str(v) for k, v in raw_generated.items()}})
        self.stage("midigpt", [gen_record, *raw_generated.values()], generate)

        normalized_dir = self.out / "generated_normalized"
        generated = {part: normalized_dir / f"{part}.mid" for part in missing}
        normalization_record = self.out / "generation_normalization.json"
        def normalize():
            import soundfile as sf
            sys.path.insert(0, str(self.modules / "beat_align"))
            from align import snap_to_reference
            aligned_midi = pretty_midi.PrettyMIDI(str(aligned))
            duration = max(float(sf.info(str(self.audio)).duration), aligned_midi.get_end_time())
            stats = {part: normalize_generated(raw_generated[part], part, aligned_midi,
                                               duration, generated[part], snap=snap_to_reference)
                     for part in missing}
            atomic_json(normalization_record, {"duration_sec": round(duration, 3), "parts": stats})
        self.stage("normalize_generated", [normalization_record, *generated.values()], normalize)

        if "guitar" in generated:
            generated_guitar_dir = self.out / ("guitar_generated" if source_guitars else "guitar")
            def new_guitar():
                generated_guitar_dir.mkdir(exist_ok=True)
                self.command("generated_guitar_tab", [str(self.tab_python),
                             str(guitar_code / "skyline_tab.py"), str(generated["guitar"]),
                             str(generated_guitar_dir), "--no-merged", "--split", "never"])
            self.stage("generated_guitar_tab", [generated_guitar_dir / "guitar.mid"], new_guitar,
                       validate=lambda: tab_ready(generated_guitar_dir, ("guitar.mid",)))
            if not source_guitars:
                guitar_dir = generated_guitar_dir
                self.manifest["guitar_score_dir"] = guitar_dir.relative_to(self.out).as_posix()
            else:
                self.manifest["guitar_extra_dir"] = generated_guitar_dir.relative_to(self.out).as_posix()
            atomic_json(self.manifest_path, self.manifest)
        else:
            generated_guitar_dir = None

        if "bass" in generated:
            with_generated = self.out / "aligned_with_generated.mid"
            self.stage("combine_generated_strings", [with_generated], lambda: combine_for_tab(
                pretty_midi.PrettyMIDI(str(aligned)), [generated["bass"]], with_generated))
            def new_bass():
                bass_dir.mkdir(exist_ok=True)
                self.command("generated_bass_tab", [str(self.tab_python), str(guitar_code / "bass_tab.py"),
                                                    str(with_generated), str(bass_dir)])
            self.stage("generated_bass_tab", [bass_dir / "bass.mid"], new_bass,
                       validate=lambda: tab_ready(bass_dir, ("bass.mid",)))

        final = self.out / "full_score.mid"
        def final_assembly():
            score = assemble(aligned, guitar_dir, bass_dir, generated, final, guitar_code,
                             self.requested_parts, generated_guitar_dir if source_guitars else None)
            guitar_tracks_count = sum(family(inst) == "guitar" for inst in score.instruments)
            if guitar_tracks_count != self.requested_guitars:
                raise ValueError(f"Expected {self.requested_guitars} guitar parts, got {guitar_tracks_count}")
            duration = json.loads(normalization_record.read_text(encoding="utf-8"))["duration_sec"]
            if score.get_end_time() > duration + 0.05:
                raise ValueError("Final score extends beyond the input song duration")
            self.manifest["final_tracks"] = describe_tracks(score)
        self.stage("assemble", [final], final_assembly)
        self.manifest.setdefault("score_publication", "pending")
        self.manifest["status"] = "complete"
        atomic_json(self.manifest_path, self.manifest)
        if not self.args.no_publish:
            self.publish_outputs()
        return final


def cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("audio", type=Path, help="one input song")
    p.add_argument("output_dir", type=Path, help="one empty directory for this song")
    p.add_argument("--original", default="unknown",
                   help="original lineup: unknown, or comma-separated keyboard,bass,guitar1/guitar2,drums")
    p.add_argument("--requested", required=True,
                   help="output lineup: comma-separated keyboard,bass,guitar1/guitar2,drums")
    p.add_argument("--personal", action="store_true",
                   help="solo practice: one requested instrument; transcribe only its stem when it is in the song")
    p.add_argument("--resume", action="store_true", help="resume the same audio and configuration")
    p.add_argument("--modules-root", type=Path, default=Path("/data/rocky-unified/ml"))
    p.add_argument("--model-python", type=Path, default=Path("/data/rocky-unified/.venv/bin/python"))
    p.add_argument("--tab-python", type=Path, default=Path("/data/rocky-unified/.venv-guitar-tab/bin/python"))
    p.add_argument("--model", default="/data/model/model.safetensors", help="MuScriptor weights")
    p.add_argument("--midigpt-model", default="yellow_medium")
    p.add_argument("--beat-checkpoint", default="/data/cache/torch/hub/checkpoints/beat_this-final0.ckpt")
    p.add_argument("--bsroformer-models-dir", type=Path, default=Path("/data/bsrofo/models"))
    p.add_argument("--bsroformer-lib-dir", type=Path, default=Path("/data/bsrofo/pylib"))
    p.add_argument("--device", default="cuda", choices=("cpu", "cuda"))
    p.add_argument("--transcription-workers", type=int, default=2, choices=(1, 2, 4),
                   help="MuScriptor stem processes on one GPU (default 2; use 1 on smaller GPUs)")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--musescore", default="musescore3", help="MuseScore executable for PDF and MP3 export")
    p.add_argument("--node", default="node", help="Node.js executable for guitar/bass GP5 PDF export")
    p.add_argument("--gp5-converter", type=Path,
                   default=Path("/data/rocky-unified/ml/gp5_to_pdf/convert.js"))
    p.add_argument("--pdfinfo", default="pdfinfo", help="Poppler pdfinfo executable")
    p.add_argument("--no-publish", action="store_true", help="stop after MIDI/GP5 for diagnostics")
    p.add_argument("--render-workers", type=int, default=2,
                   help="parallel PDF/MP3 exports when publishing inline (1-4; default 2)")
    p.add_argument("--min-band-ratio", type=float, default=GateConfig.min_band_ratio,
                   help="reject the song below this band-stem energy share (default 0.15)")
    p.add_argument("--note-floor-db", type=float, default=GateConfig.note_floor_db,
                   help="drop notes quieter than this, relative to the stem's playing level (default -40)")
    p.add_argument("--min-notes-per-minute", type=float, default=GateConfig.min_notes_per_minute,
                   help="original unknown: treat a stem with fewer notes as absent (default 20)")
    args = p.parse_args(argv)
    try:
        original_parts, original_guitars, original_unknown = parse_lineup(args.original, original=True)
        requested_parts, requested_guitars, _ = parse_lineup(args.requested, original=False)
        if not requested_parts:
            raise ValueError("Select at least one output instrument")
        if not original_unknown and not original_parts:
            raise ValueError("Known original needs at least one band instrument")
        if not original_unknown and original_guitars == 0 and requested_guitars == 2:
            raise ValueError("Generating two guitars from zero original guitars is not supported")
        if args.personal and (not original_unknown or len(requested_parts) != 1):
            raise ValueError("--personal takes an unknown original and exactly one requested instrument")
    except ValueError as exc:
        p.error(str(exc))
    args.gp5_converter = args.gp5_converter.resolve()
    args.bsroformer_models_dir = args.bsroformer_models_dir.resolve()
    args.bsroformer_lib_dir = args.bsroformer_lib_dir.resolve()
    if not args.no_publish:
        from publish_scores import check_dependencies, publication_ready
        if not publication_ready(args.output_dir.resolve()):
            check_dependencies(args.musescore, args.node, args.gp5_converter,
                               args.pdfinfo, require_gp5=False)
    try:
        final = Runner(args).run()
    except InputRejected as exc:
        print(f"rejected ({exc.code}): {exc.message}", file=sys.stderr)
        return REJECTED_EXIT
    print(f"complete: {final}")
    if not args.no_publish:
        print(f"deliverables: {args.output_dir.resolve() / 'scores' / 'score_outputs.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
