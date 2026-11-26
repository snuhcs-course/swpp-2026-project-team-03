"""GPU05 MIDI-only core experiment: five-bar coverage and at most two labels/bar."""
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
from dataclasses import dataclass
from pathlib import Path

import pretty_midi

SOURCE = Path('/work/drum_sync_priority_20261125/transcription')
OUT = Path('/work/core_local_window_20261126')
MANIFEST = Path('/experiment/core_manifest.tsv')
sys.path.insert(0, '/experiment')
import piano_other_duration_priority_20261125 as base
import bar_base

NEIGHBOR_BARS = 2
GLOBAL_WEIGHT = 0.6
LOCAL_WEIGHT = 0.4
REPEAT_WEIGHT = 0.35


@dataclass
class WindowTagged(base.Tagged):
    local_coverage: float = 0.0
    use_local: bool = False
    bar_index: int = 0

    @property
    def score(self) -> float:
        duration = ((GLOBAL_WEIGHT * self.coverage + LOCAL_WEIGHT * self.local_coverage)
                    if self.use_local else self.coverage)
        return 0.05 + duration + REPEAT_WEIGHT * self.repeated + 0.005 * self.active


def bar_at(bounds: list[float], time: float) -> int:
    return min(len(bounds) - 2, max(0, bisect.bisect_right(bounds, time) - 1))


def window_coverage(bounds: list[float], bars: dict) -> dict[int, dict[int, float]]:
    """Union of sounding time within current bar +/- two bars, divided by window length."""
    out = {}
    for bar in bars:
        first = max(0, bar - NEIGHBOR_BARS)
        last = min(len(bounds) - 1, bar + NEIGHBOR_BARS + 1)
        duration = max(bounds[last] - bounds[first], 1e-9)
        by_program = defaultdict(list)
        for near in range(first, last):
            for program, entries in bars.get(near, {}).items():
                by_program[program].extend(item.note for item, _ in entries)
        out[bar] = {program: base.union_seconds(by_program[program]) / duration
                    for program in base.ALLOWED}
    return out


def tagged(item: base.Tagged, bar: int, local: dict, use_local: bool) -> WindowTagged:
    return WindowTagged(note=copy.copy(item.note), program=item.program, track=item.track,
                        repeated=item.repeated, coverage=item.coverage, active=False,
                        local_coverage=local.get(bar, {}).get(item.program, 0.0),
                        use_local=use_local, bar_index=bar)


def refresh(notes: list[WindowTagged], bounds: list[float], local: dict,
            use_local: bool, fixed_bar: int | None = None) -> None:
    for item in notes:
        bar = fixed_bar if fixed_bar is not None else bar_at(bounds, item.note.start)
        item.local_coverage = local.get(bar, {}).get(item.program, 0.0)
        item.use_local = use_local
        item.bar_index = bar


def build_all(aligned: pretty_midi.PrettyMIDI, coverage: dict, bounds: list[float],
              local: dict, beat: float) -> tuple[list[WindowTagged], dict]:
    original = base.annotate_aligned(aligned, coverage)
    items = [tagged(item, bar_at(bounds, item.note.start), local, True) for item in original]
    merged, duplicates = base.merge_tracks(items)
    refresh(merged, bounds, local, True)
    cleaned, reattacks = base.merge_reattacks_tagged(merged, beat / 4)
    refresh(cleaned, bounds, local, True)
    repetitions = base.mark_repetitions(cleaned, beat)
    return cleaned, {'source_notes': len(original), 'duplicates_merged': duplicates,
                     'reattacks_merged': reattacks, 'repeated_by_label': repetitions}


def build_two(bounds: list[float], bars: dict, coverage: dict, local: dict,
              beat: float, use_local: bool) -> tuple[list[WindowTagged], dict]:
    candidates = []
    choices = {}
    by_label = Counter()
    duplicates = reattacks = 0
    for bar, by_program in sorted(bars.items()):
        ranking = []
        for program, entries in by_program.items():
            onsets = [item for item, starts_here in entries if starts_here]
            repeated = sum(item.repeated for item in onsets) / max(len(onsets), 1)
            global_fraction = coverage[program]
            local_fraction = local.get(bar, {}).get(program, 0.0)
            duration = ((GLOBAL_WEIGHT * global_fraction + LOCAL_WEIGHT * local_fraction)
                        if use_local else global_fraction)
            score = duration + REPEAT_WEIGHT * repeated
            ranking.append((round(score, 9), round(local_fraction, 9),
                            round(global_fraction, 9), -program, program))
        chosen = [item[-1] for item in sorted(ranking, reverse=True)[:2]]
        if not (1 <= len(chosen) <= 2):
            raise ValueError('Expected one or two labels in active bar')
        choices[str(bar + 1)] = [base.ALLOWED[program] for program in chosen]
        by_label.update(choices[str(bar + 1)])
        selected = [tagged(item, bar, local, use_local)
                    for program in chosen for item, _ in by_program[program]]
        merged, duplicate_count = base.merge_tracks(selected)
        refresh(merged, bounds, local, use_local, fixed_bar=bar)
        cleaned, reattack_count = base.merge_reattacks_tagged(merged, beat / 4)
        refresh(cleaned, bounds, local, use_local, fixed_bar=bar)
        candidates.extend(cleaned)
        duplicates += duplicate_count
        reattacks += reattack_count
    repetitions = base.mark_repetitions(candidates, beat)
    return candidates, {'bars_with_notes': len(bars), 'chosen_labels_by_bar': choices,
                        'bars_selected_by_label': dict(by_label),
                        'duplicates_merged': duplicates, 'reattacks_merged': reattacks,
                        'repeated_by_label': repetitions}


