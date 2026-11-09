"""Writes the same files unified.py and publish_scores.py write, without any model."""

import json
from pathlib import Path

STEMS = ("drums", "bass", "guitar", "piano")


def write_manifest(run: Path, completed, status="running", **extra):
    run.mkdir(parents=True, exist_ok=True)
    (run / "manifest.json").write_text(json.dumps({"completed": list(completed), "status": status, **extra}))


def write_progress(run: Path, stem: str, completed: int, total: int):
    d = run / "stem_midi"
    d.mkdir(parents=True, exist_ok=True)
    with (d / f"{stem}.progress.jsonl").open("a") as f:
        f.write(json.dumps({"stage": "transcribe", "completed": completed, "total": total,
                            "fraction": completed / total, "elapsed_sec": 1.0, "eta_sec": 1.0}) + "\n")


def write_outputs(run: Path, parts=("guitar", "bass", "drums"), generated=("piano",), extra_guitar=False):
    """Like unified.py (contract 8) + publish_scores.py (score_outputs version 3)."""
    stages = ["bs_roformer", *[f"muscriptor_{s}" for s in STEMS], "merge_stems", "beat_this", "align",
              "guitar_tab", "bass_tab", "midigpt", "normalize_generated", "assemble", "publish_outputs"]
    write_manifest(run, stages, status="complete", original_parts=sorted(parts),
                   generated_targets=list(generated), score_publication="complete",
                   score_outputs="scores/score_outputs.json",
                   config={"original": "unknown", "pipeline_contract": 8})
    (run / "full_score.mid").write_bytes(b"MThd-full")
    scores = run / "scores"
    scores.mkdir(exist_ok=True)
    keys = [*parts, *generated] + (["guitar_1", "guitar_2"] if extra_guitar else [])
    instruments, audio = {}, {}
    for p in keys:
        (scores / f"{p}.pdf").write_bytes(b"%PDF-" + p.encode())
        (scores / f"{p}.mid").write_bytes(b"MThd")
        (scores / f"{p}.mp3").write_bytes(b"ID3" + p.encode())
        instruments[p] = {"pdf": f"scores/{p}.pdf", "pages": 2}
        audio[p] = {"mp3": f"scores/{p}.mp3"}
    (scores / "full_band.pdf").write_bytes(b"%PDF-full")
    (scores / "band.mp3").write_bytes(b"ID3band")
    (scores / "score_outputs.json").write_text(json.dumps({
        "version": 3, "full_score_midi": "full_score.mid",
        "full_band": {"pdf": "scores/full_band.pdf", "pages": 5}, "instruments": instruments,
        "audio": {"full_band": {"mp3": "scores/band.mp3"}, "instruments": audio}}))


class FakeRunner:
    def __init__(self, fail_stage=None):
        self.fail_stage = fail_stage
        self.calls = []

    def cancel(self, job_id):
        self.calls.append(("cancel", job_id))

    def run_midi(self, job_id, audio, run, requested, log, note=lambda _m: None, original="unknown"):
        self.calls.append(("midi", job_id, audio.name, requested, original))
        if self.fail_stage == "midi":
            write_manifest(run, ["demucs"], status="failed", error="RuntimeError: muscriptor_drums exited 1")
            raise RuntimeError("job failed")
        write_outputs(run)
        (run / "scores" / "score_outputs.json").unlink()  # the PDF stage writes this

    def run_pdf(self, job_id, run, log, note=lambda _m: None):
        self.calls.append(("pdf", job_id))
        if self.fail_stage == "pdf":
            raise RuntimeError("pdf job failed")
        write_outputs(run)
