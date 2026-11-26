"""GPU05 only: add real drum-MIDI sync to the existing duration/repetition experiment."""
from __future__ import annotations

import argparse
import copy
import csv
import gc
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

ROOT = Path('/work/drum_sync_priority_20261125')
OLD70 = Path('/work/piano_other_muscriptor_20261124')
OLDLIVE = Path('/work/live_duration_priority_20261125/transcription/live')
INPUT70 = Path('/work/piano_other_20261123')
INPUTLIVE = Path('/work/live_duration_priority_20261125/input')
PYTHON = Path('/data/rocky-unified/.venv/bin/python')
SEPARATE = Path('/data/pipeline/separate_bs_roformer.py')
MODEL = Path('/data/model/model.safetensors')
BEAT = Path('/data/cache/torch/hub/checkpoints/beat_this-final0.ckpt')
sys.path[:0] = ['/data/pipeline', '/data/rocky-unified/ml/beat_align', '/experiment']
from rule_gates import GateConfig, gate_stem
from align import align_midi, detect_beats, save_beats
import piano_other_duration_priority_20261125 as reducer


def atomic_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)


def family(inst: pretty_midi.Instrument) -> str | None:
    return 'drums' if inst.is_drum else None


def transcribe_drums(wav: Path, raw: Path) -> None:
    from muscriptor.transcription_model import TranscriptionModel
    from muscriptor.utils.midi import ExportOptions
    model = TranscriptionModel.load_model(weights_path=str(MODEL), device='cuda', dtype=None)
    events = list(model.transcribe(wav, use_sampling=False, temperature=1.0,
                                   cfg_coef=1.0, instruments=['drums'], batch_size=None,
                                   no_eos_is_ok=True, beam_size=1, prelude_forcing=True))
    data = model.events_to_midi_bytes(iter(events), beat_grid=None, export=ExportOptions())
    raw.write_bytes(data)
    del model, events, data
    gc.collect()
    midi = pretty_midi.PrettyMIDI(str(raw))
    if any(i.notes and not i.is_drum for i in midi.instruments):
        raise ValueError('MuScriptor drums output contains non-drum note tracks')


def source_for(index: int, manifest: list[list[str]]) -> tuple[str, str, Path, Path]:
    if index <= 70:
        folder, song, ext = manifest[index - 1]
        return folder, song, INPUT70 / 'inputs' / folder / (song + ext), OLD70 / folder / song
    song = {71: 'L15', 72: 'P03', 73: 'P07'}[index]
    return 'live', song, INPUTLIVE / (song + '.wav'), OLDLIVE / song


def safe_cleanup(path: Path) -> None:
    if not path.resolve().is_relative_to((ROOT / 'temporary').resolve()):
        raise ValueError('Unsafe temporary cleanup path')
    if path.exists():
        shutil.rmtree(path)