def render(aligned: pretty_midi.PrettyMIDI, candidates: list[WindowTagged],
           output: Path) -> dict:
    kept, reduction = base.reduce_notes(copy.deepcopy(candidates))
    result = copy.deepcopy(aligned)
    track = pretty_midi.Instrument(program=0, name='Duration and repetition playable')
    track.notes = sorted((item.note for item in kept), key=lambda note: (note.start, note.pitch))
    result.instruments = [track]
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix('.tmp.mid')
    result.write(str(temporary))
    reread = pretty_midi.PrettyMIDI(str(temporary))
    if kept:
        if len(reread.instruments) != 1 or reread.instruments[0].program != 0:
            raise ValueError('Expected one GM0 keyboard track')
        audit = base.audit(reread.instruments[0])
    elif reread.instruments:
        raise ValueError('Unexpected nonempty track in blank MIDI')
    else:
        audit = {'notes_out': 0, 'max_simultaneous_notes': 0}
    os.replace(temporary, output)
    return {**reduction, **audit, 'output_sha256': base.sha256(output),
            'candidate_notes': len(candidates),
            'kept_by_source_label': dict(Counter(base.ALLOWED[item.program] for item in kept))}


def process(index: int, folder: str, song: str, title: str) -> dict:
    source = SOURCE / folder / song
    target = OUT / folder / song
    record = {'index': index, 'folder': folder, 'song': song,
              'source_title': title, 'status': 'started'}
    try:
        source_status = json.loads((source / 'status.json').read_text(encoding='utf-8'))
        if source_status.get('status') != 'complete':
            raise ValueError('Drum-corrected transcription incomplete')
        raw_path, aligned_path = source / 'raw.mid', source / 'aligned.mid'
        raw = pretty_midi.PrettyMIDI(str(raw_path))
        aligned = pretty_midi.PrettyMIDI(str(aligned_path))
        coverage, coverage_stats = base.raw_coverage(raw, float(source_status['duration_sec']))
        beat = 60.0 / float(aligned.get_tempo_changes()[1][0])
        clean_by_label, clean_stats = bar_base.clean_by_program(aligned, coverage)
        bounds, bars = bar_base.segment_bars(aligned, clean_by_label)
        local = window_coverage(bounds, bars)
        record.update(raw_sha256=base.sha256(raw_path), aligned_sha256=base.sha256(aligned_path),
                      source_status_sha256=base.sha256(source / 'status.json'),
                      bars_total=len(bounds) - 1, bars_with_notes=len(bars),
                      local_window_bars=NEIGHBOR_BARS,
                      local_source='aligned MIDI after gating and drum sync',
                      global_source='raw seven-label MIDI',
                      coverage=coverage_stats, per_label_cleaning=clean_stats, variants={})
        all_candidates, all_stats = build_all(aligned, coverage, bounds, local, beat)
        output = target / 'all_labels_local_playable.mid'
        record['variants']['all_labels_local'] = {
            **all_stats, **render(aligned, all_candidates, output), 'output': str(output)}
        for use_local, variant in ((False, 'two_labels_global'), (True, 'two_labels_local')):
            candidates, stats = build_two(bounds, bars, coverage, local, beat, use_local)
            output = target / f'{variant}_playable.mid'
            record['variants'][variant] = {
                **stats, **render(aligned, candidates, output), 'output': str(output)}
        first = record['variants']['two_labels_global']['chosen_labels_by_bar']
        second = record['variants']['two_labels_local']['chosen_labels_by_bar']
        record['bars_changed_by_local'] = sum(first.get(bar) != second.get(bar)
                                               for bar in first.keys() | second.keys())
        record['status'] = 'complete'
    except Exception as exc:
        record['status'] = 'error'
        record['error'] = f'{type(exc).__name__}: {exc}'
        record['traceback'] = traceback.format_exc()
    base.atomic_json(target / 'status.json', record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=int, required=True)
    parser.add_argument('--end', type=int, required=True)
    args = parser.parse_args()
    with MANIFEST.open(encoding='utf-8-sig', newline='') as stream:
        manifest = list(csv.reader(stream, delimiter='\t'))
    if len(manifest) != 24 or not (1 <= args.start <= args.end <= 24):
        raise ValueError('Expected core manifest of 24 songs and range 1..24')
    failed = 0
    for index in range(args.start, args.end + 1):
        folder, song, title = manifest[index - 1]
        status = OUT / folder / song / 'status.json'
        if status.is_file() and json.loads(status.read_text(encoding='utf-8')).get('status') == 'complete':
            print(f'{index}/24 {folder}/{song}: already complete', flush=True)
            continue
        result = process(index, folder, song, title)
        failed += result['status'] != 'complete'
        print(f"{index}/24 {folder}/{song}: {result['status']} "
              f"changed_bars={result.get('bars_changed_by_local', 0)}", flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
