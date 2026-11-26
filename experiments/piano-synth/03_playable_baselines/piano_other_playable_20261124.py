"""Two one-player keyboard reductions of the 70 beat-aligned piano+other MIDIs.

Execute on the gpu05/ferrari Kubernetes node. No audio transcription or model
inference is performed here. Source MIDIs are read only.
"""
from __future__ import annotations

import argparse
import copy
import csv
import hashlib
import json
import os
import sys
import traceback
from collections import defaultdict
from pathlib import Path

import pretty_midi

ROOT = Path('/work/piano_other_20261123')
SOURCE = Path('/work/piano_other_muscriptor_20261124')
OUT = Path('/work/piano_other_playable_20261124')
PLAYABLE_CODE = Path('/data/rocky-unified/ml/guitar_tab/piano_playable.py')
MERGE_CODE = Path('/data/pipeline/unified.py')
PIANO = {0, 2, 16}
SYNTH = {50, 80, 88, 61}
ALLOWED = PIANO | SYNTH
SAME_NOTE_WINDOW = 0.05

sys.path.insert(0, str(PLAYABLE_CODE.parent))
import piano_playable  # noqa: E402


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)


def merge_tracks(tracks: list[pretty_midi.Instrument], name: str) -> pretty_midi.Instrument:
    """Exact note merge from deployed /data/pipeline/unified.py, program=0."""
    events = sorted(((index, copy.copy(note)) for index, track in enumerate(tracks)
                     for note in track.notes),
                    key=lambda item: (item[1].pitch, item[1].start, -item[1].end))
    notes: list[pretty_midi.Note] = []
    sources: list[set[int]] = []
    for source, note in events:
        previous = notes[-1] if notes and notes[-1].pitch == note.pitch else None
        if (previous is not None and note.start - previous.start < SAME_NOTE_WINDOW
                and (source not in sources[-1] or note.start == previous.start)):
            previous.end = max(previous.end, note.end)
            previous.velocity = max(previous.velocity, note.velocity)
            sources[-1].add(source)
            continue
        if previous is not None and previous.end > note.start:
            previous.end = note.start
        notes.append(note)
        sources.append({source})
    merged = pretty_midi.Instrument(program=0, name=name)
    merged.notes = sorted(notes, key=lambda note: (note.start, note.pitch))
    return merged


def strict_active_limit(inst: pretty_midi.Instrument) -> dict:
    """Apply deployed hand_limit to sounding notes, including earlier held notes."""
    groups: dict[float, list[pretty_midi.Note]] = defaultdict(list)
    for note in inst.notes:
        groups[note.start].append(note)
    active: list[pretty_midi.Note] = []
    kept: list[pretty_midi.Note] = []
    dropped = truncated = reattacked = 0
    for t, incoming in sorted(groups.items()):
        active = [n for n in active if n.end > t + 1e-9]
        incoming_pitches = {n.pitch for n in incoming}
        for old in active:
            if old.pitch in incoming_pitches:
                old.end = t
                reattacked += 1
        active = [n for n in active if n.end > t + 1e-9]
        allowed = set(piano_playable.hand_limit(
            [n.pitch for n in active] + [n.pitch for n in incoming]))
        for old in active:
            if old.pitch not in allowed:
                old.end = t
                truncated += 1
        active = [n for n in active if n.end > t + 1e-9]
        for new in incoming:
            if new.pitch in allowed:
                kept.append(new)
                active.append(new)
            else:
                dropped += 1
    inst.notes = [n for n in kept if n.end > n.start + 1e-9]
    inst.notes.sort(key=lambda n: (n.start, n.pitch))
    return {'active_dropped': dropped, 'active_truncated': truncated,
            'active_reattacked': reattacked}


def audit(inst: pretty_midi.Instrument) -> dict:
    events = []
    for n in inst.notes:
        if not 0 <= n.pitch <= 127 or n.end <= n.start:
            raise ValueError('Invalid output note')
        events.append((n.start, 1, n.pitch))
        events.append((n.end, -1, n.pitch))
    active: dict[int, int] = defaultdict(int)
    maximum = 0
    by_time: dict[float, list[tuple[int, int]]] = defaultdict(list)
    for t, direction, pitch in events:
        by_time[t].append((direction, pitch))
    for t, changes in sorted(by_time.items()):
        for direction, pitch in sorted(changes):
            active[pitch] += direction
        if any(count < 0 or count > 1 for count in active.values()):
            raise ValueError(f'Overlapping same pitch at {t}')
        pitches = [p for p, count in active.items() if count]
        maximum = max(maximum, len(pitches))
        if len(pitches) > 10 or set(pitches) != set(piano_playable.hand_limit(pitches)):
            raise ValueError(f'Two-hand rule failed at {t}')
    if any(active.values()):
        raise ValueError('Unclosed active notes')
    return {'max_simultaneous_notes': maximum, 'notes_out': len(inst.notes)}