def process(index: int, manifest: list[list[str]]) -> dict:
    folder, song, audio, old = source_for(index, manifest)
    work = ROOT / 'temporary' / f'{index:02d}'
    target = ROOT / 'results' / folder / song
    old_status = json.loads((old / 'status.json').read_text(encoding='utf-8'))
    if old_status.get('status') != 'complete':
        raise ValueError('Old seven-label transcription not complete')
    if not audio.is_file() or not (old / 'raw.mid').is_file() or not (old / 'gated.mid').is_file():
        raise FileNotFoundError('Missing original audio or seven-label MIDI')
    target.mkdir(parents=True, exist_ok=True)
    safe_cleanup(work)
    work.mkdir(parents=True)
    started = time.monotonic()
    report = {'index': index, 'folder': folder, 'song': song, 'status': 'started',
              'audio': str(audio), 'original_transcription': str(old),
              'beat_audio': 'BS-RoFormer no_vocals.wav',
              'alignment': 'operational align_midi with gated drum MIDI, drum_sync=True'}
    try:
        stems = work / 'stems'
        stems.mkdir()
        with (target / 'separation.log').open('w', encoding='utf-8') as log:
            subprocess.run([str(PYTHON), str(SEPARATE), str(audio), str(stems),
                            '--models-dir', '/data/bsrofo/models',
                            '--lib-dir', '/data/bsrofo/pylib'], stdout=log,
                           stderr=subprocess.STDOUT, check=True)
        drum_wav, no_vocals = stems / 'drums.wav', stems / 'no_vocals.wav'
        for path in (drum_wav, no_vocals):
            if not path.is_file() or sf.info(str(path)).duration <= 0:
                raise ValueError(f'Missing separated audio: {path.name}')
        report['duration_sec'] = round(sf.info(str(no_vocals)).duration, 3)
        raw_drum = target / 'drums_raw.mid'
        gated_drum = target / 'drums_gated.mid'
        transcribe_drums(drum_wav, raw_drum)
        gate = gate_stem(raw_drum, drum_wav, 'drums', gated_drum,
                         GateConfig(), family, declared=False,
                         original_unknown=True, duration_sec=report['duration_sec'])
        report['drum_gate'] = gate
        drum_pm = pretty_midi.PrettyMIDI(str(gated_drum))
        drum_tracks = [copy.deepcopy(i) for i in drum_pm.instruments if i.is_drum]
        drum_notes = sum(len(i.notes) for i in drum_tracks)
        report['gated_drum_notes'] = drum_notes
        if drum_notes == 0:
            report['drum_sync_limitation'] = 'No gated drum notes; timing correction has no drum reference'
        combined = pretty_midi.PrettyMIDI(str(old / 'gated.mid'))
        reducer.validate_source(combined)
        combined.instruments.extend(drum_tracks)
        combined_path = target / 'seven_labels_plus_drums.mid'
        combined.write(str(combined_path))
        beats, downbeats = detect_beats(no_vocals, device='cuda', checkpoint=str(BEAT))
        if len(beats) < 2:
            raise ValueError('Beat This! returned fewer than two beats')
        save_beats(target / 'beats.json', beats, downbeats)
        with_drums = target / 'aligned_with_drums.mid'
        result = align_midi(combined_path, with_drums, beats=beats,
                            downbeats=downbeats, drum_sync=True)
        sync = result.drum_sync
        report['beat_count'] = len(beats)
        report['downbeat_count'] = len(downbeats)
        report['drum_sync'] = {'drum_notes': sync.drum_notes,
                               'moved_notes': sync.moved_notes,
                               'max_shift_sec': sync.max_shift,
                               'grid_kept': sync.grid_kept}
        if sync.drum_notes != drum_notes:
            raise ValueError('Drum sync did not see the gated drum track')
        aligned = pretty_midi.PrettyMIDI(str(with_drums))
        aligned.instruments = [i for i in aligned.instruments if not i.is_drum]
        reducer.validate_source(aligned)
        transcript = ROOT / 'transcription' / folder / song
        transcript.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old / 'raw.mid', transcript / 'raw.mid')
        aligned.write(str(transcript / 'aligned.mid'))
        from hashlib import sha256
        atomic_json(transcript / 'status.json', {
            'status': 'complete', 'duration_sec': old_status['duration_sec'],
            'original_status': str(old / 'status.json'),
            'original_status_sha256': sha256((old / 'status.json').read_bytes()).hexdigest(),
            'raw_sha256': sha256((transcript / 'raw.mid').read_bytes()).hexdigest(),
            'aligned_sha256': sha256((transcript / 'aligned.mid').read_bytes()).hexdigest(),
            'drum_sync': report['drum_sync'], 'beat_audio': report['beat_audio']})
        reducer.SOURCE = ROOT / 'transcription'
        reducer.OUT = ROOT / 'reduced'
        reduced = reducer.run_song(index, folder, song)
        if reduced['status'] != 'ok':
            raise ValueError(f"Reducer failed: {reduced.get('error')}")
        final = ROOT / 'reduced' / folder / song / 'duration_repeat_priority_playable.mid'
        report['final_sha256'] = sha256(final.read_bytes()).hexdigest()
        report['final_notes'] = reduced['notes_out']
        report['max_simultaneous_notes'] = reduced['max_simultaneous_notes']
        report['elapsed_sec'] = round(time.monotonic() - started, 1)
        report['status'] = 'complete'
    except Exception as exc:
        report['status'] = 'error'
        report['error'] = f'{type(exc).__name__}: {exc}'
        report['traceback'] = traceback.format_exc()
    finally:
        atomic_json(target / 'status.json', report)
        safe_cleanup(work)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=int, required=True)
    parser.add_argument('--end', type=int, required=True)
    args = parser.parse_args()
    with (INPUT70 / 'manifest.tsv').open(encoding='utf-8', newline='') as stream:
        manifest = list(csv.reader(stream, delimiter='\t'))
    if len(manifest) != 70 or not (1 <= args.start <= args.end <= 73):
        raise ValueError('Expected 70-song manifest and range 1..73')
    for index in range(args.start, args.end + 1):
        folder, song, _, _ = source_for(index, manifest)
        status = ROOT / 'results' / folder / song / 'status.json'
        if status.is_file() and json.loads(status.read_text(encoding='utf-8')).get('status') == 'complete':
            print(f'{index}/73 {folder}/{song}: already complete', flush=True)
            continue
        try:
            record = process(index, manifest)
            print(f"{index}/73 {folder}/{song}: {record['status']} "
                  f"drum={record.get('drum_sync', {}).get('drum_notes', 0)} "
                  f"moved={record.get('drum_sync', {}).get('moved_notes', 0)}", flush=True)
        except Exception:
            print(f'{index}/73 {folder}/{song}: fatal\n{traceback.format_exc()}', flush=True)


if __name__ == '__main__':
    main()
