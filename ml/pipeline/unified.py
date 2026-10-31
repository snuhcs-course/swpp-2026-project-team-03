#!/usr/bin/env python3
"""Run one ROCKY song through separation, transcription, alignment and arrangement.

The script runs in the common model Python environment. Guitar and bass TAB
use their isolated Python 3.10 environment via subprocess. Every completed
stage has a checked output and is recorded in manifest.json for --resume.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Callable

import pretty_midi


STEMS = ("vocals", "drums", "bass", "guitar", "piano", "other")
TRANSCRIBE_STEMS = ("drums", "bass", "guitar", "piano")
HINTS = {
    "drums": "drums",
    "bass": "acoustic_bass,electric_bass",
    "guitar": "acoustic_guitar,clean_electric_guitar,distorted_electric_guitar",
    "piano": "acoustic_piano,electric_piano,organ",
}
TARGETS = ("piano", "guitar", "bass", "drums")


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def family(inst: pretty_midi.Instrument) -> str | None:
    if inst.is_drum:
        return "drums"
    if 0 <= inst.program <= 7:
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


def merge_stem_midis(paths: dict[str, Path], output: Path) -> pretty_midi.PrettyMIDI:
    """Keep every nonempty instrument transcription; vocal stem is excluded."""
    merged = pretty_midi.PrettyMIDI(initial_tempo=120, resolution=480)
    for stem in TRANSCRIBE_STEMS:
        midi = pretty_midi.PrettyMIDI(str(paths[stem]))
        for inst in midi.instruments:
            if inst.notes:
                track = copy.deepcopy(inst)
                track.name = f"{stem}: {inst.name or pretty_midi.program_to_instrument_name(inst.program)}"
                merged.instruments.append(track)
    if not merged.instruments:
        raise ValueError("All four instrument MuScriptor outputs are empty")
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
                        duration: float, output: Path) -> dict:
    """Keep only the requested generated part within the input song's length."""
    original = pretty_midi.PrettyMIDI(str(source))
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
            "clipped_at_end": clipped, "duration_sec": round(duration, 3)}


def combine_for_tab(aligned: pretty_midi.PrettyMIDI, parts: list[Path], output: Path) -> None:
    combined = copy.deepcopy(aligned)
    for path in parts:
        combined.instruments.extend(copy.deepcopy(pretty_midi.PrettyMIDI(str(path)).instruments))
    combined.write(str(output))


def assemble(aligned_path: Path, guitar_dir: Path, bass_dir: Path,
             generated: dict[str, Path], output: Path, guitar_code: Path) -> pretty_midi.PrettyMIDI:
    """Replace raw string tracks and add only generated tracks, not GPT band copies."""
    aligned = pretty_midi.PrettyMIDI(str(aligned_path))
    sys.path.insert(0, str(guitar_code))
    from full_score import build, guitar_tracks  # imported in the common env

    guitars = guitar_tracks(guitar_dir) if any((guitar_dir / n).is_file()
                                           for n in ("guitar.mid", "skyline_lead_rhythm.mid")) else []
    bass_file = bass_dir / "bass.mid"
    basses = pretty_midi.PrettyMIDI(str(bass_file)).instruments if bass_file.is_file() else []
    result = build(aligned, guitars, basses)
    for target in ("guitar", "bass"):
        if target in generated:
            for inst in result.instruments:
                if family(inst) == target:
                    inst.name = f"AI generated {target}: {inst.name}"
    additions = []
    for target, path in generated.items():
        if target in {"guitar", "bass"}:
            continue  # the processed TAB MIDI replaced this generated part
        for inst in pretty_midi.PrettyMIDI(str(path)).instruments:
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
    output.parent.mkdir(parents=True, exist_ok=True)
    result.write(str(output))
    return result


