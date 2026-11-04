"""Stand-in for unified.py / publish_scores.py in the emulator end-to-end test.

Writes the same files the real stages write, with valid (tiny) PDF and MIDI
content so the app can render and play them. Takes a few seconds and reports
MuScriptor-style progress so the app's progress screen moves.

  python ci_fake_pipeline.py midi <audio> <run>
  python ci_fake_pipeline.py pdf <run>
"""

import json
import struct
import sys
import time
from pathlib import Path

STEMS = ("drums", "bass", "guitar", "piano")
PARTS = ("guitar", "bass", "drums")      # "heard" in the song
GENERATED = ("piano",)                    # made by MIDI-GPT when requested


def pdf(text: str) -> bytes:
    """A one-page PDF with a line of text."""
    stream = f"BT /F1 24 Tf 72 720 Td ({text}) Tj ET".encode()
    objs = [b"<< /Type /Catalog /Pages 2 0 R >>",
            b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] /Contents 4 0 R "
            b"/Resources << /Font << /F1 5 0 R >> >> >>",
            b"<< /Length %d >>\nstream\n" % len(stream) + stream + b"\nendstream",
            b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, o in enumerate(objs, 1):
        offsets.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objs) + 1)
    out += b"".join(b"%010d 00000 n \n" % o for o in offsets)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objs) + 1, xref)
    return bytes(out)


def midi() -> bytes:
    """One track, four quarter notes."""
    ev = b""
    for pitch in (60, 64, 67, 72):
        ev += b"\x00\x90" + bytes([pitch, 100]) + b"\x83\x60\x80" + bytes([pitch, 0])
    ev += b"\x00\xff\x2f\x00"
    return b"MThd" + struct.pack(">IHHH", 6, 0, 1, 480) + b"MTrk" + struct.pack(">I", len(ev)) + ev


# one silent MPEG-1 Layer III frame (128 kbps, 44.1 kHz), repeated: enough for a player to open
MP3 = (b"\xff\xfb\x90\x64" + b"\x00" * 413) * 40


def manifest(run: Path, completed, status="running", **extra):
    path = run / "manifest.json"
    old = json.loads(path.read_text()) if path.exists() else {}
    old.update({"completed": list(completed), "status": status, **extra})
    path.write_text(json.dumps(old))


def run_midi(run: Path) -> None:
    run.mkdir(parents=True, exist_ok=True)
    manifest(run, [], config={"original": "unknown", "pipeline_contract": 8})
    time.sleep(1)
    done = ["bs_roformer"]
    manifest(run, done)
    (run / "stem_midi").mkdir(exist_ok=True)
    for stem in STEMS:
        for i in range(1, 4):
            with (run / "stem_midi" / f"{stem}.progress.jsonl").open("a") as f:
                f.write(json.dumps({"completed": i, "total": 3, "fraction": i / 3, "eta_sec": 1}) + "\n")
            time.sleep(0.2)
        done.append(f"muscriptor_{stem}")
        manifest(run, done)
    done += ["merge_stems", "beat_this", "align", "guitar_tab", "bass_tab", "midigpt",
             "normalize_generated", "assemble"]
    (run / "full_score.mid").write_bytes(midi())
    manifest(run, done, status="complete", original_parts=sorted(PARTS),
             generated_targets=list(GENERATED), score_publication="pending")


def run_pdf(run: Path) -> None:
    scores = run / "scores"
    scores.mkdir(exist_ok=True)
    time.sleep(1)
    instruments, audio = {}, {}
    for p in (*PARTS, *GENERATED):
        (scores / f"{p}.pdf").write_bytes(pdf(f"ROCKY {p}"))
        (scores / f"{p}.mid").write_bytes(midi())
        (scores / f"{p}.mp3").write_bytes(MP3)
        instruments[p] = {"pdf": f"scores/{p}.pdf", "pages": 1}
        audio[p] = {"mp3": f"scores/{p}.mp3"}
    (scores / "full_band.pdf").write_bytes(pdf("ROCKY full band"))
    (scores / "band.mp3").write_bytes(MP3)
    (scores / "score_outputs.json").write_text(json.dumps({
        "version": 3, "full_score_midi": "full_score.mid",
        "full_band": {"pdf": "scores/full_band.pdf", "pages": 1}, "instruments": instruments,
        "audio": {"full_band": {"mp3": "scores/band.mp3"}, "instruments": audio}}))
    m = json.loads((run / "manifest.json").read_text())
    m["score_publication"] = "complete"
    (run / "manifest.json").write_text(json.dumps(m))


if __name__ == "__main__":
    if sys.argv[1] == "midi":
        run_midi(Path(sys.argv[3]))
    else:
        run_pdf(Path(sys.argv[2]))
