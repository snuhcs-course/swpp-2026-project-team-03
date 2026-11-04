#!/usr/bin/env python3
"""Publish full-band and instrument PDF scores and MP3 playback from a unified run.

This stage needs MuseScore, Node/Playwright, and the gp5-to-pdf module.
It can run without a GPU. For PDFs, guitar and bass use their completed GP5
tablatures; full-band, keyboard, and drums use the final assembled MIDI. All
playback audio is synthesized from that MIDI (or its instrument-only copies),
not the input recording or Demucs stems.
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import time
import xml.etree.ElementTree as ET

import pretty_midi


# MuseScore 3's stock drumset drops these GM pitches during MIDI import.
# Map them only in notation inputs; full_score.mid remains untouched.
DRUM_NOTATION_MAP = {39: 38, 70: 54, 82: 44}  # clap->snare, maracas->tambourine, shaker->pedal hi-hat


def score_part_name(track: pretty_midi.Instrument, guitar_number: int = 0) -> tuple[str, str]:
    part = family(track)
    if part == "guitar":
        kind = "Acoustic Guitar" if track.program in (24, 25) else "Electric Guitar"
        return (f"{kind} {guitar_number}" if guitar_number else kind,
                "Ac. Guit." if kind == "Acoustic Guitar" else "El. Guit.")
    if part == "bass":
        return (("Acoustic Bass", "Ac. B.") if track.program == 32 else
                ("Synth Bass", "Synth B.") if track.program in (38, 39) else
                ("Electric Bass", "El. B."))
    if part == "piano":
        return (("Organ", "Org.") if track.program in range(16, 24) else
                ("Electric Piano", "El. Pno.") if track.program in range(2, 8) else
                ("Piano", "Pno."))
    return "Drum Set", "Dr."


def musescore_score(source: Path, target: Path, musescore: str, *, force: bool = False) -> None:
    """Import MIDI once, then set MuseScore's printed instrument names explicitly."""
    source_hash = sha256(source)
    stamp = target.with_suffix(target.suffix + ".source_sha256")
    if not force and target.is_file() and stamp.is_file() and stamp.read_text().strip() == source_hash:
        return
    subprocess.run([musescore, "-o", str(target), str(source)], check=True)
    document = ET.parse(target)
    root = document.getroot()
    score = root.find("Score")
    if score is None:
        raise ValueError(f"MuseScore score has no Score element: {target}")
    parts = score.findall("Part")
    tracks = [track for track in pretty_midi.PrettyMIDI(str(source)).instruments if track.notes]
    if len(parts) != len(tracks):
        raise ValueError(f"MuseScore imported {len(parts)} parts for {len(tracks)} MIDI tracks: {source}")
    guitar_count = sum(family(track) == "guitar" for track in tracks)
    guitar_number = 0
    for part, track in zip(parts, tracks):
        if family(track) == "guitar":
            guitar_number += 1
        long_name, short_name = score_part_name(track, guitar_number if guitar_count > 1 else 0)
        instrument = part.find("Instrument")
        if instrument is None:
            raise ValueError(f"MuseScore part has no Instrument element: {target}")
        for parent, tag, value in ((part, "trackName", long_name),
                                   (instrument, "longName", long_name),
                                   (instrument, "shortName", short_name),
                                   (instrument, "trackName", long_name)):
            elements = parent.findall(tag)
            if not elements:
                elements = [ET.SubElement(parent, tag)]
            for element in elements:
                element.text = value
    document.write(target, encoding="utf-8", xml_declaration=True)
    stamp.write_text(source_hash + "\n", encoding="ascii")


def gp5_score(source: Path, target: Path, parts: list[tuple[str, int]], *, force: bool = False) -> None:
    """Change only the publication copy of a TAB's title and playback patch."""
    source_hash = sha256(source)
    stamp = target.with_suffix(target.suffix + ".source_sha256")
    config = json.dumps({"source_sha256": source_hash, "parts": parts}, sort_keys=True)
    if not force and target.is_file() and stamp.is_file() and stamp.read_text().strip() == config:
        return
    try:
        import guitarpro
    except ImportError as exc:
        raise ImportError("pyguitarpro is required to label GP5 score PDFs") from exc
    song = guitarpro.parse(str(source))
    if len(song.tracks) != len(parts):
        raise ValueError(f"GP5 has {len(song.tracks)} tracks for {len(parts)} final-score parts: {source}")
    song.title = parts[0][0] if len(parts) == 1 else " / ".join(name for name, _ in parts)
    for track, (name, program) in zip(song.tracks, parts):
        track.name = name
        track.channel.instrument = program
    guitarpro.write(song, str(target))
    stamp.write_text(config + "\n", encoding="ascii")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def family(track: pretty_midi.Instrument) -> str:
    if track.is_drum:
        return "drums"
    name = track.name.lower()
    if name.startswith(("piano:", "ai generated piano:")) or track.program in range(0, 8) or track.program in range(16, 24):
        return "piano"
    if track.program in range(24, 32):
        return "guitar"
    if track.program in range(32, 40):
        return "bass"
    raise ValueError(f"Unexpected final-score track: {track.name!r}, program={track.program}")