def reduce_one(source: pretty_midi.PrettyMIDI, selected: list, name: str) -> tuple[pretty_midi.PrettyMIDI, dict]:
    out = copy.deepcopy(source)
    merged = merge_tracks(selected, name)
    merge_count = sum(len(i.notes) for i in selected) - len(merged.notes)
    out.instruments = [merged]
    out, stats = piano_playable.process(out)
    strict = strict_active_limit(out.instruments[0])
    verified = audit(out.instruments[0])
    return out, {'selected_tracks': len(selected),
                 'selected_notes': sum(len(i.notes) for i in selected),
                 'merge_removed': merge_count, **stats, **strict, **verified}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=int, required=True)
    parser.add_argument('--end', type=int, required=True)
    parser.add_argument('--only', help='Comma-separated 1-based song indexes to retry')
    args = parser.parse_args()
    with (ROOT / 'manifest.tsv').open(newline='', encoding='utf-8') as f:
        songs = list(csv.reader(f, delimiter='\t'))
    if len(songs) != 70 or not (1 <= args.start <= args.end <= 70):
        raise ValueError('Expected 70 songs and valid inclusive range')
    indexes = ([int(x) for x in args.only.split(',')]
               if args.only else list(range(args.start, args.end + 1)))
    if not indexes or any(x < args.start or x > args.end for x in indexes) or len(set(indexes)) != len(indexes):
        raise ValueError('Invalid --only indexes')
    run = {'range': [args.start, args.end], 'merge_code_sha256': sha256(MERGE_CODE),
           'piano_playable_code_sha256': sha256(PLAYABLE_CODE), 'songs': []}
    for index in indexes:
        folder, song_id, _ = songs[index - 1]
        src = SOURCE / folder / song_id / 'aligned.mid'
        target = OUT / folder / song_id
        record = {'index': index, 'folder': folder, 'song_id': song_id,
                  'source': str(src)}
        try:
            if not src.is_file():
                raise FileNotFoundError(src)
            pm = pretty_midi.PrettyMIDI(str(src))
            if any(i.is_drum or i.program not in ALLOWED for i in pm.instruments):
                raise ValueError('Unexpected source instrument')
            all_tracks = [i for i in pm.instruments if i.notes]
            piano_tracks = [i for i in all_tracks if i.program in PIANO]
            synth_tracks = [i for i in all_tracks if i.program in SYNTH]
            priority_tracks = piano_tracks if piano_tracks else synth_tracks
            branch = 'piano' if piano_tracks else ('synth' if synth_tracks else 'empty')
            all_out, all_stats = reduce_one(pm, all_tracks, 'All merged playable')
            priority_out, priority_stats = reduce_one(pm, priority_tracks, 'Piano priority playable')
            target.mkdir(parents=True, exist_ok=True)
            paths = [target / 'all_merged_playable.mid', target / 'piano_priority_playable.mid']
            for midi, path in zip((all_out, priority_out), paths):
                tmp = path.with_suffix('.tmp.mid')
                midi.write(str(tmp))
                # Re-read the serialized artifact and verify its actual MIDI events.
                reread = pretty_midi.PrettyMIDI(str(tmp))
                if midi.instruments[0].notes:
                    if len(reread.instruments) != 1 or reread.instruments[0].program != 0:
                        raise ValueError('Output must have one GM0 keyboard track')
                    audit(reread.instruments[0])
                elif reread.instruments:
                    raise ValueError('Empty output unexpectedly contains a track')
                os.replace(tmp, path)
            record.update(status='ok', source_sha256=sha256(src), branch=branch,
                          input_notes=sum(len(i.notes) for i in pm.instruments),
                          all_merged=all_stats, piano_priority=priority_stats,
                          outputs={p.name: {'path': str(p), 'sha256': sha256(p)} for p in paths})
        except Exception as exc:
            record.update(status='error', error=f'{type(exc).__name__}: {exc}',
                          traceback=traceback.format_exc())
        atomic_json(target / 'status.json', record)
        run['songs'].append(record)
        print(f"{index}/70 {folder}/{song_id}: {record['status']}", flush=True)
    run['ok'] = sum(s['status'] == 'ok' for s in run['songs'])
    run['failed'] = len(run['songs']) - run['ok']
    suffix = '_retry' if args.only else ''
    atomic_json(OUT / f'summary_{args.start}_{args.end}{suffix}.json', run)
    if run['failed']:
        sys.exit(1)


if __name__ == '__main__':
    main()
