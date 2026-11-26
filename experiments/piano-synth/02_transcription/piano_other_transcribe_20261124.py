"""Transcribe 70 sample-aligned piano+other stems on gpu05 without ROCKY.

Inputs live on the rocky-work PVC. Outputs are isolated under OUT. This is a
development experiment, not a deployment or an independent model evaluation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import sys
import time
import traceback
from pathlib import Path

import pretty_midi
import soundfile as sf

ROOT = Path('/work/piano_other_20261123')
OUT = Path('/work/piano_other_muscriptor_20261124')
PIPELINE = Path('/data/pipeline')
BEAT_ALIGN = Path('/data/rocky-unified/ml/beat_align')
MODEL = Path('/data/model/model.safetensors')
BEAT_CHECKPOINT = Path('/data/cache/torch/hub/checkpoints/beat_this-final0.ckpt')
INSTRUMENTS = ('acoustic_piano', 'electric_piano', 'organ',
               'synth_strings', 'synth_lead', 'synth_pad', 'brass_section')
PROGRAMS = {'acoustic_piano': 0, 'electric_piano': 2, 'organ': 16,
            'synth_strings': 50, 'synth_lead': 80,
            'synth_pad': 88, 'brass_section': 61}

sys.path.insert(0, str(PIPELINE))
sys.path.insert(0, str(BEAT_ALIGN))
from rule_gates import GateConfig, gate_stem  # noqa: E402
from align import align_midi, detect_beats, save_beats  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)


def valid_midi(path: Path) -> bool:
    try:
        pretty_midi.PrettyMIDI(str(path))
        return True
    except (OSError, ValueError, EOFError):
        return False


def tracks(path: Path) -> list[dict]:
    midi = pretty_midi.PrettyMIDI(str(path))
    return [{'name': i.name, 'program': int(i.program), 'notes': len(i.notes)}
            for i in midi.instruments]


def family(inst: pretty_midi.Instrument) -> str | None:
    return 'piano_other' if not inst.is_drum and inst.program in PROGRAMS.values() else None


def ensure_labels(path: Path) -> None:
    for item in tracks(path):
        if item['program'] not in PROGRAMS.values():
            raise ValueError(f"unexpected program {item['program']}")
        expected = next(k for k, v in PROGRAMS.items() if v == item['program'])
        # MuScriptor writes human-readable MIDI track names with spaces. Keep
        # those names untouched; only normalize for this validation.
        if item['name'].replace(' ', '_') != expected:
            raise ValueError(f"unexpected label {item['name']!r} for {expected}")


def load_items() -> list[tuple[str, str, str]]:
    with (ROOT / 'manifest.tsv').open(newline='', encoding='utf-8') as f:
        items = [tuple(row) for row in csv.reader(f, delimiter='\t')]
    if len(items) != 70 or any(len(row) != 3 for row in items):
        raise ValueError(f'Expected 70 three-column manifest rows, got {len(items)}')
    if len({(folder, file_id) for folder, file_id, _ in items}) != 70:
        raise ValueError('Duplicate input IDs')
    for folder, file_id, ext in items:
        if folder not in {'synth', 'synth_piano', 'piano'} or not file_id or '/' in file_id:
            raise ValueError('Invalid manifest entry')
        if not (ROOT / 'inputs' / folder / f'{file_id}{ext}').is_file():
            raise FileNotFoundError('original audio missing')
        piano = ROOT / 'results' / folder / f'{file_id}__piano.wav'
        other = ROOT / 'results' / folder / f'{file_id}__other.wav'
        if not piano.is_file() or not other.is_file():
            raise FileNotFoundError('piano or other stem missing')
        a, b = sf.info(str(piano)), sf.info(str(other))
        if (a.frames, a.samplerate, a.channels) != (b.frames, b.samplerate, b.channels):
            raise ValueError(f'piano/other WAV grid mismatch for {folder}/{file_id}')
        if a.frames <= 0 or a.samplerate <= 0 or a.channels <= 0:
            raise ValueError(f'unexpected stem WAV format for {folder}/{file_id}')
    return items


def combine_wavs(folder: str, file_id: str) -> tuple[Path, dict]:
    piano = ROOT / 'results' / folder / f'{file_id}__piano.wav'
    other = ROOT / 'results' / folder / f'{file_id}__other.wav'
    target = OUT / 'combined_wav' / folder / f'{file_id}__piano_other.wav'
    info = sf.info(str(piano))
    if target.is_file():
        existing = sf.info(str(target))
        if (existing.frames, existing.samplerate, existing.channels) == (info.frames, info.samplerate, info.channels):
            return target, {'reused': True, 'frames': info.frames, 'samplerate': info.samplerate,
                            'channels': info.channels}
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix('.wav.tmp')
    peak = 0.0
    above_full_scale = 0
    with sf.SoundFile(str(piano)) as p, sf.SoundFile(str(other)) as o, sf.SoundFile(
            str(temp), mode='w', samplerate=info.samplerate, channels=info.channels,
            format='WAV', subtype='FLOAT') as out:
        while True:
            x = p.read(65536, dtype='float32', always_2d=True)
            y = o.read(65536, dtype='float32', always_2d=True)
            if x.shape != y.shape:
                raise ValueError('Stem block shapes differ')
            if not len(x):
                break
            z = x + y
            peak = max(peak, float(abs(z).max()))
            above_full_scale += int((abs(z) > 1.0).sum())
            out.write(z)
    os.replace(temp, target)
    return target, {'reused': False, 'frames': info.frames, 'samplerate': info.samplerate,
                    'channels': info.channels, 'peak': round(peak, 5),
                    'samples_above_1': above_full_scale}


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--limit', type=int, default=70)
    p.add_argument('--start', type=int, default=1)
    p.add_argument('--end', type=int, default=70)
    args = p.parse_args()
    if not 1 <= args.start <= args.end <= 70:
        p.error('Require 1 <= --start <= --end <= 70')
    items = load_items()[args.start - 1:args.end][:args.limit]
    OUT.mkdir(parents=True, exist_ok=True)
    atomic_json(OUT / f'experiment_{args.start}_{args.end}.json', {
        'input': 'Sample-aligned sums of Iteration 4 piano and other WAV stems; original audio for Beat This',
        'output': 'combined_wav and raw.mid, gated.mid, aligned.mid, beats.json, status.json per song',
        'instruments': list(INSTRUMENTS), 'programs': PROGRAMS,
        'gate': GateConfig().as_dict(),
        'gate_mode': {'declared': False, 'original_unknown': True},
        'beat_source_difference': 'Original audio; current ROCKY full pipeline uses no_vocals mix',
        'model_sha256': sha256(MODEL),
        'beat_checkpoint_sha256': sha256(BEAT_CHECKPOINT),
        'script_sha256': sha256(Path(__file__)),
        'pipeline_gate_sha256': sha256(PIPELINE / 'rule_gates.py'),
        'beat_align_sha256': sha256(BEAT_ALIGN / 'align.py'),
        'transcription_helper_sha256': sha256(PIPELINE / 'transcribe_with_progress.py'),
        'total_manifest_songs': 70,
    })
    from muscriptor.transcription_model import TranscriptionModel
    from muscriptor.utils.midi import ExportOptions
    model = None
    failures = 0
    for number, (folder, file_id, ext) in enumerate(items, 1):
        source = ROOT / 'inputs' / folder / f'{file_id}{ext}'
        dest = OUT / folder / file_id
        dest.mkdir(parents=True, exist_ok=True)
        raw, gated, aligned = (dest / name for name in ('raw.mid', 'gated.mid', 'aligned.mid'))
        status_file = dest / 'status.json'
        started = time.monotonic()
        try:
            if valid_midi(aligned) and status_file.is_file():
                print(f'SKIP {number}/{len(items)} {folder}/{file_id}', flush=True)
                continue
            stem, combined = combine_wavs(folder, file_id)
            print(f'COMBINED {number}/{len(items)} {folder}/{file_id}', flush=True)
            if not valid_midi(raw):
                if model is None:
                    model = TranscriptionModel.load_model(weights_path=str(MODEL),
                                                          device='cuda', dtype=None)
                events = list(model.transcribe(
                    stem, use_sampling=False, temperature=1.0, cfg_coef=1.0,
                    instruments=list(INSTRUMENTS), batch_size=None,
                    no_eos_is_ok=True, beam_size=1, prelude_forcing=True))
                midi_bytes = model.events_to_midi_bytes(iter(events), beat_grid=None,
                                                         export=ExportOptions())
                temp = raw.with_suffix('.mid.tmp')
                temp.write_bytes(midi_bytes)
                os.replace(temp, raw)
            ensure_labels(raw)
            duration = float(sf.info(str(stem)).duration)
            gate = gate_stem(raw, stem, 'piano_other', gated, GateConfig(), family,
                             declared=False, original_unknown=True, duration_sec=duration)
            ensure_labels(gated)
            beats, downbeats = detect_beats(source, device='cuda',
                                            checkpoint=str(BEAT_CHECKPOINT))
            if len(beats) < 2:
                raise ValueError('Beat This returned fewer than two beats')
            save_beats(dest / 'beats.json', beats, downbeats)
            result = align_midi(gated, aligned, beats=beats, downbeats=downbeats,
                                drum_sync=True)
            ensure_labels(aligned)
            record = {
                'status': 'complete', 'folder': folder, 'id': file_id,
                'stem_sha256': sha256(stem), 'source_sha256': sha256(source),
                'piano_sha256': sha256(ROOT / 'results' / folder / f'{file_id}__piano.wav'),
                'other_sha256': sha256(ROOT / 'results' / folder / f'{file_id}__other.wav'),
                'combined': combined,
                'duration_sec': round(duration, 3),
                'raw': tracks(raw), 'gated': tracks(gated), 'aligned': tracks(aligned),
                'gate': gate, 'beats': len(beats), 'downbeats': len(downbeats),
                'alignment': {'bpm': result.bpm, 'meter': result.meter,
                              'note_count': result.note_count},
                'aligned_sha256': sha256(aligned),
            }
            print(f'DONE {number}/{len(items)} {folder}/{file_id} notes={result.note_count}', flush=True)
        except Exception as exc:
            failures += 1
            record = {'status': 'failed', 'folder': folder, 'id': file_id,
                      'error': f'{type(exc).__name__}: {exc}',
                      'traceback': traceback.format_exc()[-4000:]}
            print(f'FAILED {number}/{len(items)} {folder}/{file_id}: {exc}', flush=True)
        record['elapsed_sec'] = round(time.monotonic() - started, 2)
        atomic_json(status_file, record)
    records = [json.loads((OUT / folder / file_id / 'status.json').read_text(encoding='utf-8'))
               for folder, file_id, _ in items]
    by_folder = {}
    by_label = {label: {'raw': 0, 'gated': 0, 'aligned': 0} for label in INSTRUMENTS}
    for record in records:
        folder = record['folder']
        bucket = by_folder.setdefault(folder, {'complete': 0, 'failed': 0,
                                                'with_notes': 0, 'aligned_notes': 0})
        bucket[record['status']] += 1
        if record['status'] != 'complete':
            continue
        note_count = sum(t['notes'] for t in record['aligned'])
        bucket['aligned_notes'] += note_count
        bucket['with_notes'] += int(note_count > 0)
        for stage in ('raw', 'gated', 'aligned'):
            for track in record[stage]:
                label = track['name'].replace(' ', '_')
                by_label[label][stage] += track['notes']
    atomic_json(OUT / f'summary_{args.start}_{args.end}.json', {
        'songs': len(records), 'complete': sum(r['status'] == 'complete' for r in records),
        'failed': sum(r['status'] == 'failed' for r in records),
        'by_folder': by_folder, 'notes_by_label': by_label,
        'interpretation': 'Transcription output counts only; no reference-note accuracy or UAT claim',
    })
    print(f'BATCH_FINISHED total={len(items)} failed={failures}', flush=True)
    if failures:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