def pdf_pages(path: Path, pdfinfo: str) -> int:
    if not path.is_file() or path.stat().st_size < 1000:
        raise ValueError(f"PDF missing or too small: {path}")
    result = subprocess.run([pdfinfo, str(path)], capture_output=True, text=True, check=True)
    match = re.search(r"^Pages:\s*(\d+)\s*$", result.stdout, re.MULTILINE)
    if not match or int(match.group(1)) < 1:
        raise ValueError(f"PDF has no readable pages: {path}")
    return int(match.group(1))


def check_mp3(path: Path) -> None:
    if not path.is_file() or path.stat().st_size < 1000:
        raise ValueError(f"MP3 missing or too small: {path}")
    with path.open("rb") as stream:
        header = stream.read(3)
    if header != b"ID3" and not (header[0] == 0xFF and header[1] & 0xE0 == 0xE0):
        raise ValueError(f"MP3 has no MPEG audio header: {path}")


def write_json(path: Path, value: dict) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def check_dependencies(musescore: str, node: str, gp5_converter: Path, pdfinfo: str,
                       *, require_gp5: bool = True) -> None:
    tools = [("MuseScore", musescore), ("pdfinfo", pdfinfo)]
    if require_gp5:
        tools.append(("Node.js", node))
    for name, executable in tools:
        if shutil.which(executable) is None:
            raise FileNotFoundError(f"{name} executable not found: {executable}")
    if require_gp5 and not gp5_converter.is_file():
        raise FileNotFoundError(f"GP5-to-PDF converter not found: {gp5_converter}")


def publication_ready(run: Path) -> bool:
    """Validate the full publication contract before --resume skips the stage."""
    try:
        contract = json.loads((run / "scores" / "score_outputs.json").read_text(encoding="utf-8"))
        if contract.get("version") != 5 or sha256(run / "full_score.mid") != contract["full_score_midi_sha256"]:
            return False
        families = {family(track) for track in pretty_midi.PrettyMIDI(str(run / "full_score.mid")).instruments
                    if track.notes}
        manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
        expected = families | ({"guitar_1", "guitar_2"} if manifest.get("guitar_extra_dir") else set())
        if set(contract["instruments"]) != expected or set(contract["audio"]["instruments"]) != expected:
            return False
        pdfs = [contract["full_band"], *contract["instruments"].values()]
        mp3s = [contract["audio"]["full_band"], *contract["audio"]["instruments"].values()]
        for item in pdfs + mp3s:
            relative = Path(item.get("pdf", item.get("mp3", "")))
            if relative.is_absolute() or ".." in relative.parts:
                return False
            path = run / relative
            if not path.is_file() or path.stat().st_size != item["bytes"] or sha256(path) != item["sha256"]:
                return False
        for item in pdfs + mp3s:
            relative_source = Path(item["source"])
            if relative_source.is_absolute() or ".." in relative_source.parts:
                return False
            source = run / relative_source
            if not source.is_file() or sha256(source) != item["source_sha256"]:
                return False
        for item in pdfs:
            for track in item.get("tracks", []):
                if "source_gp5" not in track:
                    continue
                relative_gp5 = Path(track["source_gp5"])
                if relative_gp5.is_absolute() or ".." in relative_gp5.parts:
                    return False
                gp5 = run / relative_gp5
                if not gp5.is_file() or sha256(gp5) != track["source_gp5_sha256"]:
                    return False
        for item in mp3s:
            midi_source = Path(item["midi_source"])
            if midi_source.is_absolute() or ".." in midi_source.parts:
                return False
            if (item.get("converter") != "musescore-score" or
                    Path(item["source"]).suffix != ".mscx" or
                    sha256(run / midi_source) != item["midi_source_sha256"]):
                return False
            check_mp3(run / item["mp3"])
        return True
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError):
        return False


