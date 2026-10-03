#!/usr/bin/env python3
"""Generate collapsed BabySlakh instrument tracks with pretrained MIDI-RWKV.

For each case, every stem in the requested target family is removed. All other
MIDI stems form the prompt passed to MIDI-RWKV's ``generate_new_track``. The
excluded target notes are written only to ``reference.mid`` and never enter the
model prompt or attribute controls.
"""

from __future__ import annotations

import argparse
import contextlib
import copy
import ctypes
import hashlib
import json
import os
import random
import subprocess
import sys
import time
import traceback
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np
import torch
import yaml
from miditok import MMM
from symusic import Score
from transformers import GenerationConfig


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATASET_ROOT = PROJECT_ROOT.parent / "babyslakh_16k"
DEFAULT_MIDI_RWKV_ROOT = PROJECT_ROOT / "ml" / "external" / "MIDI-RWKV"
DEFAULT_OUTPUT_ROOT = PROJECT_ROOT / "ml" / "outputs" / "midi_rwkv_babyslakh"

TARGETS = ("Piano", "Guitar", "Bass", "Drums")

# Canonical General MIDI programs after removing detailed instrument variants.
# MidiTok represents drum tracks as Program_-1.
CANONICAL_PROGRAM = {
    "Piano": 0,
    "Guitar": 24,
    "Bass": 32,
    "Drums": -1,
}

_DLL_DIRECTORY_HANDLES: list[Any] = []
_DLL_DEPENDENCIES: list[Any] = []


@dataclass(frozen=True)
class Stem:
    stem_id: str
    midi_path: Path
    metadata: dict[str, Any]
    category: str | None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate collapsed Piano, Guitar, Bass, and Drums tracks for "
            "BabySlakh with MIDI-RWKV generate_new_track()."
        )
    )
    parser.add_argument("--dataset-root", type=Path, default=DEFAULT_DATASET_ROOT)
    parser.add_argument("--midi-rwkv-root", type=Path, default=DEFAULT_MIDI_RWKV_ROOT)
    parser.add_argument("--output-root", type=Path, default=DEFAULT_OUTPUT_ROOT)
    parser.add_argument(
        "--model-path",
        type=Path,
        default=None,
        help="Converted GGML model. Default: rwkv.cpp/python/rwkv_cpp/rcpp.bin.",
    )
    parser.add_argument(
        "--checkpoint-path",
        type=Path,
        default=None,
        help="Official pretrained PyTorch checkpoint. Default: midi_rwkv.pth.",
    )
    parser.add_argument(
        "--reconvert-model",
        action="store_true",
        help="Recreate the FP16 GGML model from the pretrained checkpoint.",
    )
    parser.add_argument("--tokenizer-path", type=Path, default=None)
    parser.add_argument(
        "--targets",
        nargs="+",
        choices=TARGETS,
        default=list(TARGETS),
        help="Collapsed target families to generate.",
    )
    parser.add_argument(
        "--tracks",
        nargs="*",
        default=None,
        help="Optional directory names such as Track00001. Default: all tracks.",
    )
    parser.add_argument("--seed", type=int, default=110)
    parser.add_argument("--max-new-tokens", type=int, default=8192)
    parser.add_argument("--temperature", type=float, default=1.0)
    parser.add_argument("--repetition-penalty", type=float, default=1.2)
    parser.add_argument("--top-k", type=int, default=20)
    parser.add_argument("--top-p", type=float, default=0.95)
    parser.add_argument("--epsilon-cutoff", type=float, default=9e-4)
    parser.add_argument("--overwrite", action="store_true")
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop at the first failed case instead of recording and continuing.",
    )
    return parser.parse_args()


def normalize_text(value: Any) -> str:
    return " ".join(str(value or "").strip().lower().replace("_", " ").split())


def collapse_instrument(metadata: dict[str, Any]) -> str | None:
    """Map a detailed BabySlakh instrument to a shared experiment family."""
    if bool(metadata.get("is_drum")):
        return "Drums"

    try:
        program = int(metadata.get("program_num"))
    except (TypeError, ValueError):
        program = None

    if program in (-1, 128):
        return "Drums"
    if program is not None:
        if 0 <= program <= 7:
            return "Piano"
        if 24 <= program <= 31:
            return "Guitar"
        if 32 <= program <= 39:
            return "Bass"

    labels = {
        normalize_text(metadata.get("inst_class")),
        normalize_text(metadata.get("midi_program_name")),
    }
    if any(label == "drums" or label.startswith("drum ") for label in labels):
        return "Drums"
    if any("piano" in label for label in labels):
        return "Piano"
    if any("guitar" in label for label in labels):
        return "Guitar"
    if any(
        label == "bass" or label.startswith("bass ") or " bass " in label
        for label in labels
    ):
        return "Bass"
    return None


