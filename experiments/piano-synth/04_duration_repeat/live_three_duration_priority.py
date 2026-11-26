"""Run the established piano+other and duration/repetition reduction on three live WAVs.

One GPU05 pod runs one song. Inputs and outputs are isolated on rocky-work.
"""
from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import traceback
from pathlib import Path

import pretty_midi
import soundfile as sf

ROOT = Path('/work/live_duration_priority_20261125')
MODEL_DATA = Path('/data')
PYTHON = Path('/data/rocky-unified/.venv/bin/python')
SEPARATE = Path('/data/pipeline/separate_bs_roformer.py')
PIPELINE = Path('/data/pipeline')
BEAT_ALIGN = Path('/data/rocky-unified/ml/beat_align')
MODEL = Path('/data/model/model.safetensors')
BEAT_CHECKPOINT = Path('/data/cache/torch/hub/checkpoints/beat_this-final0.ckpt')
INSTRUMENTS = ('acoustic_piano', 'electric_piano', 'organ',
               'synth_strings', 'synth_lead', 'synth_pad', 'brass_section')
PROGRAMS = {'acoustic_piano': 0, 'electric_piano': 2, 'organ': 16,
            'synth_strings': 50, 'synth_lead': 80, 'synth_pad': 88,
            'brass_section': 61}

sys.path.insert(0, str(PIPELINE))
sys.path.insert(0, str(BEAT_ALIGN))
sys.path.insert(0, '/experiment')
from rule_gates import GateConfig, gate_stem  # noqa: E402
from align import align_midi, detect_beats, save_beats  # noqa: E402
import piano_other_duration_priority_20261125 as reducer  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temporary, path)


def valid_midi(path: Path) -> bool:
    try:
        pretty_midi.PrettyMIDI(str(path))
        return True
    except (OSError, ValueError, EOFError):
        return False


def tracks(path: Path) -> list[dict]:
    midi = pretty_midi.PrettyMIDI(str(path))
    return [{'name': inst.name, 'program': int(inst.program), 'notes': len(inst.notes)}
            for inst in midi.instruments]


def ensure_labels(path: Path) -> None:
    for track in tracks(path):
        program = track['program']
        if program not in PROGRAMS.values():
            raise ValueError(f'Unexpected program {program}')
        expected = next(name for name, value in PROGRAMS.items() if value == program)
        if track['name'].replace(' ', '_') != expected:
            raise ValueError(f"Unexpected label {track['name']!r} for {expected}")


def family(inst: pretty_midi.Instrument) -> str | None:
    return 'piano_other' if not inst.is_drum and inst.program in PROGRAMS.values() else None


def matching_wavs(a: Path, b: Path) -> bool:
    try:
        left, right = sf.info(str(a)), sf.info(str(b))
        return ((left.frames, left.samplerate, left.channels)
                == (right.frames, right.samplerate, right.channels)
                and left.frames > 0 and left.channels == 2)
    except (OSError, RuntimeError):
        return False


def separate(song: str, source: Path, dest: Path) -> tuple[Path, Path]:
    piano, other = dest / 'piano.wav', dest / 'other.wav'
    if matching_wavs(piano, other):
        return piano, other
    dest.mkdir(parents=True, exist_ok=True)
    temporary = ROOT / 'temporary' / song
    if not temporary.resolve().is_relative_to((ROOT / 'temporary').resolve()):
        raise ValueError('Unsafe temporary directory')
    if temporary.exists():
        shutil.rmtree(temporary)
    temporary.mkdir(parents=True)
    log_path = dest / 'separation.log'
    with log_path.open('w', encoding='utf-8') as log:
        subprocess.run([str(PYTHON), str(SEPARATE), str(source), str(temporary),
                        '--models-dir', '/data/bsrofo/models',
                        '--lib-dir', '/data/bsrofo/pylib'],
                       stdout=log, stderr=subprocess.STDOUT, check=True)
    if not matching_wavs(temporary / 'piano.wav', temporary / 'other.wav'):
        raise ValueError('Invalid separated piano/other WAVs')
    os.replace(temporary / 'piano.wav', piano)
    os.replace(temporary / 'other.wav', other)
    shutil.rmtree(temporary)
    return piano, other


def combine(piano: Path, other: Path, target: Path) -> dict:
    if not matching_wavs(piano, other):
        raise ValueError('Piano/other sample grid mismatch')
    info = sf.info(str(piano))
    if target.is_file():
        existing = sf.info(str(target))
        if (existing.frames, existing.samplerate, existing.channels) == (
                info.frames, info.samplerate, info.channels):
            return {'reused': True, 'frames': info.frames,
                    'samplerate': info.samplerate, 'channels': info.channels}
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix('.wav.tmp')
    peak = 0.0
    above_full_scale = 0
    with sf.SoundFile(str(piano)) as a, sf.SoundFile(str(other)) as b, sf.SoundFile(
            str(temporary), mode='w', samplerate=info.samplerate, channels=info.channels,
            format='WAV', subtype='FLOAT') as output:
        while True:
            x = a.read(65536, dtype='float32', always_2d=True)
            y = b.read(65536, dtype='float32', always_2d=True)
            if x.shape != y.shape:
                raise ValueError('Piano/other block mismatch')
            if not len(x):
                break
            mixed = x + y
            peak = max(peak, float(abs(mixed).max()))
            above_full_scale += int((abs(mixed) > 1.0).sum())
            output.write(mixed)
    os.replace(temporary, target)
    return {'reused': False, 'frames': info.frames, 'samplerate': info.samplerate,
            'channels': info.channels, 'peak': round(peak, 5),
            'samples_above_1': above_full_scale}