def choose_gp5(directory: Path, part: str) -> Path:
    candidates = sorted(directory.glob("*.gp5"))
    if len(candidates) != 1:
        raise ValueError(f"Expected exactly one final {part} GP5 in {directory}, found {len(candidates)}")
    if candidates[0].stat().st_size == 0:
        raise ValueError(f"Empty {part} GP5: {candidates[0]}")
    return candidates[0]


def export_part_midi(score: pretty_midi.PrettyMIDI, part: str, path: Path) -> list[dict]:
    tracks = [copy.deepcopy(track) for track in score.instruments if track.notes and family(track) == part]
    if not tracks:
        raise ValueError(f"Final score has no {part} notes")
    result = copy.deepcopy(score)
    result.instruments = tracks
    path.parent.mkdir(parents=True, exist_ok=True)
    result.write(str(path))
    return [{"name": str(track.name), "program": int(track.program), "notes": len(track.notes)} for track in tracks]


def notation_midi(source: pretty_midi.PrettyMIDI, path: Path) -> dict[int, int]:
    """Make a render-only copy so unsupported drum hits stay visible in PDF."""
    rendered = copy.deepcopy(source)
    mapped = {pitch: 0 for pitch in DRUM_NOTATION_MAP}
    for track in rendered.instruments:
        if track.is_drum:
            for note in track.notes:
                if note.pitch in DRUM_NOTATION_MAP:
                    mapped[note.pitch] += 1
                    note.pitch = DRUM_NOTATION_MAP[note.pitch]
    path.parent.mkdir(parents=True, exist_ok=True)
    rendered.write(str(path))
    return {pitch: count for pitch, count in mapped.items() if count}