class Runner:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.audio = args.audio.resolve(strict=True)
        self.out = args.output_dir.resolve()
        self.pipeline = Path(__file__).resolve().parent
        self.modules = args.modules_root.resolve()
        # Do not resolve venv/bin/python symlinks: their location is how Python
        # discovers the virtual environment and its installed packages.
        self.model_python = args.model_python.absolute()
        self.tab_python = args.tab_python.absolute()
        self.config = {
            "pipeline_contract": 5,
            "audio": str(self.audio), "audio_sha256": digest(self.audio),
            "requested": args.requested, "model": args.model,
            "midigpt_model": args.midigpt_model, "device": args.device,
            "beat_checkpoint": args.beat_checkpoint, "seed": args.seed,
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
        try:
            action()
            if not ready():
                raise RuntimeError(f"{name}: outputs are missing, empty, or invalid: {outputs}")
        except Exception as exc:
            self.manifest["status"] = "failed"
            self.manifest["error"] = f"{type(exc).__name__}: {exc}"
            atomic_json(self.manifest_path, self.manifest)
            raise
        if name not in self.manifest["completed"]:
            self.manifest["completed"].append(name)
        self.manifest["status"] = "running"
        self.manifest.pop("error", None)
        atomic_json(self.manifest_path, self.manifest)

    def run(self) -> Path:
        stems_dir = self.out / "stems"
        stem_files = [stems_dir / f"{s}.wav" for s in STEMS]
        no_vocals = stems_dir / "no_vocals.wav"
        stems_dir.mkdir(exist_ok=True)
        self.stage("demucs", stem_files + [no_vocals], lambda: self.command(
            "demucs", [str(self.model_python), str(self.pipeline / "separate_stems.py"),
                       str(self.audio), str(stems_dir), "--model", "htdemucs_6s", "--no-vocals-mix"]))

        midi_dir = self.out / "stem_midi"
        midi_dir.mkdir(exist_ok=True)
        stem_midis = {s: midi_dir / f"{s}.mid" for s in TRANSCRIBE_STEMS}
        for stem in TRANSCRIBE_STEMS:
            def transcribe(stem=stem):
                cmd = [str(self.model_python), str(self.pipeline / "transcribe_with_progress.py"),
                       str(stems_dir / f"{stem}.wav"), str(stem_midis[stem]),
                       "--model", self.args.model, "--device", self.args.device,
                       "--progress", str(midi_dir / f"{stem}.progress.jsonl")]
                if stem in HINTS:
                    cmd += ["--instruments", HINTS[stem]]
                self.command(f"muscriptor_{stem}", cmd)
            self.stage(f"muscriptor_{stem}", [stem_midis[stem]], transcribe)

        raw = self.out / "stems_merged.mid"
        self.stage("merge_stems", [raw], lambda: merge_stem_midis(stem_midis, raw))

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
        missing = [part for part in self.args.requested if part not in presence]
        self.manifest["original_parts"] = sorted(presence)
        self.manifest["generated_targets"] = missing
        atomic_json(self.manifest_path, self.manifest)

        guitar_code = self.modules / "guitar_tab"
        guitar_dir = self.out / "guitar"
        bass_dir = self.out / "bass"
        if "guitar" in presence:
            def guitar():
                guitar_dir.mkdir(exist_ok=True)
                self.command("guitar_tab", [str(self.tab_python), str(guitar_code / "skyline_tab.py"),
                                            str(aligned), str(guitar_dir), "--no-merged"])
                atomic_json(self.out / "guitar_done.json", {"done": True})
            self.stage("guitar_tab", [self.out / "guitar_done.json"], guitar,
                       validate=lambda: tab_ready(guitar_dir, ("guitar.mid", "skyline_lead_rhythm.mid")))
        if "bass" in presence:
            def bass():
                bass_dir.mkdir(exist_ok=True)
                self.command("bass_tab", [str(self.tab_python), str(guitar_code / "bass_tab.py"),
                                          str(aligned), str(bass_dir)])
            self.stage("bass_tab", [bass_dir / "bass.mid"], bass,
                       validate=lambda: tab_ready(bass_dir, ("bass.mid",)))

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
            atomic_json(gen_record, {"requested": self.args.requested, "missing": missing,
                                     "generated_only": {k: str(v) for k, v in raw_generated.items()}})
        self.stage("midigpt", [gen_record, *raw_generated.values()], generate)

        normalized_dir = self.out / "generated_normalized"
        generated = {part: normalized_dir / f"{part}.mid" for part in missing}
        normalization_record = self.out / "generation_normalization.json"
        def normalize():
            import soundfile as sf
            aligned_midi = pretty_midi.PrettyMIDI(str(aligned))
            duration = max(float(sf.info(str(self.audio)).duration), aligned_midi.get_end_time())
            stats = {part: normalize_generated(raw_generated[part], part, aligned_midi,
                                               duration, generated[part]) for part in missing}
            atomic_json(normalization_record, {"duration_sec": round(duration, 3), "parts": stats})
        self.stage("normalize_generated", [normalization_record, *generated.values()], normalize)

        if any(part in generated for part in ("guitar", "bass")):
            with_generated = self.out / "aligned_with_generated.mid"
            self.stage("combine_generated_strings", [with_generated], lambda: combine_for_tab(
                pretty_midi.PrettyMIDI(str(aligned)),
                [generated[p] for p in ("guitar", "bass") if p in generated], with_generated))
            if "guitar" in generated:
                def new_guitar():
                    guitar_dir.mkdir(exist_ok=True)
                    self.command("generated_guitar_tab", [str(self.tab_python), str(guitar_code / "skyline_tab.py"),
                                                          str(with_generated), str(guitar_dir), "--no-merged"])
                    atomic_json(self.out / "generated_guitar_done.json", {"done": True})
                self.stage("generated_guitar_tab", [self.out / "generated_guitar_done.json"], new_guitar,
                           validate=lambda: tab_ready(guitar_dir, ("guitar.mid", "skyline_lead_rhythm.mid")))
            if "bass" in generated:
                def new_bass():
                    bass_dir.mkdir(exist_ok=True)
                    self.command("generated_bass_tab", [str(self.tab_python), str(guitar_code / "bass_tab.py"),
                                                        str(with_generated), str(bass_dir)])
                self.stage("generated_bass_tab", [bass_dir / "bass.mid"], new_bass,
                           validate=lambda: tab_ready(bass_dir, ("bass.mid",)))

        final = self.out / "full_score.mid"
        def final_assembly():
            score = assemble(aligned, guitar_dir, bass_dir, generated, final, guitar_code)
            duration = json.loads(normalization_record.read_text(encoding="utf-8"))["duration_sec"]
            if score.get_end_time() > duration + 0.05:
                raise ValueError("Final score extends beyond the input song duration")
            self.manifest["final_tracks"] = describe_tracks(score)
        self.stage("assemble", [final], final_assembly)
        self.manifest.setdefault("score_publication", "pending")
        self.manifest["status"] = "complete"
        atomic_json(self.manifest_path, self.manifest)
        return final


def cli(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("audio", type=Path, help="one input song")
    p.add_argument("output_dir", type=Path, help="one empty directory for this song")
    p.add_argument("--requested", default="", help="comma-separated instruments selected by the user: piano,guitar,bass,drums")
    p.add_argument("--resume", action="store_true", help="resume the same audio and configuration")
    p.add_argument("--modules-root", type=Path, default=Path("/data/rocky-unified/ml"))
    p.add_argument("--model-python", type=Path, default=Path("/data/rocky-unified/.venv/bin/python"))
    p.add_argument("--tab-python", type=Path, default=Path("/data/rocky-unified/.venv-guitar-tab/bin/python"))
    p.add_argument("--model", default="/data/model/model.safetensors", help="MuScriptor weights")
    p.add_argument("--midigpt-model", default="yellow_medium")
    p.add_argument("--beat-checkpoint", default="/data/cache/torch/hub/checkpoints/beat_this-final0.ckpt")
    p.add_argument("--device", default="cuda", choices=("cpu", "cuda"))
    p.add_argument("--seed", type=int, default=0)
    args = p.parse_args(argv)
    args.requested = [s.strip() for s in args.requested.split(",") if s.strip()]
    if len(args.requested) != len(set(args.requested)) or any(s not in TARGETS for s in args.requested):
        p.error("--requested must contain distinct names from piano,guitar,bass,drums")
    final = Runner(args).run()
    print(f"complete: {final}")
    return 0


if __name__ == "__main__":
    raise SystemExit(cli())
