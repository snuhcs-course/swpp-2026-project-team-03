"""Second reduction: use piano in piano-bearing bars, synth in other bars.

Run on gpu05. Reuses the exact one-track merge and two-hand checks from
piano_other_playable_20261124.py. Existing song-level outputs stay intact.
"""
from __future__ import annotations

import argparse
import bisect
import copy
import csv
import json
import os
import sys
import traceback
from collections import defaultdict
from pathlib import Path

import pretty_midi

from piano_other_playable_20261124 import (
    ROOT, SOURCE, OUT, PIANO, SYNTH, atomic_json, audit,
    reduce_one, sha256, MERGE_CODE, PLAYABLE_CODE,
)


def select_by_bar(pm: pretty_midi.PrettyMIDI) -> tuple[list[pretty_midi.Instrument], dict]:
    end = pm.get_end_time()
    downbeats = [float(t) for t in pm.get_downbeats() if 0 < t < end]
    bounds = [0.0] + sorted(set(downbeats)) + [max(end + 1e-6, 1e-6)]
    segments: dict[tuple[int, int], list[pretty_midi.Note]] = defaultdict(list)
    piano_bars: set[int] = set()
    active_bars: set[int] = set()
    for track_index, track in enumerate(pm.instruments):
        for note in track.notes:
            bar = max(0, bisect.bisect_right(bounds, note.start) - 1)
            while bar < len(bounds) - 1 and bounds[bar] < note.end:
                left = max(note.start, bounds[bar])
                right = min(note.end, bounds[bar + 1])
                if right > left + 1e-9:
                    piece = copy.copy(note)
                    piece.start, piece.end = left, right
                    segments[(bar, track_index)].append(piece)
                    active_bars.add(bar)
                    if track.program in PIANO:
                        piano_bars.add(bar)
                bar += 1
    selected = []
    piano_notes = synth_notes = 0
    synth_bars: set[int] = set()
    for track_index, track in enumerate(pm.instruments):
        notes = []
        for bar in active_bars:
            if ((bar in piano_bars and track.program in PIANO)
                    or (bar not in piano_bars and track.program in SYNTH)):
                chosen = segments.get((bar, track_index), [])
                notes.extend(chosen)
                if track.program in PIANO:
                    piano_notes += len(chosen)
                else:
                    synth_notes += len(chosen)
                    if chosen:
                        synth_bars.add(bar)
        if notes:
            copy_track = pretty_midi.Instrument(program=track.program, name=track.name)
            copy_track.notes = sorted(notes, key=lambda n: (n.start, n.pitch))
            selected.append(copy_track)
    return selected, {'bars_total': len(bounds) - 1,
                      'bars_with_any_notes': len(active_bars),
                      'piano_bars': len(piano_bars),
                      'synth_fallback_bars': len(synth_bars),
                      'piano_segment_notes': piano_notes,
                      'synth_segment_notes': synth_notes}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=int, required=True)
    parser.add_argument('--end', type=int, required=True)
    args = parser.parse_args()
    with (ROOT / 'manifest.tsv').open(newline='', encoding='utf-8') as f:
        songs = list(csv.reader(f, delimiter='\t'))
    if len(songs) != 70 or not (1 <= args.start <= args.end <= 70):
        raise ValueError('Expected 70 songs and valid inclusive range')
    run = {'range': [args.start, args.end], 'merge_code_sha256': sha256(MERGE_CODE),
           'piano_playable_code_sha256': sha256(PLAYABLE_CODE), 'songs': []}
    for index in range(args.start, args.end + 1):
        folder, song_id, _ = songs[index - 1]
        src = SOURCE / folder / song_id / 'aligned.mid'
        dst = OUT / folder / song_id / 'piano_priority_by_bar_playable.mid'
        record = {'index': index, 'folder': folder, 'song_id': song_id,
                  'source': str(src), 'output': str(dst)}
        try:
            pm = pretty_midi.PrettyMIDI(str(src))
            if any(i.is_drum or i.program not in PIANO | SYNTH for i in pm.instruments):
                raise ValueError('Unexpected source instrument')
            selected, bars = select_by_bar(pm)
            reduced, stats = reduce_one(pm, selected, 'Piano priority by bar playable')
            dst.parent.mkdir(parents=True, exist_ok=True)
            tmp = dst.with_suffix('.tmp.mid')
            reduced.write(str(tmp))
            reread = pretty_midi.PrettyMIDI(str(tmp))
            if reduced.instruments[0].notes:
                if len(reread.instruments) != 1 or reread.instruments[0].program != 0:
                    raise ValueError('Expected one GM0 keyboard track')
                audit(reread.instruments[0])
            elif reread.instruments:
                raise ValueError('Empty output unexpectedly contains a track')
            os.replace(tmp, dst)
            record.update(status='ok', source_sha256=sha256(src),
                          output_sha256=sha256(dst), **bars, **stats)
        except Exception as exc:
            record.update(status='error', error=f'{type(exc).__name__}: {exc}',
                          traceback=traceback.format_exc())
        atomic_json(OUT / folder / song_id / 'bar_priority_status.json', record)
        run['songs'].append(record)
        print(f"{index}/70 {folder}/{song_id}: {record['status']}", flush=True)
    run['ok'] = sum(r['status'] == 'ok' for r in run['songs'])
    run['failed'] = len(run['songs']) - run['ok']
    atomic_json(OUT / f'bar_summary_{args.start}_{args.end}.json', run)
    if run['failed']:
        sys.exit(1)


if __name__ == '__main__':
    main()