def transcribe(song: str, source: Path, stem: Path, destination: Path,
               hashes: dict, combined: dict) -> dict:
    from muscriptor.transcription_model import TranscriptionModel
    from muscriptor.utils.midi import ExportOptions
    destination.mkdir(parents=True, exist_ok=True)
    raw, gated, aligned = (destination / name for name in ('raw.mid', 'gated.mid', 'aligned.mid'))
    if not valid_midi(raw):
        model = TranscriptionModel.load_model(weights_path=str(MODEL), device='cuda', dtype=None)
        events = list(model.transcribe(
            stem, use_sampling=False, temperature=1.0, cfg_coef=1.0,
            instruments=list(INSTRUMENTS), batch_size=None,
            no_eos_is_ok=True, beam_size=1, prelude_forcing=True))
        midi_bytes = model.events_to_midi_bytes(iter(events), beat_grid=None,
                                                 export=ExportOptions())
        temporary = raw.with_suffix('.mid.tmp')
        temporary.write_bytes(midi_bytes)
        os.replace(temporary, raw)
        del model, events, midi_bytes
        gc.collect()
    ensure_labels(raw)
    duration = float(sf.info(str(stem)).duration)
    gate = gate_stem(raw, stem, 'piano_other', gated, GateConfig(), family,
                     declared=False, original_unknown=True, duration_sec=duration)
    ensure_labels(gated)
    beats, downbeats = detect_beats(source, device='cuda', checkpoint=str(BEAT_CHECKPOINT))
    if len(beats) < 2:
        raise ValueError('Beat This returned fewer than two beats')
    save_beats(destination / 'beats.json', beats, downbeats)
    alignment = align_midi(gated, aligned, beats=beats, downbeats=downbeats,
                           drum_sync=True)
    ensure_labels(aligned)
    record = {'status': 'complete', 'song': song, 'duration_sec': round(duration, 3),
              'source_sha256': hashes['input_sha256'],
              'piano_sha256': hashes['piano_sha256'],
              'other_sha256': hashes['other_sha256'],
              'combined_sha256': hashes['combined_sha256'],
              'raw_sha256': sha256(raw), 'gated_sha256': sha256(gated),
              'aligned_sha256': sha256(aligned),
              'combined': combined, 'raw': tracks(raw), 'gated': tracks(gated),
              'aligned': tracks(aligned), 'gate': gate,
              'beats': len(beats), 'downbeats': len(downbeats),
              'alignment': {'bpm': alignment.bpm, 'meter': alignment.meter,
                            'note_count': alignment.note_count}}
    atomic_json(destination / 'status.json', record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--song', required=True, choices=('L15', 'P03', 'P07'))
    args = parser.parse_args()
    song = args.song
    source = ROOT / 'input' / f'{song}.wav'
    if not source.is_file():
        raise FileNotFoundError(source)
    final_path = ROOT / 'outputs' / f'{song}_duration_repeat_priority_playable.mid'
    final_status = ROOT / 'outputs' / f'{song}_status.json'
    if final_path.exists() or final_status.exists():
        raise FileExistsError(f'Output already exists for {song}')
    started = time.monotonic()
    record = {'song': song, 'input': str(source), 'input_sha256': sha256(source),
              'script_sha256': sha256(Path(__file__)),
              'reducer_sha256': sha256(Path(reducer.__file__)),
              'separation_code_sha256': sha256(SEPARATE),
              'gate_code_sha256': sha256(PIPELINE / 'rule_gates.py'),
              'align_code_sha256': sha256(BEAT_ALIGN / 'align.py'),
              'model_sha256': sha256(MODEL),
              'beat_checkpoint_sha256': sha256(BEAT_CHECKPOINT)}
    try:
        print(f'{song}: separating', flush=True)
        piano, other = separate(song, source, ROOT / 'stems' / song)
        record.update(piano_sha256=sha256(piano), other_sha256=sha256(other))
        stem = ROOT / 'combined' / f'{song}_piano_other.wav'
        combined = combine(piano, other, stem)
        record.update(combined_sha256=sha256(stem), combined=combined)
        print(f'{song}: transcribing and aligning', flush=True)
        transcription_dir = ROOT / 'transcription' / 'live' / song
        transcription = transcribe(song, source, stem, transcription_dir, record, combined)
        reducer.SOURCE = ROOT / 'transcription'
        reducer.OUT = ROOT / 'reduced'
        print(f'{song}: reducing', flush=True)
        reduced = reducer.run_song(1, 'live', song)
        if reduced['status'] != 'ok':
            raise RuntimeError(reduced['error'])
        reduced_midi = Path(reduced['output'])
        final_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(reduced_midi, final_path)
        if sha256(final_path) != reduced['output_sha256']:
            raise ValueError('Final MIDI hash mismatch')
        record.update(status='complete', transcription=transcription,
                      reduction_status=str(reducer.OUT / 'live' / song / 'duration_priority_status.json'),
                      notes_out=reduced['notes_out'],
                      max_simultaneous_notes=reduced['max_simultaneous_notes'],
                      final_midi=str(final_path), final_sha256=sha256(final_path))
    except Exception as exc:
        record.update(status='failed', error=f'{type(exc).__name__}: {exc}',
                      traceback=traceback.format_exc()[-6000:])
    record['elapsed_sec'] = round(time.monotonic() - started, 2)
    atomic_json(final_status, record)
    print(f"{song}: {record['status']} elapsed={record['elapsed_sec']}s", flush=True)
    if record['status'] != 'complete':
        raise SystemExit(1)


if __name__ == '__main__':
    main()