def canonicalize_track(track: Any, category: str | None) -> None:
    """Remove detailed program distinctions for the four shared families."""
    if category is None:
        return
    program = CANONICAL_PROGRAM[category]
    track.program = 0 if program == -1 else program
    track.is_drum = category == "Drums"
    track.name = category


def is_requested_generated_track(track: Any, category: str) -> bool:
    """Return whether a decoded final track has the requested MIDI identity."""
    if category == "Drums":
        return bool(track.is_drum)
    return not bool(track.is_drum) and track.program == CANONICAL_PROGRAM[category]


def load_stems(
    track_dir: Path, metadata: dict[str, Any]
) -> tuple[list[Stem], list[str]]:
    midi_dir = track_dir / str(metadata.get("midi_dir", "MIDI"))
    stems: list[Stem] = []
    missing: list[str] = []
    for stem_id, stem_metadata in sorted(metadata.get("stems", {}).items()):
        midi_path = midi_dir / f"{stem_id}.mid"
        if not midi_path.is_file():
            missing.append(stem_id)
            continue
        stems.append(
            Stem(
                stem_id=stem_id,
                midi_path=midi_path,
                metadata=dict(stem_metadata),
                category=collapse_instrument(stem_metadata),
            )
        )
    return stems, missing


def source_score_path(track_dir: Path, fallback_stem: Stem) -> Path:
    full_midi = track_dir / "all_src.mid"
    return full_midi if full_midi.is_file() else fallback_stem.midi_path


def score_template(track_dir: Path, fallback_stem: Stem) -> Score:
    template = Score(source_score_path(track_dir, fallback_stem))
    template.tracks = []
    return template


def append_stem_tracks(destination: Score, stems: Iterable[Stem]) -> None:
    for stem in stems:
        source = Score(stem.midi_path)
        if source.ticks_per_quarter != destination.ticks_per_quarter:
            source = source.resample(tpq=destination.ticks_per_quarter)
        for source_track in source.tracks:
            track = copy.deepcopy(source_track)
            canonicalize_track(track, stem.category)
            destination.tracks.append(track)


def make_score(track_dir: Path, fallback_stem: Stem, stems: Sequence[Stem]) -> Score:
    score = score_template(track_dir, fallback_stem)
    append_stem_tracks(score, stems)
    return score


def filter_unsupported_pitches(score: Score, tokenizer: MMM) -> dict[str, Any]:
    """Remove notes outside the released tokenizer's melodic/drum vocabularies."""
    melodic_pitches = {
        int(token.removeprefix("Pitch_"))
        for token in tokenizer.vocab
        if token.startswith("Pitch_")
    }
    drum_pitches = {
        int(token.removeprefix("PitchDrum_"))
        for token in tokenizer.vocab
        if token.startswith("PitchDrum_")
    }
    removed_melodic = 0
    removed_drums = 0
    for track in score.tracks:
        allowed = drum_pitches if track.is_drum else melodic_pitches
        retained_notes = [note for note in track.notes if note.pitch in allowed]
        removed = len(track.notes) - len(retained_notes)
        track.notes = retained_notes
        if track.is_drum:
            removed_drums += removed
        else:
            removed_melodic += removed
    return {
        "melodic_pitch_range": [min(melodic_pitches), max(melodic_pitches)],
        "drum_pitch_range": [min(drum_pitches), max(drum_pitches)],
        "removed_melodic_notes": removed_melodic,
        "removed_drum_notes": removed_drums,
    }


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def stem_manifest(stem: Stem) -> dict[str, Any]:
    return {
        "stem_id": stem.stem_id,
        "midi_path": str(stem.midi_path.resolve()),
        "collapsed_category": stem.category,
        "original_inst_class": stem.metadata.get("inst_class"),
        "original_program_num": stem.metadata.get("program_num"),
        "original_program_name": stem.metadata.get("midi_program_name"),
        "original_is_drum": bool(stem.metadata.get("is_drum")),
    }


