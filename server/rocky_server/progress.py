"""Turn a unified.py run directory into the progress the Android app shows.

The app has four stages (see app/.../progress/JobProgress.kt). The weights
below must match the app's Stage weights so the server's percent and the
app's percent agree.
"""

from __future__ import annotations

import json
from pathlib import Path

APP_STAGES = ("SEPARATE", "TRANSCRIBE", "BEATS", "ARRANGE")
WEIGHTS = {"SEPARATE": 0.10, "TRANSCRIBE": 0.75, "BEATS": 0.05, "ARRANGE": 0.10}

TRANSCRIBE_STEMS = ("drums", "bass", "guitar", "piano")

SEPARATION_STAGES = ("bs_roformer", "demucs")  # BS-RoFormer since contract 8; Demucs before

# unified.py stage name -> app stage. Anything not listed (TAB, MIDI-GPT,
# assembly, PDF publication) counts as ARRANGE.
PIPELINE_TO_APP = {
    "bs_roformer": "SEPARATE",
    "demucs": "SEPARATE",
    **{f"muscriptor_{s}": "TRANSCRIBE" for s in TRANSCRIBE_STEMS},
    "muscriptor_batch": "TRANSCRIBE",  # contract 10: all stems in one stage
    "merge_stems": "BEATS",
    "beat_this": "BEATS",
    "align": "BEATS",
}


def read_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def last_progress_line(path: Path) -> dict | None:
    """Last complete JSON line of a MuScriptor progress.jsonl file."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            return json.loads(line)
        except ValueError:
            continue  # a line being written right now
    return None


def stems_to_transcribe(manifest: dict) -> tuple[str, ...]:
    """unified.py transcribes only the declared original instruments (all four when unknown)."""
    original = (manifest.get("config") or {}).get("original", "unknown")
    if original == "unknown" or not isinstance(original, list):
        return TRANSCRIBE_STEMS
    stems = tuple(s for s in TRANSCRIBE_STEMS if s in original)
    return stems or TRANSCRIBE_STEMS


def stem_done(stem: str, completed) -> bool:
    """Contract 10 records one muscriptor_batch stage; older runs one stage per stem."""
    return "muscriptor_batch" in completed or f"muscriptor_{stem}" in completed


def transcription_chunks(run: Path, completed_stages: list[str], stems=TRANSCRIBE_STEMS) -> tuple[int, int]:
    """(chunks done, chunks total) summed over the transcribed stems."""
    per_stem_total = 0
    done = 0
    for stem in stems:
        line = last_progress_line(run / "stem_midi" / f"{stem}.progress.jsonl")
        if line:
            per_stem_total = max(per_stem_total, int(line.get("total") or 0))
        if stem_done(stem, completed_stages):
            done += int(line.get("total") or 0) if line else 0
        elif line:
            done += int(line.get("completed") or 0)
    total = per_stem_total * len(stems)
    return min(done, total), total


def current_app_stage(completed: list[str], stems=TRANSCRIBE_STEMS) -> str:
    """The app stage of the first unfinished pipeline stage."""
    done = set(completed)
    if not done & set(SEPARATION_STAGES):
        return "SEPARATE"
    if not all(stem_done(s, done) for s in stems):
        return "TRANSCRIBE"
    if not {"merge_stems", "beat_this", "align"} <= done:
        return "BEATS"
    return "ARRANGE"


def arrange_steps(manifest: dict) -> tuple[int, int]:
    """Rough progress through ARRANGE: TAB, MIDI-GPT, assembly, then PDF/MP3 publication.

    Which of these stages run depends on the song (guitar count, generated parts),
    so the total is the finished ones plus what is surely still to come.
    """
    completed = manifest.get("completed", [])
    done = len([n for n in completed if n not in PIPELINE_TO_APP and n != "publish_outputs"])
    published = manifest.get("score_publication") == "complete"
    if published:
        return done + 1, done + 1
    remaining = 1 if "assemble" in completed else 3  # (assemble +) publication
    return done, done + remaining


def overall_fraction(stage: str, completed: int, total: int) -> float:
    before = 0.0
    for s in APP_STAGES:
        if s == stage:
            break
        before += WEIGHTS[s]
    frac = 0.0 if total <= 0 else max(0.0, min(1.0, completed / total))
    return before + WEIGHTS[stage] * frac


def run_progress(run: Path, elapsed_sec: float | None) -> dict:
    """Progress fields for GET /jobs/{id} while the pipeline is running."""
    manifest = read_json(run / "manifest.json") or {"completed": []}
    completed = manifest.get("completed", [])
    stems = stems_to_transcribe(manifest)
    stage = current_app_stage(completed, stems)
    if stage == "TRANSCRIBE":
        done, total = transcription_chunks(run, completed, stems)
    elif stage == "ARRANGE":
        done, total = arrange_steps(manifest)
    else:
        done, total = 0, 1
    fraction = overall_fraction(stage, done, total)
    eta = None
    # Like MuScriptor, give no estimate until the first chunk has finished.
    transcribe_started = stage != "SEPARATE" and not (stage == "TRANSCRIBE" and done == 0)
    if elapsed_sec is not None and transcribe_started and fraction >= 0.05:
        eta = int(round(elapsed_sec * (1 - fraction) / fraction))
    return {"stage": stage, "completed": done, "total": total,
            "fraction": round(fraction, 4), "eta_sec": eta}


def result_files(run: Path) -> dict:
    """Downloadable files of a finished run, as paths relative to the run.

    Reads scores/score_outputs.json written by publish_scores.py (version 3:
    PDF and MP3 for the band and each part; version 1 had PDF only). Parts are
    guitar, bass, piano, drums, plus guitar_1/guitar_2 when MIDI-GPT added a
    second guitar. Each part's MIDI is scores/<part>.mid when present.
    """
    contract = read_json(run / "scores" / "score_outputs.json")
    if contract is None:
        raise FileNotFoundError("scores/score_outputs.json is missing")
    manifest = read_json(run / "manifest.json") or {}
    audio = contract.get("audio") or {}
    part_audio = audio.get("instruments") or {}
    old_midi = {"guitar": "guitar/guitar.mid", "bass": "bass/bass.mid"}  # version 1 layout

    def present(rel: str | None) -> str | None:
        return rel if rel and (run / rel).is_file() else None

    parts = {}
    for part, info in contract.get("instruments", {}).items():
        entry = {"pdf": info["pdf"], "pages": info.get("pages")}
        midi = present(f"scores/{part}.mid") or present(old_midi.get(part))
        if midi:
            entry["midi"] = midi
        mp3 = present((part_audio.get(part) or {}).get("mp3"))
        if mp3:
            entry["mp3"] = mp3
        parts[part] = entry
    full = {"pdf": contract["full_band"]["pdf"], "pages": contract["full_band"].get("pages"),
            "midi": contract.get("full_score_midi", "full_score.mid")}
    band_mp3 = present((audio.get("full_band") or {}).get("mp3"))
    if band_mp3:
        full["mp3"] = band_mp3
    return {
        "full_band": full,
        "instruments": parts,
        "original_parts": manifest.get("original_parts", []),
        "generated_parts": manifest.get("generated_targets", []),
        # Declared parts whose stem barely sounds (note gate "faint"); the app marks them with a warning.
        "faint_parts": manifest.get("faint_parts", []),
    }


def allowed_paths(result: dict) -> set[str]:
    paths = set()
    for entry in [result["full_band"], *result["instruments"].values()]:
        paths.update(entry[k] for k in ("pdf", "midi", "mp3") if entry.get(k))
    return paths
