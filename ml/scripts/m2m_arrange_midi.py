#!/usr/bin/env python
"""Arrange one multitrack MIDI into piano, guitar, bass, and drum parts."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import sys
import time
from pathlib import Path

import mido
import torch
from transformers import AutoTokenizer, GPT2LMHeadModel


ROOT = Path(__file__).resolve().parents[2]
REMI_Z = ROOT / "ml" / "external" / "REMI-z"
sys.path.insert(0, str(REMI_Z))
from remi_z import Bar, MultiTrack, Track  # noqa: E402


MODEL_PATH = ROOT / "ml" / "models" / "m2m_arranger"
DRUM_MODEL_PATH = ROOT / "ml" / "models" / "m2m_drummer"
TOKENIZER_PATH = ROOT / "ml" / "models" / "m2m_ft"
TARGETS = {
    "piano": (0, set(range(0, 8))),
    "guitar": (24, set(range(24, 32))),
    "bass": (32, set(range(32, 40))),
    "drum": (128, {128}),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_bar(bar_id, tracks, meter, tempo):
    return Bar.from_tracks(bar_id, tracks, time_signature=meter, tempo=tempo)


def filtered_bar(bar: Bar, excluded_programs: set[int]) -> Bar:
    tracks = [
        Track.from_note_list(inst, list(track.notes))
        for inst, track in bar.tracks.items()
        if inst not in excluded_programs
    ]
    return build_bar(bar.bar_id, tracks, bar.time_signature, bar.tempo)


def make_model_input(tokenizer, device, target_program, content, history):
    tokens = ["[BOS]", "[INST]", f"i-{target_program}", "[PITCH]"]
    tokens.extend(content)
    tokens.append("[HIST]")
    tokens.extend(history)
    tokens.append("[SEP]")
    encoded = tokenizer(
        [" ".join(tokens)], return_tensors="pt", padding=False,
        add_special_tokens=False,
    )["input_ids"]
    return encoded.to(device)


def decode_generated(tokenizer, model, input_ids, generation_kwargs):
    with torch.inference_mode():
        output = model.generate(
            input_ids,
            pad_token_id=tokenizer.pad_token_id,
            **generation_kwargs,
        )
    decoded = tokenizer.batch_decode(output)[0]
    if "[SEP]" not in decoded:
        raise RuntimeError("Model output did not contain [SEP]")
    generated = decoded.split("[SEP]", 1)[1]
    if "[EOS]" in generated:
        return generated.split("[EOS]", 1)[0].strip()
    # Keep the last complete bar if a capped generation reaches the token limit.
    tokens = generated.split()
    if "b-1" not in tokens:
        raise RuntimeError("Capped model output did not finish a complete bar")
    return " ".join(tokens[: len(tokens) - 1 - tokens[::-1].index("b-1") + 1])


def load_model(path: Path, device: str):
    # The current CPU exposes AVX2 but not native BF16, so FP32 avoids slow BF16 emulation.
    model = GPT2LMHeadModel.from_pretrained(path, torch_dtype=torch.float32)
    model.eval().to(device)
    return model


def generate_pitched_part(source: MultiTrack, tokenizer, model, device,
                          name: str, seed: int, log):
    program, family = TARGETS[name]
    kwargs = {
        "max_new_tokens": 180,
        "use_cache": True,
        "bad_words_ids": [[tokenizer.pad_token_id],
                          [tokenizer.convert_tokens_to_ids("[PAD]")],
                          [tokenizer.convert_tokens_to_ids("[INST]")],
                          [tokenizer.convert_tokens_to_ids("[SEP]")]],
        "no_repeat_ngram_size": 10,
        "do_sample": True,
        "top_k": 10,
        "top_p": 1.0,
        "temperature": 1.0,
    }
    generated = []
    previous = None
    for index, source_bar in enumerate(source.bars):
        random.seed(seed + index + program * 1009)
        torch.manual_seed(seed + index + program * 1009)
        context = filtered_bar(source_bar, family | {128})
        if not context.get_all_notes():
            result = build_bar(source_bar.bar_id, [], source_bar.time_signature, source_bar.tempo)
        else:
            content = context.get_content_seq(with_dur=False)
            history = previous.to_remiz_seq() if previous is not None else []
            input_ids = make_model_input(tokenizer, device, program, content, history)
            encoded = decode_generated(tokenizer, model, input_ids, kwargs)
            raw_bar = Bar.from_remiz_str(encoded)
            notes = []
            for inst, track in raw_bar.tracks.items():
                if inst in family:
                    notes.extend(track.notes)
            canonical_track = Track.from_note_list(program, notes) if notes else None
            result = build_bar(
                source_bar.bar_id,
                [canonical_track] if canonical_track else [],
                source_bar.time_signature,
                source_bar.tempo,
            )
        generated.append(result)
        previous = result
        log(f"{name}: bar {index + 1}/{len(source.bars)} ({sum(len(t.notes) for t in result.tracks.values())} notes)")
    return generated


def generate_drum_part(source: MultiTrack, tokenizer, model, device, seed: int, log):
    generated = []
    previous_segment = None
    kwargs = {
        "max_new_tokens": 512,
        "use_cache": True,
        "bad_words_ids": [[tokenizer.pad_token_id],
                          [tokenizer.convert_tokens_to_ids("[PAD]")],
                          [tokenizer.convert_tokens_to_ids("[INST]")],
                          [tokenizer.convert_tokens_to_ids("[SEP]")]],
        "no_repeat_ngram_size": 0,
        "do_sample": True,
        "top_k": 20,
        "top_p": 1.0,
        "temperature": 1.0,
    }
    segment_count = (len(source.bars) + 3) // 4
    for segment_index, start in enumerate(range(0, len(source.bars), 4)):
        source_bars = source.bars[start:start + 4]
        context_bars = [filtered_bar(bar, {128}) for bar in source_bars]
        content = MultiTrack.from_bars(context_bars).get_content_seq(with_dur=False)
        history = previous_segment.to_remiz_seq() if previous_segment is not None else []
        input_ids = make_model_input(tokenizer, device, 128, content, history)
        random.seed(seed + 900001 + segment_index)
        torch.manual_seed(seed + 900001 + segment_index)
        encoded = decode_generated(tokenizer, model, input_ids, kwargs)
        raw_segment = MultiTrack.from_remiz_str(encoded)
        for offset, source_bar in enumerate(source_bars):
            source_index = start + offset
            raw_bar = raw_segment.bars[offset] if offset < len(raw_segment.bars) else None
            notes = list(raw_bar.tracks.get(128).notes) if raw_bar and 128 in raw_bar.tracks else []
            drum_track = Track.from_note_list(128, notes) if notes else None
            generated.append(build_bar(
                source_bar.bar_id,
                [drum_track] if drum_track else [],
                source_bar.time_signature,
                source_bar.tempo,
            ))
        previous_segment = MultiTrack.from_bars(generated[-len(source_bars):])
        log(f"drum: segment {segment_index + 1}/{segment_count}, bars {start + 1}-{start + len(source_bars)}")
    return generated


def absolute_meta_events(mid: mido.MidiFile, event_types: set[str], scale: int):
    found = {}
    for track in mid.tracks:
        tick = 0
        for message in track:
            tick += message.time
            if message.type in event_types:
                found[(tick * scale, message.type, str(message))] = message.copy(time=0)
    return [(tick, msg) for (tick, _, _), msg in found.items()]


def restore_source_timing(output_path: Path, input_path: Path):
    source = mido.MidiFile(input_path)
    result = mido.MidiFile(output_path)
    scale = result.ticks_per_beat / source.ticks_per_beat
    timing_types = {"set_tempo", "time_signature"}
    timing = absolute_meta_events(source, timing_types, scale)
    if not timing:
        return
    first = result.tracks[0]
    kept = []
    tick = 0
    for msg in first:
        tick += msg.time
        if msg.type not in timing_types and msg.type != "end_of_track":
            kept.append((tick, msg.copy(time=0)))
    for track in result.tracks[1:]:
        tick = 0
        new_messages = []
        for msg in track:
            tick += msg.time
            if msg.type not in timing_types:
                new_messages.append((tick, msg.copy(time=0)))
        track.clear()
        previous_tick = 0
        for event_tick, msg in sorted(new_messages, key=lambda item: item[0]):
            msg.time = event_tick - previous_tick
            track.append(msg)
            previous_tick = event_tick
    combined = kept + timing
    end_tick = max((event_tick for event_tick, _ in combined), default=0)
    combined.append((end_tick, mido.MetaMessage("end_of_track", time=0)))
    combined.sort(key=lambda item: (item[0], 0 if item[1].type in timing_types else 1))
    first.clear()
    previous_tick = 0
    for event_tick, msg in combined:
        msg.time = event_tick - previous_tick
        first.append(msg)
        previous_tick = event_tick
    result.save(output_path)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input_midi", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seed", type=int, default=20261005)
    parser.add_argument("--device", default="cpu")
    parser.add_argument("--parts", nargs="+", choices=list(TARGETS), default=list(TARGETS))
    args = parser.parse_args()
    input_path = args.input_midi.resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    log_path = output_dir / "generation.log"
    log_path.write_text("", encoding="utf-8")

    def log(message):
        print(message, flush=True)
        with log_path.open("a", encoding="utf-8") as stream:
            stream.write(message + "\n")

    if not input_path.is_file():
        raise FileNotFoundError(input_path)
    required_models = [MODEL_PATH / "model.safetensors"]
    if "drum" in args.parts:
        required_models.append(DRUM_MODEL_PATH / "model.safetensors")
    for path in (*required_models, TOKENIZER_PATH / "tokenizer.json"):
        if not path.is_file():
            raise FileNotFoundError(f"Missing model asset: {path}")

    start_time = time.time()
    source = MultiTrack.from_midi(str(input_path))
    if not source.bars:
        raise ValueError("Input MIDI did not produce any bars")
    if any(bar.time_signature != (4, 4) for bar in source.bars):
        raise ValueError("M2M fine-tuning expects 4/4; input has another meter")
    log(f"Input parsed: {len(source.bars)} bars, meter 4/4, bar tempi={sorted(source.tempos)}")
    log(f"Input SHA-256: {sha256(input_path)}")
    tokenizer = AutoTokenizer.from_pretrained(TOKENIZER_PATH, local_files_only=True)
    band_model = load_model(MODEL_PATH, args.device)
    log("Loaded m2m_arranger checkpoint in FP32 for this AVX2 CPU")
    parts = {}
    for part in ("piano", "guitar", "bass"):
        if part in args.parts:
            parts[part] = generate_pitched_part(source, tokenizer, band_model, args.device,
                                                part, args.seed, log)
    del band_model
    if args.device.startswith("cuda"):
        torch.cuda.empty_cache()
    if "drum" in args.parts:
        drum_model = load_model(DRUM_MODEL_PATH, args.device)
        log("Loaded m2m_drummer checkpoint in FP32 for the paper's separate drum task")
        parts["drum"] = generate_drum_part(source, tokenizer, drum_model, args.device, args.seed, log)
        del drum_model

    combined_bars = []
    for bar_index, source_bar in enumerate(source.bars):
        tracks = []
        for part in args.parts:
            tracks.extend(parts[part][bar_index].tracks.values())
        combined_bars.append(build_bar(source_bar.bar_id, tracks,
                                       source_bar.time_signature, source_bar.tempo))
    result = MultiTrack.from_bars(combined_bars)
    suffix = "four_parts" if len(args.parts) == len(TARGETS) else "_and_".join(args.parts)
    output_path = output_dir / f"{input_path.stem}_m2m_{suffix}.mid"
    result.to_midi(str(output_path))
    restore_source_timing(output_path, input_path)

    check = mido.MidiFile(output_path)
    actual = MultiTrack.from_midi(str(output_path))
    stats = {}
    for part in args.parts:
        program, _ = TARGETS[part]
        notes = [note for bar in actual.bars for note in bar.tracks.get(program, Track(program, {})).notes]
        stats[part] = {
            "program": program,
            "note_count": len(notes),
            "pitch_min": min((note.pitch for note in notes), default=None),
            "pitch_max": max((note.pitch for note in notes), default=None),
        }
    summary = {
        "input": str(input_path),
        "input_sha256": sha256(input_path),
        "output": str(output_path),
        "seed": args.seed,
        "device": args.device,
        "models": {"pitched": "LongshenOu/m2m_arranger",
                   **({"drums": "LongshenOu/m2m_drummer"} if "drum" in args.parts else {})},
        "tokenizer": "LongshenOu/m2m_ft",
        "bars": len(actual.bars),
        "ticks_per_beat": check.ticks_per_beat,
        "instruments": stats,
        "parts": args.parts,
        "source_tempo_events": len(absolute_meta_events(mido.MidiFile(input_path), {"set_tempo"}, 1)),
        "elapsed_seconds": round(time.time() - start_time, 2),
    }
    (output_dir / "manifest.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    log(json.dumps(summary, ensure_ascii=False))
    log(f"Saved MIDI: {output_path}")


if __name__ == "__main__":
    main()
