"""GPU05 MIDI-only correction: consensus notes and cross-label repeated motifs."""
from __future__ import annotations

import argparse
import copy
import csv
import json
import os
import sys
import traceback
from collections import Counter, defaultdict
from dataclasses import dataclass
from itertools import combinations
from pathlib import Path

import pretty_midi

SOURCE = Path('/work/drum_sync_priority_20261125/transcription')
OUT = Path('/work/bar_consensus_motif_20261125')
MANIFEST = Path('/work/piano_other_20261123/manifest.tsv')
sys.path.insert(0, '/experiment')
import piano_other_duration_priority_20261125 as base
import bar_base

VARIANTS = ('consensus', 'consensus_cross_motif')
CONSENSUS_TOLERANCE_SEC = 0.05
CONSENSUS_NOTE_BONUS = 1000.0
CROSS_MOTIF_BONUS = 0.35
MOTIF_TICKS_PER_BEAT = 12


@dataclass
class Scored(base.Tagged):
    consensus: bool = False
    cross_motif: bool = False

    @property
    def score(self) -> float:
        return (super().score + (CONSENSUS_NOTE_BONUS if self.consensus else 0.0)
                + (CROSS_MOTIF_BONUS if self.cross_motif else 0.0))


def event_key(bar: int, item: base.Tagged, bounds: list[float], beat: float) -> tuple[int, int]:
    tick = int(round((item.note.start - bounds[bar]) / beat * MOTIF_TICKS_PER_BEAT))
    return item.note.pitch, tick


def find_consensus(bars: dict) -> dict[int, list[tuple[list[base.Tagged], base.Tagged]]]:
    """Same-pitch onsets within 50ms, present under at least two labels in one bar."""
    found = {}
    for bar, by_program in bars.items():
        by_pitch = defaultdict(list)
        for program, entries in by_program.items():
            for item, starts_here in entries:
                if starts_here:
                    by_pitch[item.note.pitch].append(item)
        groups = []
        for items in by_pitch.values():
            items.sort(key=lambda x: x.note.start)
            cluster = []
            for item in items:
                if cluster and item.note.start - cluster[0].note.start > CONSENSUS_TOLERANCE_SEC:
                    if len({x.program for x in cluster}) >= 2:
                        representative = max(cluster, key=lambda x: (x.score, x.note.end, x.note.velocity))
                        groups.append((cluster, representative))
                    cluster = []
                cluster.append(item)
            if cluster and len({x.program for x in cluster}) >= 2:
                representative = max(cluster, key=lambda x: (x.score, x.note.end, x.note.velocity))
                groups.append((cluster, representative))
        found[bar] = groups
    return found


def find_cross_label_motifs(bounds: list[float], bars: dict, beat: float) -> set[tuple[int, int, tuple[int, int]]]:
    """Mark 3+ shared pitch/metrical-slot events at 2+ slots in different-label bars."""
    inverted = defaultdict(set)
    for bar, by_program in bars.items():
        for program, entries in by_program.items():
            keys = {event_key(bar, item, bounds, beat) for item, onset in entries if onset}
            for key in keys:
                inverted[key].add((bar, program))
    pair_matches = defaultdict(set)
    for key, located in inverted.items():
        if len(located) > 150:
            # A ubiquitous note/slot is not distinctive evidence of a riff.
            continue
        for first, second in combinations(sorted(located), 2):
            if first[0] != second[0] and first[1] != second[1]:
                pair_matches[(first, second)].add(key)
    marked = set()
    for (first, second), common in pair_matches.items():
        if len(common) >= 3 and len({slot for _, slot in common}) >= 2:
            marked.update((first[0], first[1], key) for key in common)
            marked.update((second[0], second[1], key) for key in common)
    return marked


def to_scored(item: base.Tagged, *, consensus: bool, cross_motif: bool) -> Scored:
    return Scored(note=copy.copy(item.note), program=item.program, track=item.track,
                  repeated=item.repeated, coverage=item.coverage, active=False,
                  consensus=consensus, cross_motif=cross_motif)


def choose(bounds: list[float], bars: dict, coverage: dict[int, float],
           consensus: dict, motifs: set, beat: float, variant: str) -> tuple[list[Scored], dict]:
    selected = []
    winners = Counter()
    primary_by_bar = {}
    consensus_by_bar = {}
    motif_by_bar = {}
    for bar, by_program in sorted(bars.items()):
        length = max(bounds[bar + 1] - bounds[bar], 1e-9)
        scored = []
        for program, entries in by_program.items():
            local = base.union_seconds([item.note for item, _ in entries]) / length
            onsets = [item for item, starts_here in entries if starts_here]
            repeated = sum(item.repeated for item in onsets) / max(len(onsets), 1)
            cross = sum((bar, program, event_key(bar, item, bounds, beat)) in motifs
                        for item in onsets) / max(len(onsets), 1)
            score = 0.6 * coverage[program] + 0.4 * local + 0.35 * repeated
            if variant == 'consensus_cross_motif':
                score += CROSS_MOTIF_BONUS * cross
            scored.append((round(score, 9), round(local, 9), round(coverage[program], 9),
                           -program, program))
        winner = max(scored)[-1]
        winners[base.ALLOWED[winner]] += 1
        primary_by_bar[str(bar + 1)] = base.ALLOWED[winner]
        shared = consensus.get(bar, [])
        ignore = {id(item) for group, _ in shared for item in group}
        for item, _ in by_program[winner]:
            if id(item) not in ignore:
                motif = (variant == 'consensus_cross_motif' and
                         (bar, item.program, event_key(bar, item, bounds, beat)) in motifs)
                selected.append(to_scored(item, consensus=False, cross_motif=motif))
        for _, representative in shared:
            motif = (variant == 'consensus_cross_motif' and
                     (bar, representative.program, event_key(bar, representative, bounds, beat)) in motifs)
            selected.append(to_scored(representative, consensus=True, cross_motif=motif))
        consensus_by_bar[str(bar + 1)] = len(shared)
        motif_by_bar[str(bar + 1)] = sum((bar, winner, event_key(bar, item, bounds, beat)) in motifs
                                          for item, starts_here in by_program[winner] if starts_here)
    return selected, {'bars_with_notes': len(bars), 'bars_by_primary_label': dict(winners),
                      'primary_by_bar': primary_by_bar, 'consensus_by_bar': consensus_by_bar,
                      'motif_onsets_by_bar': motif_by_bar}