def resolve_tracks(dataset_root: Path, requested: Sequence[str] | None) -> list[Path]:
    discovered = sorted(path for path in dataset_root.glob("Track*") if path.is_dir())
    if requested is None:
        return discovered
    requested_set = set(requested)
    selected = [path for path in discovered if path.name in requested_set]
    missing = sorted(requested_set - {path.name for path in selected})
    if missing:
        raise FileNotFoundError(f"Unknown BabySlakh tracks: {', '.join(missing)}")
    return selected


def prepare_imports(midi_rwkv_root: Path) -> tuple[Any, Any, Any]:
    python_dir = midi_rwkv_root / "rwkv.cpp" / "python"
    if not python_dir.is_dir():
        raise FileNotFoundError(
            f"MIDI-RWKV rwkv.cpp Python directory not found: {python_dir}"
        )
    sys.path.insert(0, str(python_dir))

    if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
        dll_dir = midi_rwkv_root / "rwkv.cpp"
        _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(dll_dir)))
        for dependency in ("libunwind.dll", "libc++.dll"):
            dependency_path = dll_dir / dependency
            if dependency_path.is_file():
                _DLL_DEPENDENCIES.append(
                    ctypes.CDLL(str(dependency_path), winmode=0)
                )

    # Imported only after the selected official clone has been added to sys.path.
    from inference import generate_new_track
    from rwkv_cpp.cpp_model import CppModelConfig, CustomGenerator

    return generate_new_track, CppModelConfig, CustomGenerator


def prepare_pretrained_model(
    *,
    midi_rwkv_root: Path,
    checkpoint_path: Path,
    model_path: Path,
    force: bool,
) -> None:
    """Convert the official PyTorch weights to rwkv.cpp FP16 when needed."""
    if not checkpoint_path.is_file():
        raise FileNotFoundError(
            f"Pretrained MIDI-RWKV checkpoint not found: {checkpoint_path}"
        )
    if model_path.is_file() and not force:
        return

    converter = midi_rwkv_root / "rwkv.cpp" / "python" / "convert_pytorch_to_ggml.py"
    if not converter.is_file():
        raise FileNotFoundError(f"rwkv.cpp checkpoint converter not found: {converter}")
    model_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Converting pretrained checkpoint to FP16 GGML: {model_path}")
    subprocess.run(
        [
            sys.executable,
            str(converter),
            str(checkpoint_path),
            str(model_path),
            "FP16",
        ],
        check=True,
    )


def build_manifest_base(
    *,
    track_dir: Path,
    target: str,
    retained: Sequence[Stem],
    excluded: Sequence[Stem],
    missing_midi_stems: Sequence[str],
    args: argparse.Namespace,
    checkpoint_path: Path,
    checkpoint_sha256: str,
    model_path: Path,
    tokenizer_path: Path,
    model_sha256: str,
) -> dict[str, Any]:
    return {
        "status": "running",
        "track": track_dir.name,
        "target": target,
        "collapse_policy": {
            "Piano": {"gm_programs": "0-7", "canonical_program": 0},
            "Guitar": {"gm_programs": "24-31", "canonical_program": 24},
            "Bass": {"gm_programs": "32-39", "canonical_program": 32},
            "Drums": {"is_drum": True, "canonical_program_token": -1},
        },
        "target_program_token": CANONICAL_PROGRAM[target],
        "attribute_controls": [],
        "retained_stems": [stem_manifest(stem) for stem in retained],
        "excluded_stems": [stem_manifest(stem) for stem in excluded],
        "missing_midi_stems": list(missing_midi_stems),
        "seed": args.seed,
        "sampling": {
            "temperature": args.temperature,
            "repetition_penalty": args.repetition_penalty,
            "top_k": args.top_k,
            "top_p": args.top_p,
            "epsilon_cutoff": args.epsilon_cutoff,
            "max_new_tokens": args.max_new_tokens,
        },
        "model_path": str(model_path.resolve()),
        "model_sha256": model_sha256,
        "pretrained": True,
        "checkpoint_path": str(checkpoint_path.resolve()),
        "checkpoint_sha256": checkpoint_sha256,
        "converted_model_format": "FP16 GGML",
        "tokenizer_path": str(tokenizer_path.resolve()),
        "excluded_notes_used_for_conditioning": False,
    }


