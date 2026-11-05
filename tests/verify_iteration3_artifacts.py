"""Read-only checks for Iteration 3 Pod YAML and saved score bundles.

This validates file integrity and declared contracts. It does not run models,
judge musical accuracy, or prove that a saved bundle used the current commit.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import pretty_midi
import yaml


POD_FILES = ("pod.yaml", "files-pod.yaml", "unified-pod.example.yaml",
             "score-pdf-pod.example.yaml")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def relative_file(root: Path, name: str) -> Path:
    relative = Path(name)
    assert not relative.is_absolute() and ".." not in relative.parts, name
    path = root / relative
    assert path.is_file(), path
    return path


def pdf_pages(path: Path, pdfinfo: str) -> int:
    result = subprocess.run([pdfinfo, str(path)], check=True, capture_output=True, text=True)
    match = re.search(r"^Pages:\s*(\d+)\s*$", result.stdout, re.MULTILINE)
    assert match, path
    return int(match.group(1))


def verify_pods(repo: Path) -> int:
    root = repo / "ml" / "pipeline" / "sgs"
    for name in POD_FILES:
        document = yaml.safe_load((root / name).read_text(encoding="utf-8"))
        assert document["apiVersion"] == "v1" and document["kind"] == "Pod", name
        spec = document["spec"]
        assert spec["nodeSelector"]["kubernetes.io/hostname"] == "ferrari", name
        assert spec["restartPolicy"] == "Never", name
        volumes = {item["name"] for item in spec["volumes"]
                   if item.get("persistentVolumeClaim", {}).get("claimName") == "muscriptor-data"}
        assert volumes, name
        assert any(mount["name"] in volumes and mount["mountPath"] == "/data"
                   for container in spec["containers"]
                   for mount in container.get("volumeMounts", [])), name
        if name in ("pod.yaml", "unified-pod.example.yaml"):
            assert any(container["resources"]["limits"].get("nvidia.com/gpu") == 1
                       for container in spec["containers"]), name
    return len(POD_FILES)


def verify_run(run: Path, pdfinfo: str) -> dict[str, int]:
    manifest = json.loads((run / "manifest.json").read_text(encoding="utf-8"))
    contract = json.loads((run / "scores" / "score_outputs.json").read_text(encoding="utf-8"))
    assert manifest["status"] == "complete", run
    assert contract["version"] in (4, 5), run
    source = relative_file(run, contract["full_score_midi"])
    assert sha256(source) == contract["full_score_midi_sha256"], source
    score = pretty_midi.PrettyMIDI(str(source))
    assert any(track.notes for track in score.instruments), source
    assert set(contract["instruments"]) == set(contract["audio"]["instruments"]), run

    pdfs = [contract["full_band"], *contract["instruments"].values()]
    audio = [contract["audio"]["full_band"], *contract["audio"]["instruments"].values()]
    for item in (*pdfs, *audio):
        path = relative_file(run, item.get("pdf", item.get("mp3", "")))
        assert path.stat().st_size == item["bytes"] and sha256(path) == item["sha256"], path
        source_path = relative_file(run, item["source"])
        assert sha256(source_path) == item["source_sha256"], source_path
        if "midi_source" in item:
            midi_path = relative_file(run, item["midi_source"])
            assert sha256(midi_path) == item["midi_source_sha256"], midi_path
    for item in pdfs:
        path = relative_file(run, item["pdf"])
        assert pdf_pages(path, pdfinfo) == item["pages"] > 0, path
        for track in item.get("tracks", []):
            if "source_gp5" in track:
                gp5 = relative_file(run, track["source_gp5"])
                assert sha256(gp5) == track["source_gp5_sha256"], gp5
    for item in audio:
        path = relative_file(run, item["mp3"])
        with path.open("rb") as stream:
            header = stream.read(3)
        assert header == b"ID3" or (len(header) >= 2 and header[0] == 0xFF
                                     and header[1] & 0xE0 == 0xE0), path
    return {"contract": contract["version"], "pdfs": len(pdfs), "mp3s": len(audio),
            "midi_tracks": len(score.instruments)}


def verify_gp5_reference(manifest_path: Path, pdfinfo: str) -> int:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    root = manifest_path.parent
    for entry in manifest["files"]:
        path = relative_file(root, entry["pdf"])
        assert sha256(path) == entry["pdf_sha256"], path
        assert pdf_pages(path, pdfinfo) == entry["pages"] > 0, path
    return len(manifest["files"])


def verify_tabs(root: Path) -> dict[str, int]:
    """Apply T6's fingering limits to original and generated guitar/bass GP5s."""
    import guitarpro as gp

    counts = {"files": 0, "guitar_onsets": 0, "bass_onsets": 0,
              "invalid_onsets": 0, "out_of_range_notes": 0, "bass_chords": 0}
    for song in root.iterdir():
        if not song.is_dir():
            continue
        for folder in ("guitar", "guitar_generated", "bass"):
            for file in (song / folder).glob("*.gp5"):
                counts["files"] += 1
                for track in gp.parse(str(file)).tracks:
                    strings = len(track.strings)
                    for measure in track.measures:
                        for voice in measure.voices:
                            for beat in voice.beats:
                                notes = [note for note in beat.notes if note.type == gp.NoteType.normal]
                                if not notes:
                                    continue
                                key = "bass_onsets" if folder == "bass" else "guitar_onsets"
                                counts[key] += 1
                                fretted = [note.value for note in notes if note.value > 0]
                                invalid = (len(notes) > strings or
                                           len({note.string for note in notes}) < len(notes) or
                                           bool(fretted) and max(fretted) - min(fretted) > 4)
                                counts["invalid_onsets"] += int(invalid)
                                counts["out_of_range_notes"] += sum(
                                    not 0 <= note.value <= 20 for note in notes)
                                if folder == "bass":
                                    counts["bass_chords"] += int(len(notes) > 1)
    assert counts["files"] > 0, root
    assert (counts["invalid_onsets"] == counts["out_of_range_notes"] ==
            counts["bass_chords"] == 0), counts
    return counts


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--run", type=Path, action="append", default=[])
    parser.add_argument("--gp5-manifest", type=Path)
    parser.add_argument("--tab-root", type=Path, help="song folders with guitar/, guitar_generated/, bass/")
    parser.add_argument("--pdfinfo", default="pdfinfo")
    args = parser.parse_args()
    result = {"pod_manifests": verify_pods(args.repo),
              "runs": {str(path): verify_run(path, args.pdfinfo) for path in args.run}}
    if args.gp5_manifest:
        result["gp5_reference_pdfs"] = verify_gp5_reference(args.gp5_manifest, args.pdfinfo)
    if args.tab_root:
        result["tab_playability"] = verify_tabs(args.tab_root)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