def render(aligned: pretty_midi.PrettyMIDI, candidates: list[Scored], output: Path) -> dict:
    kept, reduction = base.reduce_notes(copy.deepcopy(candidates))
    midi = copy.deepcopy(aligned)
    track = pretty_midi.Instrument(program=0, name='Bar primary with consensus notes')
    track.notes = sorted((x.note for x in kept), key=lambda n: (n.start, n.pitch))
    midi.instruments = [track]
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix('.tmp.mid')
    midi.write(str(temp))
    reread = pretty_midi.PrettyMIDI(str(temp))
    if kept:
        if len(reread.instruments) != 1 or reread.instruments[0].program != 0:
            raise ValueError('Expected one GM0 track')
        audit = base.audit(reread.instruments[0])
    elif reread.instruments:
        raise ValueError('Unexpected nonempty track')
    else:
        audit = {'notes_out': 0, 'max_simultaneous_notes': 0}
    os.replace(temp, output)
    return {**reduction, **audit, 'output_sha256': base.sha256(output),
            'consensus_candidates': sum(x.consensus for x in candidates),
            'consensus_kept': sum(x.consensus for x in kept),
            'cross_motif_candidates': sum(x.cross_motif for x in candidates),
            'cross_motif_kept': sum(x.cross_motif for x in kept),
            'kept_by_source_label': dict(Counter(base.ALLOWED[x.program] for x in kept))}


def process(index: int, manifest: list[list[str]]) -> dict:
    folder, song = bar_base.source_for(index, manifest)
    source = SOURCE / folder / song
    target = OUT / folder / song
    status = {'index': index, 'folder': folder, 'song': song, 'status': 'started'}
    try:
        source_status = json.loads((source / 'status.json').read_text(encoding='utf-8'))
        if source_status.get('status') != 'complete':
            raise ValueError('Drum-corrected source incomplete')
        raw_path, aligned_path = source / 'raw.mid', source / 'aligned.mid'
        raw = pretty_midi.PrettyMIDI(str(raw_path))
        aligned = pretty_midi.PrettyMIDI(str(aligned_path))
        coverage, coverage_stats = base.raw_coverage(raw, float(source_status['duration_sec']))
        cleaned, clean_stats = bar_base.clean_by_program(aligned, coverage)
        bounds, bars = bar_base.segment_bars(aligned, cleaned)
        beat = 60.0 / float(aligned.get_tempo_changes()[1][0])
        shared = find_consensus(bars)
        motifs = find_cross_label_motifs(bounds, bars, beat)
        status.update(raw_sha256=base.sha256(raw_path), aligned_sha256=base.sha256(aligned_path),
                      source_status_sha256=base.sha256(source / 'status.json'),
                      bars_total=len(bounds) - 1, coverage=coverage_stats,
                      cleaning=clean_stats, consensus_events=sum(map(len, shared.values())),
                      cross_label_motif_events=len(motifs), variants={})
        for variant in VARIANTS:
            chosen, chosen_stats = choose(bounds, bars, coverage, shared, motifs, beat, variant)
            output = target / f'{variant}_playable.mid'
            status['variants'][variant] = {'output': str(output), 'candidate_notes': len(chosen),
                                           **chosen_stats, **render(aligned, chosen, output)}
        left = status['variants']['consensus']['primary_by_bar']
        right = status['variants']['consensus_cross_motif']['primary_by_bar']
        status['bars_changed_by_motif'] = sum(left.get(key) != right.get(key)
                                               for key in left.keys() | right.keys())
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
        folder, song = bar_base.source_for(index, manifest)
        path = OUT / folder / song / 'status.json'
        if path.is_file() and json.loads(path.read_text(encoding='utf-8')).get('status') == 'complete':
            print(f'{index}/73 {folder}/{song}: already complete', flush=True)
            continue
        result = process(index, manifest)
        failed += result['status'] != 'complete'
        print(f"{index}/73 {folder}/{song}: {result['status']} "
              f"consensus={result.get('consensus_events', 0)} "
              f"motif={result.get('cross_label_motif_events', 0)}", flush=True)
    if failed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
