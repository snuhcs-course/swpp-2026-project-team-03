"""GPU05 MIDI-only experiment: choose one of seven source instruments per bar."""
from __future__ import annotations

import argparse
import bisect
import copy
import csv
import json
import os
import sys
import traceback
from collections import Counter, defaultdict
from pathlib import Path

import pretty_midi

SOURCE = Path('/work/drum_sync_priority_20261125/transcription')
OUT = Path('/work/bar_instrument_priority_20261125')
MANIFEST = Path('/work/piano_other_20261123/manifest.tsv')
sys.path.insert(0, '/experiment')
import piano_other_duration_priority_20261125 as base

VARIANTS = ('global_repeat', 'global_local_repeat')


def source_for(index: int, manifest: list[list[str]]) -> tuple[str, str]:
    if index <= 70:
        folder, song, _ = manifest[index - 1]
        return folder, song
    return 'live', {71: 'L15', 72: 'P03', 73: 'P07'}[index]


def clean_by_program(aligned: pretty_midi.PrettyMIDI, coverage: dict[int, float]) -> tuple[list[base.Tagged], dict]:
    tagged = base.annotate_aligned(aligned, coverage)
    beat = 60.0 / float(aligned.get_tempo_changes()[1][0])
    cleaned = []
    duplicate_count = reattack_count = 0
    for program in base.ALLOWED:
        group = [item for item in tagged if item.program == program]
        merged, duplicates = base.merge_tracks(group)
        trimmed, reattacks = base.merge_reattacks_tagged(merged, beat / 4)
        cleaned.extend(trimmed)
        duplicate_count += duplicates
        reattack_count += reattacks
    repetitions = base.mark_repetitions(cleaned, beat)
    return cleaned, {'source_notes': len(tagged), 'duplicates_merged': duplicate_count,
                     'reattacks_merged': reattack_count,
                     'repeated_by_label': repetitions}


def segment_bars(aligned: pretty_midi.PrettyMIDI, tagged: list[base.Tagged]) -> tuple[list[float], dict]:
    end = aligned.get_end_time()
    downbeats = [float(t) for t in aligned.get_downbeats() if 0 < t < end]
    bounds = [0.0] + sorted(set(downbeats)) + [max(end + 1e-6, 1e-6)]
    bars: dict[int, dict[int, list[tuple[base.Tagged, bool]]]] = defaultdict(lambda: defaultdict(list))
    for item in tagged:
        start_bar = max(0, bisect.bisect_right(bounds, item.note.start) - 1)
        bar = start_bar
        while bar < len(bounds) - 1 and bounds[bar] < item.note.end:
            left = max(item.note.start, bounds[bar])
            right = min(item.note.end, bounds[bar + 1])
            if right > left + 1e-9:
                piece = copy.copy(item)
                piece.note = copy.copy(item.note)
                piece.note.start, piece.note.end = left, right
                bars[bar][item.program].append((piece, bar == start_bar))
            bar += 1
    return bounds, bars


def choose(bounds: list[float], bars: dict, coverage: dict[int, float], variant: str) -> tuple[list[base.Tagged], dict]:
    selected: list[base.Tagged] = []
    winners = Counter()
    bar_labels = {}
    bar_scores = {}
    for bar, by_program in sorted(bars.items()):
        length = max(bounds[bar + 1] - bounds[bar], 1e-9)
        scored = []
        for program, entries in by_program.items():
            notes = [item.note for item, _ in entries]
            local = base.union_seconds(notes) / length
            onsets = [item for item, starts_here in entries if starts_here]
            repeat = sum(item.repeated for item in onsets) / max(len(onsets), 1)
            global_fraction = coverage[program]
            if variant == 'global_repeat':
                score = global_fraction + 0.35 * repeat
            else:
                score = 0.6 * global_fraction + 0.4 * local + 0.35 * repeat
            scored.append((round(score, 9), round(local, 9), round(global_fraction, 9),
                           repeat, -program, program))
        winner = max(scored)[-1]
        winners[base.ALLOWED[winner]] += 1
        bar_labels[str(bar + 1)] = base.ALLOWED[winner]
        bar_scores[str(bar + 1)] = round(max(scored)[0], 6)
        selected.extend(item for item, _ in by_program[winner])
    return selected, {'bars_with_notes': len(bars), 'bars_by_label': dict(winners),
                      'bar_labels': bar_labels, 'bar_scores': bar_scores}