def publish(run: Path, musescore: str, node: str, gp5_converter: Path, pdfinfo: str, force: bool,
            chrome: Path | None = None, render_workers: int = 1) -> dict:
    if not 1 <= render_workers <= 4:
        raise ValueError("render_workers must be between 1 and 4")
    final = run / "full_score.mid"
    manifest_path = run / "manifest.json"
    if not final.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("Completed unified run must contain full_score.mid and manifest.json")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("status") != "complete":
        raise ValueError("MIDI workflow is not complete")
    score = pretty_midi.PrettyMIDI(str(final))
    families = {family(track) for track in score.instruments if track.notes}
    if not families or not families <= {"guitar", "bass", "piano", "drums"}:
        raise ValueError(f"Unexpected band parts: {families}")
    check_dependencies(musescore, node, gp5_converter, pdfinfo,
                       require_gp5=bool(families & {"guitar", "bass"}))
    def score_dir(key: str, default: str) -> Path:
        relative = Path(manifest.get(key, default))
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError(f"Invalid score directory in manifest: {relative}")
        return run / relative

    guitar_dir = score_dir("guitar_score_dir", "guitar")
    guitar_extra_dir = score_dir("guitar_extra_dir", "") if manifest.get("guitar_extra_dir") else None
    out = run / "scores"
    out.mkdir(exist_ok=True)
    source_hash = sha256(final)
    outputs = {}
    audio_outputs = {}
    render_jobs = []
    try:
        previous = json.loads((out / "score_outputs.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        previous = {}
    if not isinstance(previous, dict):
        previous = {}

    def unchanged(target: Path, source: Path, prior: dict) -> bool:
        return (isinstance(prior, dict) and target.is_file()
                and prior.get("source_sha256") == sha256(source)
                and prior.get("bytes") == target.stat().st_size
                and prior.get("sha256") == sha256(target))

    def render(key: str, source: Path, converter: str, command: list[str], tracks: list[dict]) -> None:
        def task() -> None:
            render_pdf(key, source, converter, command, tracks)
        render_jobs.append(task)

    def render_pdf(key: str, source: Path, converter: str, command: list[str], tracks: list[dict]) -> None:
        target = out / f"{key}.pdf"
        prior = previous.get("full_band", {}) if key == "full_band" else previous.get("instruments", {}).get(key, {})
        if force or not unchanged(target, source, prior):
            target.unlink(missing_ok=True)
            subprocess.run(command, check=True)
        pages = pdf_pages(target, pdfinfo)
        outputs[key] = {"pdf": target.relative_to(run).as_posix(),
                        "source": source.relative_to(run).as_posix(),
                        "source_sha256": sha256(source), "converter": converter,
                        "tracks": tracks, "pages": pages, "bytes": target.stat().st_size,
                        "sha256": sha256(target)}

    def render_audio(key: str, source: Path, tracks: list[dict]) -> None:
        def task() -> None:
            export_audio(key, source, tracks)
        render_jobs.append(task)

    def export_audio(key: str, source: Path, tracks: list[dict]) -> None:
        # MuseScore 3's direct MIDI-to-MP3 export can silently render GM guitar
        # and bass programs as piano. Importing to MSCX first preserves patches.
        notation = out / f"{key}_audio.mscx"
        musescore_score(source, notation, musescore, force=force)
        target = out / f"{key}.mp3"
        prior = (previous.get("audio", {}).get("full_band", {}) if key == "band"
                 else previous.get("audio", {}).get("instruments", {}).get(key, {}))
        if force or not unchanged(target, notation, prior):
            target.unlink(missing_ok=True)
            subprocess.run([musescore, "-o", str(target), str(notation)], check=True)
        check_mp3(target)
        audio_outputs[key] = {"mp3": target.relative_to(run).as_posix(),
                              "source": notation.relative_to(run).as_posix(),
                              "source_sha256": sha256(notation),
                              "midi_source": source.relative_to(run).as_posix(),
                              "midi_source_sha256": sha256(source),
                              "converter": "musescore-score",
                              "tracks": tracks, "bytes": target.stat().st_size,
                              "sha256": sha256(target)}

    part_midis = {}
    part_tracks = {}
    for part in ("guitar", "bass", "piano", "drums"):
        if part in families:
            part_midis[part] = out / f"{part}.mid"
            part_tracks[part] = export_part_midi(score, part, part_midis[part])
    if guitar_extra_dir is not None:
        guitars = [track for track in score.instruments if track.notes and family(track) == "guitar"]
        if len(guitars) != 2:
            raise ValueError(f"Expected two guitar tracks for separate TAB PDFs, got {len(guitars)}")
        for index, track in enumerate(guitars, start=1):
            key = f"guitar_{index}"
            one = copy.deepcopy(score)
            one.instruments = [copy.deepcopy(track)]
            path = out / f"{key}.mid"
            one.write(str(path))
            part_midis[key] = path
            part_tracks[key] = [{"name": str(track.name), "program": int(track.program),
                                 "notes": len(track.notes)}]

    full_render = out / "full_band_render.mid"
    drum_mapping_counts = notation_midi(score, full_render)
    full_notation = out / "full_band_render.mscx"
    musescore_score(full_render, full_notation, musescore, force=force)
    render("full_band", full_notation, "musescore-score", [musescore, "-o", str(out / "full_band.pdf"), str(full_notation)],
           [{"name": str(t.name), "program": int(t.program), "notes": len(t.notes)} for t in score.instruments if t.notes])
    for part in ("piano", "drums"):
        if part not in families:
            continue
        part_midi = part_midis[part]
        tracks = part_tracks[part]
        render_midi = out / f"{part}_render.mid" if part == "drums" else part_midi
        if part == "drums":
            notation_midi(pretty_midi.PrettyMIDI(str(part_midi)), render_midi)
        notation = out / f"{part}_render.mscx"
        musescore_score(render_midi, notation, musescore, force=force)
        render(part, notation, "musescore-score",
               [musescore, "-o", str(out / f"{part}.pdf"), str(notation)], tracks)
    for part in ("guitar", "bass"):
        if part not in families:
            continue
        if part == "guitar" and guitar_extra_dir is not None:
            notation = out / "guitar_render.mscx"
            musescore_score(part_midis["guitar"], notation, musescore, force=force)
            render("guitar", notation, "musescore-score",
                   [musescore, "-o", str(out / "guitar.pdf"), str(notation)],
                   part_tracks["guitar"])
            for key, directory in (("guitar_1", guitar_dir), ("guitar_2", guitar_extra_dir)):
                gp5 = choose_gp5(directory, key)
                guitar = pretty_midi.PrettyMIDI(str(part_midis[key])).instruments[0]
                label, _ = score_part_name(guitar, int(key[-1]))
                prepared_gp5 = out / f"{key}_render.gp5"
                gp5_score(gp5, prepared_gp5, [(label, int(guitar.program))], force=force)
                command = [node, str(gp5_converter), str(prepared_gp5), str(out / f"{key}.pdf"),
                           "--timeout-ms", "180000"]
                if chrome is not None:
                    command.extend(("--chrome", str(chrome)))
                render(key, prepared_gp5, "gp5-to-pdf", command,
                       [{"name": key, "source_gp5": gp5.relative_to(run).as_posix(),
                         "source_gp5_sha256": sha256(gp5)}])
        else:
            directory = guitar_dir if part == "guitar" else run / "bass"
            gp5 = choose_gp5(directory, part)
            instruments = pretty_midi.PrettyMIDI(str(part_midis[part])).instruments
            labels = [(score_part_name(inst, index if part == "guitar" and len(instruments) > 1 else 0)[0],
                       int(inst.program)) for index, inst in enumerate(instruments, 1)]
            prepared_gp5 = out / f"{part}_render.gp5"
            gp5_score(gp5, prepared_gp5, labels, force=force)
            command = [node, str(gp5_converter), str(prepared_gp5), str(out / f"{part}.pdf"),
                       "--timeout-ms", "180000"]
            if chrome is not None:
                command.extend(("--chrome", str(chrome)))
            render(part, prepared_gp5, "gp5-to-pdf", command,
                   [{"name": part, "source_gp5": gp5.relative_to(run).as_posix(),
                     "source_gp5_sha256": sha256(gp5)}])

    band_audio = out / "band.mid"
    score.write(str(band_audio))
    render_audio("band", band_audio,
                 [{"name": str(track.name), "program": int(track.program), "notes": len(track.notes)}
                  for track in score.instruments if track.notes])
    for part in ("guitar", "bass", "piano", "drums"):
        if part in families:
            render_audio(part, part_midis[part], part_tracks[part])
    if guitar_extra_dir is not None:
        for key in ("guitar_1", "guitar_2"):
            render_audio(key, part_midis[key], part_tracks[key])

    # All score, GP5 and MIDI inputs are finalized before export. Each worker
    # writes a distinct target; cap processes to avoid exhausting the CPU Pod.
    if render_workers == 1:
        for task in render_jobs:
            task()
    else:
        with ThreadPoolExecutor(max_workers=render_workers) as pool:
            futures = [pool.submit(task) for task in render_jobs]
            for future in futures:
                future.result()

    extra_keys = ("guitar_1", "guitar_2") if guitar_extra_dir is not None else ()
    contract = {"version": 5, "full_score_midi": final.relative_to(run).as_posix(), "full_score_midi_sha256": source_hash,
                "drum_notation_map": {str(k): v for k, v in DRUM_NOTATION_MAP.items()},
                "drum_notation_mapped_counts": {str(k): v for k, v in drum_mapping_counts.items()},
                "full_band": outputs["full_band"],
                "instruments": {part: outputs[part] for part in ("guitar", "bass", "piano", "drums", *extra_keys) if part in outputs},
                "audio": {"full_band": audio_outputs["band"],
                          "instruments": {part: audio_outputs[part] for part in ("guitar", "bass", "piano", "drums", *extra_keys)
                                          if part in audio_outputs}}}
    contract_path = out / "score_outputs.json"
    write_json(contract_path, contract)
    manifest["score_outputs"] = contract_path.relative_to(run).as_posix()
    manifest["score_publication"] = "complete"
    write_json(manifest_path, manifest)
    # The shared PVC can briefly lag immediately after parallel renderers exit.
    # Confirm the complete contract before reporting publication success.
    for attempt in range(10):
        if publication_ready(run):
            break
        if attempt < 9:
            time.sleep(0.5)
    else:
        raise RuntimeError(f"Published scores did not pass contract validation: {contract_path}")
    return contract


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run", type=Path, help="completed unified run directory")
    parser.add_argument("--musescore", default="musescore3")
    parser.add_argument("--node", default="node")
    parser.add_argument("--gp5-converter", type=Path,
                        default=Path("/data/rocky-unified/ml/gp5_to_pdf/convert.js"))
    parser.add_argument("--pdfinfo", default="pdfinfo")
    parser.add_argument("--chrome", type=Path, help="optional Chrome executable for GP5-to-PDF")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--render-workers", type=int, default=2,
                        help="parallel PDF/MP3 exports (1-4; default 2)")
    args = parser.parse_args()
    result = publish(args.run.resolve(), args.musescore, args.node,
                     args.gp5_converter.resolve(), args.pdfinfo, args.force, args.chrome,
                     args.render_workers)
    print(json.dumps({"full_band": result["full_band"]["pages"],
                      "instruments": {key: value["pages"] for key, value in result["instruments"].items()},
                      "audio": {"full_band": result["audio"]["full_band"]["mp3"],
                                "instruments": {key: value["mp3"] for key, value in
                                                result["audio"]["instruments"].items()}}}))


if __name__ == "__main__":
    main()