def run_case(
    *,
    track_dir: Path,
    target: str,
    model: Any,
    tokenizer: MMM,
    generate_new_track: Any,
    generation_config: GenerationConfig,
    args: argparse.Namespace,
    checkpoint_path: Path,
    checkpoint_sha256: str,
    model_path: Path,
    tokenizer_path: Path,
    model_sha256: str,
) -> None:
    metadata_path = track_dir / "metadata.yaml"
    metadata = yaml.safe_load(metadata_path.read_text(encoding="utf-8"))
    stems, missing_midi_stems = load_stems(track_dir, metadata)
    if not stems:
        raise RuntimeError(f"No MIDI stems found for {track_dir.name}")

    excluded = [stem for stem in stems if stem.category == target]
    retained = [stem for stem in stems if stem.category != target]
    output_dir = args.output_root / track_dir.name / target.lower()
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "manifest.json"

    if manifest_path.is_file() and not args.overwrite:
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        if existing.get("status") == "completed":
            print(f"[skip] {track_dir.name}/{target}: completed output exists")
            return

    manifest = build_manifest_base(
        track_dir=track_dir,
        target=target,
        retained=retained,
        excluded=excluded,
        missing_midi_stems=missing_midi_stems,
        args=args,
        checkpoint_path=checkpoint_path,
        checkpoint_sha256=checkpoint_sha256,
        model_path=model_path,
        tokenizer_path=tokenizer_path,
        model_sha256=model_sha256,
    )

    if not excluded:
        manifest["status"] = "skipped"
        manifest["reason"] = f"No {target} stem found after family collapse"
        write_json(manifest_path, manifest)
        print(f"[skip] {track_dir.name}/{target}: no target stems")
        return
    if not retained:
        raise RuntimeError(f"No conditioning stems remain for {track_dir.name}/{target}")

    try:
        timeline_end = Score(source_score_path(track_dir, stems[0])).end()
        context_score = make_score(track_dir, stems[0], retained)
        reference_score = make_score(track_dir, stems[0], excluded)
        reference_score.dump_midi(output_dir / "reference.mid")

        manifest["tokenizer_pitch_filter"] = filter_unsupported_pitches(
            context_score, tokenizer
        )
        input_tokens = tokenizer.encode(context_score)
        manifest["input_token_count"] = len(input_tokens.ids)
        manifest["context_track_count"] = len(context_score.tracks)
        manifest["reference_track_count"] = len(reference_score.tracks)
        manifest["timeline_end_tick"] = timeline_end

        set_seed(args.seed)
        start = time.perf_counter()
        log_path = output_dir / "generation.log"
        with log_path.open("w", encoding="utf-8") as log_handle:
            with contextlib.redirect_stdout(log_handle), contextlib.redirect_stderr(
                log_handle
            ):
                with warnings.catch_warnings(record=True) as caught:
                    warnings.simplefilter("always")
                    combined_score = generate_new_track(
                        model,
                        tokenizer,
                        (CANONICAL_PROGRAM[target], []),
                        context_score,
                        {"generation_config": generation_config},
                    )
        runtime_seconds = time.perf_counter() - start

        warning_messages = [str(item.message) for item in caught]
        track_end_generated = not any(
            "failed to predict a <TRACK_END>" in item for item in warning_messages
        )
        # MidiTok can merge context stems that share a program while decoding,
        # so comparing the decoded track count with the original stem count is
        # invalid. generate_new_track() appends the requested track last.
        if not combined_score.tracks:
            raise RuntimeError("MIDI-RWKV decoded an empty score")
        decoded_track = combined_score.tracks[-1]
        if not is_requested_generated_track(decoded_track, target):
            raise RuntimeError(
                "MIDI-RWKV's final decoded track does not match "
                f"the requested {target} program"
            )
        if not decoded_track.notes:
            raise RuntimeError(
                f"MIDI-RWKV decoded an empty {target} track; increase "
                "--max-new-tokens or change the sampling seed"
            )

        combined_score = combined_score.clip(0, timeline_end, clip_end=True)
        generated_track = copy.deepcopy(combined_score.tracks[-1])
        if not generated_track.notes:
            raise RuntimeError(
                f"Generated {target} notes fall outside the source timeline"
            )
        canonicalize_track(generated_track, target)
        combined_score.tracks[-1] = copy.deepcopy(generated_track)

        generated_score = score_template(track_dir, stems[0])
        generated_score.tracks.append(copy.deepcopy(generated_track))
        generated_score.dump_midi(output_dir / "generated.mid")
        combined_score.dump_midi(output_dir / "combined.mid")

        output_tokens = tokenizer.encode(generated_score)
        manifest.update(
            {
                "status": "completed",
                "runtime_seconds": runtime_seconds,
                "generated_token_count_after_decode": len(output_tokens.ids),
                "generated_track_count": 1,
                "generated_note_count": len(generated_track.notes),
                "decoded_combined_track_count": len(combined_score.tracks),
                "track_end_generated": track_end_generated,
                "warnings": warning_messages,
                "outputs": {
                    "generated": "generated.mid",
                    "combined": "combined.mid",
                    "reference": "reference.mid",
                    "log": "generation.log",
                },
            }
        )
        write_json(manifest_path, manifest)
        print(f"[done] {track_dir.name}/{target}: {runtime_seconds:.2f}s")
    except Exception as exc:
        manifest.update(
            {
                "status": "failed",
                "error_type": type(exc).__name__,
                "error": str(exc),
                "traceback": traceback.format_exc(),
            }
        )
        write_json(manifest_path, manifest)
        print(f"[failed] {track_dir.name}/{target}: {exc}", file=sys.stderr)
        if args.fail_fast:
            raise