def render(aligned: pretty_midi.PrettyMIDI, selected: list[base.Tagged], out: Path) -> dict:
    # The first ablation must not mutate the shared candidate notes of the second.
    selected, reduction = base.reduce_notes(copy.deepcopy(selected))
    result = copy.deepcopy(aligned)
    track = pretty_midi.Instrument(program=0, name='One instrument per bar playable')
    track.notes = sorted((item.note for item in selected), key=lambda n: (n.start, n.pitch))
    result.instruments = [track]
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix('.tmp.mid')
    result.write(str(tmp))
    reread = pretty_midi.PrettyMIDI(str(tmp))
    if selected:
        if len(reread.instruments) != 1 or reread.instruments[0].program != 0:
            raise ValueError('Expected one GM0 keyboard track')
        audit = base.audit(reread.instruments[0])
    elif reread.instruments:
        raise ValueError('Unexpected nonempty track in blank MIDI')
    else:
        audit = {'notes_out': 0, 'max_simultaneous_notes': 0}
    os.replace(tmp, out)
    return {**reduction, **audit, 'output_sha256': base.sha256(out),
            'kept_by_label': dict(Counter(base.ALLOWED[item.program] for item in selected))}


def process(index: int, manifest: list[list[str]]) -> dict:
    folder, song = source_for(index, manifest)
    source = SOURCE / folder / song
    target = OUT / folder / song
    status = {'index': index, 'folder': folder, 'song': song, 'status': 'started'}
    try:
        source_status = json.loads((source / 'status.json').read_text(encoding='utf-8'))
        if source_status.get('status') != 'complete':
            raise ValueError('Drum-aligned source incomplete')
        raw_path, aligned_path = source / 'raw.mid', source / 'aligned.mid'
        raw = pretty_midi.PrettyMIDI(str(raw_path))
        aligned = pretty_midi.PrettyMIDI(str(aligned_path))
        coverage, coverage_stats = base.raw_coverage(raw, float(source_status['duration_sec']))
        cleaned, clean_stats = clean_by_program(aligned, coverage)
        bounds, bars = segment_bars(aligned, cleaned)
        status.update(raw_sha256=base.sha256(raw_path), aligned_sha256=base.sha256(aligned_path),
                      source_status_sha256=base.sha256(source / 'status.json'),
                      bars_total=len(bounds) - 1, coverage=coverage_stats,
                      cleaning=clean_stats, variants={})
        for variant in VARIANTS:
            chosen, bar_stats = choose(bounds, bars, coverage, variant)
            output = target / f'{variant}_one_instrument_per_bar.mid'
            result = render(aligned, chosen, output)
            status['variants'][variant] = {'output': str(output),
                                           'candidate_notes': len(chosen),
                                           **bar_stats, **result}
        a = status['variants']['global_repeat']['bar_labels']
        b = status['variants']['global_local_repeat']['bar_labels']
        status['bars_changed_by_local'] = sum(a.get(key) != b.get(key) for key in a.keys() | b.keys())
        status['status'] = 'complete'
    except Exception as exc:
        status['status'] = 'error'
        status['error'] = f'{type(exc).__name__}: {exc}'
        status['traceback'] = traceback.format_exc()
    base.atomic_json(target / 'status.json', status)
    return status


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=int, required=True)
    parser.add_argument('--end', type=int, required=True)
    args = parser.parse_args()
    with MANIFEST.open(encoding='utf-8', newline='') as stream:
        manifest = list(csv.reader(stream, delimiter='\t'))
    if len(manifest) != 70 or not (1 <= args.start <= args.end <= 73):
        raise ValueError('Expected 70-song manifest and range 1..73')
    failed = 0
    for index in range(args.start, args.end + 1):
        folder, song = source_for(index, manifest)
        status_path = OUT / folder / song / 'status.json'
        if status_path.is_file() and json.loads(status_path.read_text(encoding='utf-8')).get('status') == 'complete':
            print(f'{index}/73 {folder}/{song}: already complete', flush=True)
            continue
        record = process(index, manifest)
        failed += record['status'] != 'complete'
        print(f"{index}/73 {folder}/{song}: {record['status']} "
              f"changed_bars={record.get('bars_changed_by_local', 0)}", flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