def main() -> int:
    args = parse_args()
    args.dataset_root = args.dataset_root.resolve()
    args.midi_rwkv_root = args.midi_rwkv_root.resolve()
    args.output_root = args.output_root.resolve()

    if not args.dataset_root.is_dir():
        raise FileNotFoundError(f"BabySlakh dataset not found: {args.dataset_root}")
    if not args.midi_rwkv_root.is_dir():
        raise FileNotFoundError(f"MIDI-RWKV clone not found: {args.midi_rwkv_root}")

    model_path = (
        args.model_path.resolve()
        if args.model_path
        else args.midi_rwkv_root / "rwkv.cpp" / "python" / "rwkv_cpp" / "rcpp.bin"
    )
    checkpoint_path = (
        args.checkpoint_path.resolve()
        if args.checkpoint_path
        else args.midi_rwkv_root / "midi_rwkv.pth"
    )
    tokenizer_path = (
        args.tokenizer_path.resolve()
        if args.tokenizer_path
        else args.midi_rwkv_root / "train" / "tokenizer" / "tokenizer_with_acs.json"
    )
    prepare_pretrained_model(
        midi_rwkv_root=args.midi_rwkv_root,
        checkpoint_path=checkpoint_path,
        model_path=model_path,
        force=args.reconvert_model,
    )
    if not tokenizer_path.is_file():
        raise FileNotFoundError(f"Tokenizer not found: {tokenizer_path}")

    generate_new_track, cpp_model_config, custom_generator = prepare_imports(
        args.midi_rwkv_root
    )
    tokenizer = MMM(params=tokenizer_path)
    print(f"Loading pretrained MIDI-RWKV parameters: {model_path}")
    model = custom_generator(cpp_model_config(str(model_path), ""), tokenizer)
    generation_config = GenerationConfig(
        num_beams=1,
        temperature=args.temperature,
        repetition_penalty=args.repetition_penalty,
        top_k=args.top_k,
        top_p=args.top_p,
        epsilon_cutoff=args.epsilon_cutoff,
        max_new_tokens=args.max_new_tokens,
        do_sample=True,
    )

    tracks = resolve_tracks(args.dataset_root, args.tracks)
    if not tracks:
        raise RuntimeError(f"No Track* directories found in {args.dataset_root}")

    args.output_root.mkdir(parents=True, exist_ok=True)
    checkpoint_digest = sha256(checkpoint_path)
    model_digest = sha256(model_path)
    print(
        f"Running {len(tracks) * len(args.targets)} cases: "
        f"{len(tracks)} tracks x {len(args.targets)} targets"
    )
    for track_dir in tracks:
        for target in args.targets:
            run_case(
                track_dir=track_dir,
                target=target,
                model=model,
                tokenizer=tokenizer,
                generate_new_track=generate_new_track,
                generation_config=generation_config,
                args=args,
                checkpoint_path=checkpoint_path,
                checkpoint_sha256=checkpoint_digest,
                model_path=model_path,
                tokenizer_path=tokenizer_path,
                model_sha256=model_digest,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
