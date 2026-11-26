"""Reduce the 70 existing piano+other transcriptions on gpu05, preserving dominant parts.

No model or audio processing occurs. Read raw.mid for whole-song instrument coverage,
and aligned.mid for notes. Write only to a new experiment directory on rocky-work.
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
from dataclasses import dataclass
from pathlib import Path

import pretty_midi

ROOT = Path('/work/piano_other_20261123')
SOURCE = Path('/work/piano_other_muscriptor_20261124')
OUT = Path('/work/piano_other_duration_priority_20261125')
PLAYABLE_CODE = Path('/data/rocky-unified/ml/guitar_tab/piano_playable.py')
ALLOWED = {0: 'acoustic_piano', 2: 'electric_piano', 16: 'organ',
           50: 'synth_strings', 80: 'synth_lead', 88: 'synth_pad',
           61: 'brass_section'}
SAME_NOTE_WINDOW = 0.05
REPEAT_BONUS = 0.35
BASE_NOTE_SCORE = 0.05

sys.path.insert(0, str(PLAYABLE_CODE.parent))
import piano_playable  # noqa: E402


@dataclass
class Tagged:
    note: pretty_midi.Note
    program: int
    track: int
    repeated: bool
    coverage: float
    active: bool = False

    @property
    def score(self) -> float:
        # A note from a part active for most of the song has greater priority.
        # The repetition bonus can rescue a recurring riff in a less active part.
        return BASE_NOTE_SCORE + self.coverage + REPEAT_BONUS * self.repeated + 0.005 * self.active


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(temp, path)


def validate_source(pm: pretty_midi.PrettyMIDI) -> None:
    for inst in pm.instruments:
        if inst.is_drum or inst.program not in ALLOWED:
            raise ValueError(f'Unexpected source instrument: {inst.program}')


def union_seconds(notes: list[pretty_midi.Note]) -> float:
    """Sounding-time union; simultaneous chord notes do not inflate part coverage."""
    total = 0.0
    left = right = 0.0
    for n in sorted(notes, key=lambda item: (item.start, item.end)):
        if n.end <= n.start:
            continue
        if n.start > right:
            total += max(0.0, right - left)
            left, right = n.start, n.end
        else:
            right = max(right, n.end)
    return total + max(0.0, right - left)


def raw_coverage(raw: pretty_midi.PrettyMIDI, duration: float) -> tuple[dict[int, float], dict]:
    validate_source(raw)
    duration = max(duration, raw.get_end_time())
    if duration <= 0:
        raise ValueError('Missing song duration')
    by_program: dict[int, list[pretty_midi.Note]] = defaultdict(list)
    for inst in raw.instruments:
        by_program[inst.program].extend(inst.notes)
    coverage = {p: union_seconds(by_program[p]) / duration for p in ALLOWED}
    stats = {ALLOWED[p]: {'raw_notes': len(by_program[p]),
                          'sounding_seconds': round(union_seconds(by_program[p]), 4),
                          'coverage_fraction': round(coverage[p], 6)}
             for p in ALLOWED}
    return coverage, {'raw_duration_seconds': round(duration, 4), 'instruments': stats}


def repeated_ids(notes: list[pretty_midi.Note], beat: float) -> set[int]:
    """Mark three same-pitch strikes within four beats after artifact merging.

    Each gap must be 0.375–2 beats. This excludes most consecutive 16th-note
    retrigger artifacts while recognizing repeated 8ths, quarters, and riffs.
    """
    by_pitch: dict[int, list[pretty_midi.Note]] = defaultdict(list)
    for n in notes:
        by_pitch[n.pitch].append(n)
    marked: set[int] = set()
    for group in by_pitch.values():
        group.sort(key=lambda n: n.start)
        for i in range(len(group) - 2):
            a, b, c = group[i:i + 3]
            gaps = (b.start - a.start, c.start - b.start)
            if all(0.375 * beat <= gap <= 2 * beat for gap in gaps) and c.start - a.start <= 4 * beat:
                marked.update((id(a), id(b), id(c)))
    return marked


def annotate_aligned(pm: pretty_midi.PrettyMIDI, coverage: dict[int, float]) -> list[Tagged]:
    validate_source(pm)
    tagged: list[Tagged] = []
    for index, inst in enumerate(pm.instruments):
        for note in inst.notes:
            tagged.append(Tagged(copy.copy(note), inst.program, index, False,
                                 coverage[inst.program]))
    return tagged


def merge_tracks(tagged: list[Tagged]) -> tuple[list[Tagged], int]:
    """Apply the prior experiment's 50 ms duplicate merge, retaining provenance."""
    ordered = sorted(tagged, key=lambda x: (x.note.pitch, x.note.start, -x.note.end))
    result: list[Tagged] = []
    sources: list[set[int]] = []
    merged = 0
    for item in ordered:
        item.note = copy.copy(item.note)
        previous = result[-1] if result and result[-1].note.pitch == item.note.pitch else None
        if (previous is not None and item.note.start - previous.note.start < SAME_NOTE_WINDOW
                and (item.track not in sources[-1] or item.note.start == previous.note.start)):
            previous.note.end = max(previous.note.end, item.note.end)
            previous.note.velocity = max(previous.note.velocity, item.note.velocity)
            if item.score > previous.score:
                previous.program = item.program
                previous.track = item.track
                previous.repeated = item.repeated
                previous.coverage = item.coverage
            sources[-1].add(item.track)
            merged += 1
            continue
        if previous is not None and previous.note.end > item.note.start:
            previous.note.end = item.note.start
        result.append(item)
        sources.append({item.track})
    return sorted(result, key=lambda x: (x.note.start, x.note.pitch)), merged


def merge_reattacks_tagged(tagged: list[Tagged], s16: float) -> tuple[list[Tagged], int]:
    """Deployed reattack rule on the single merged track, preserving the winning label."""
    by_pitch: dict[int, list[Tagged]] = defaultdict(list)
    for item in tagged:
        by_pitch[item.note.pitch].append(item)
    output: list[Tagged] = []
    merged = 0
    for group in by_pitch.values():
        group.sort(key=lambda x: x.note.start)
        ticks = [int(round(x.note.start / s16)) for x in group]
        i = 0
        while i < len(group):
            j = i
            while (j + 1 < len(group) and ticks[j + 1] - ticks[j] in (1, 2)
                   and group[j].note.end >= group[j + 1].note.start - s16 - 1e-6):
                j += 1
            steps = [ticks[x + 1] - ticks[x] for x in range(i, j)]
            if (j - i + 1 >= piano_playable.MERGE_MIN_RUN
                    and steps.count(1) * 3 >= len(steps) * 2):
                first = copy.copy(group[i])
                first.note = copy.copy(group[i].note)
                first.note.end = max(x.note.end for x in group[i:j + 1])
                first.note.velocity = max(x.note.velocity for x in group[i:j + 1])
                winner = max(group[i:j + 1], key=lambda x: (x.coverage, x.note.velocity))
                first.program, first.track, first.coverage = (
                    winner.program, winner.track, winner.coverage)
                output.append(first)
                merged += j - i
            else:
                output.extend(group[i:j + 1])
            i = j + 1
    return sorted(output, key=lambda x: (x.note.start, x.note.pitch)), merged


def mark_repetitions(tagged: list[Tagged], beat: float) -> dict[str, int]:
    by_program: dict[int, list[Tagged]] = defaultdict(list)
    for item in tagged:
        by_program[item.program].append(item)
    counts: dict[str, int] = {}
    for program, items in by_program.items():
        marked = repeated_ids([x.note for x in items], beat)
        for item in items:
            item.repeated = id(item.note) in marked
        counts[ALLOWED[program]] = sum(x.repeated for x in items)
    return counts


def feasible(pitches: list[int]) -> bool:
    """At most five notes and a 14-semitone span in each of two hands."""
    ps = sorted(set(pitches))
    if len(ps) != len(pitches) or len(ps) > 10:
        return False
    for split in range(len(ps) + 1):
        left, right = ps[:split], ps[split:]
        if (len(left) <= 5 and len(right) <= 5
                and (not left or left[-1] - left[0] <= piano_playable.HAND_SPAN)
                and (not right or right[-1] - right[0] <= piano_playable.HAND_SPAN)):
            return True
    return False


def best_hand(items: list[Tagged]) -> list[Tagged]:
    """Best at-most-five-note span among a pitch-sorted side of the hand split."""
    best: list[Tagged] = []
    best_key = (-1.0, -1, -1, -1)
    for start in range(len(items)):
        for stop in range(start + 1, len(items) + 1):
            window = items[start:stop]
            if window[-1].note.pitch - window[0].note.pitch > piano_playable.HAND_SPAN:
                break
            picked = sorted(window, key=lambda x: (x.score, x.note.velocity,
                                                    x.note.end - x.note.start, x.note.pitch),
                            reverse=True)[:piano_playable.HAND_NOTES]
            key = (round(sum(x.score for x in picked), 9), len(picked),
                   len({x.note.pitch % 12 for x in picked}),
                   sum(x.note.velocity for x in picked))
            if key > best_key:
                best, best_key = picked, key
    return best


def select_two_hands(items: list[Tagged]) -> list[Tagged]:
    by_pitch: dict[int, Tagged] = {}
    for item in items:
        pitch = item.note.pitch
        if pitch not in by_pitch or item.score > by_pitch[pitch].score:
            by_pitch[pitch] = item
    ordered = [by_pitch[p] for p in sorted(by_pitch)]
    if feasible([x.note.pitch for x in ordered]):
        return ordered
    best: list[Tagged] = []
    best_key = (-1.0, -1, -1, -1)
    for split in range(len(ordered) + 1):
        picked = best_hand(ordered[:split]) + best_hand(ordered[split:])
        key = (round(sum(x.score for x in picked), 9), len(picked),
               len({x.note.pitch % 12 for x in picked}),
               sum(x.note.velocity for x in picked))
        if key > best_key:
            best, best_key = picked, key
    if not feasible([x.note.pitch for x in best]):
        raise ValueError('Internal two-hand optimizer error')
    return best


def reduce_notes(tagged: list[Tagged]) -> tuple[list[Tagged], dict]:
    groups: dict[float, list[Tagged]] = defaultdict(list)
    for item in tagged:
        groups[item.note.start].append(item)
    active: list[Tagged] = []
    kept: list[Tagged] = []
    dropped = truncated = reattacked = 0
    for time, incoming in sorted(groups.items()):
        active = [x for x in active if x.note.end > time + 1e-9]
        incoming_pitches = {x.note.pitch for x in incoming}
        for old in active:
            if old.note.pitch in incoming_pitches:
                old.note.end = time
                reattacked += 1
        active = [x for x in active if x.note.end > time + 1e-9]
        for old in active:
            old.active = True
        chosen = select_two_hands(active + incoming)
        chosen_ids = {id(x) for x in chosen}
        for old in active:
            if id(old) not in chosen_ids:
                old.note.end = time
                truncated += 1
        active = [x for x in active if id(x) in chosen_ids]
        for new in incoming:
            if id(new) in chosen_ids:
                kept.append(new)
                active.append(new)
            else:
                dropped += 1
    kept = [x for x in kept if x.note.end > x.note.start + 1e-9]
    return kept, {'new_notes_dropped': dropped,
                  'held_notes_truncated': truncated, 'reattacked_held_notes': reattacked}


def audit(inst: pretty_midi.Instrument) -> dict:
    events: dict[float, list[tuple[int, int]]] = defaultdict(list)
    for note in inst.notes:
        if not 0 <= note.pitch <= 127 or note.end <= note.start:
            raise ValueError('Invalid output note')
        events[note.start].append((1, note.pitch))
        events[note.end].append((-1, note.pitch))
    active: dict[int, int] = defaultdict(int)
    maximum = 0
    for time, changes in sorted(events.items()):
        for direction, pitch in sorted(changes):
            active[pitch] += direction
        if any(count < 0 or count > 1 for count in active.values()):
            raise ValueError(f'Overlapping pitch at {time}')
        pitches = [pitch for pitch, count in active.items() if count]
        if not feasible(pitches):
            raise ValueError(f'Two-hand rule failed at {time}')
        maximum = max(maximum, len(pitches))
    if any(active.values()):
        raise ValueError('Unclosed notes')
    return {'notes_out': len(inst.notes), 'max_simultaneous_notes': maximum}


def run_song(index: int, folder: str, song_id: str) -> dict:
    base = SOURCE / folder / song_id
    raw_path, aligned_path = base / 'raw.mid', base / 'aligned.mid'
    source_status_path = base / 'status.json'
    target = OUT / folder / song_id
    output_path = target / 'duration_repeat_priority_playable.mid'
    record = {'index': index, 'folder': folder, 'song_id': song_id,
              'raw': str(raw_path), 'aligned': str(aligned_path), 'output': str(output_path)}
    try:
        source_status = json.loads(source_status_path.read_text(encoding='utf-8'))
        if source_status.get('status') != 'complete':
            raise ValueError('Source transcription is not complete')
        song_duration = float(source_status['duration_sec'])
        raw = pretty_midi.PrettyMIDI(str(raw_path))
        aligned = pretty_midi.PrettyMIDI(str(aligned_path))
        coverage, raw_stats = raw_coverage(raw, song_duration)
        tagged = annotate_aligned(aligned, coverage)
        merged, duplicates = merge_tracks(tagged)
        tempo = float(aligned.get_tempo_changes()[1][0])
        cleaned, reattacks = merge_reattacks_tagged(merged, 60.0 / tempo / 4)
        repeated = mark_repetitions(cleaned, 60.0 / tempo)
        selected, selection_stats = reduce_notes(cleaned)
        result = copy.deepcopy(aligned)
        track = pretty_midi.Instrument(program=0, name='Duration and repeat priority playable')
        track.notes = sorted((x.note for x in selected), key=lambda n: (n.start, n.pitch))
        result.instruments = [track]
        audited = audit(track)
        target.mkdir(parents=True, exist_ok=True)
        temp = output_path.with_suffix('.tmp.mid')
        result.write(str(temp))
        reread = pretty_midi.PrettyMIDI(str(temp))
        if selected:
            if len(reread.instruments) != 1 or reread.instruments[0].program != 0:
                raise ValueError('Expected one GM0 track')
            audit(reread.instruments[0])
        elif reread.instruments:
            raise ValueError('Unexpected nonempty MIDI')
        os.replace(temp, output_path)
        candidate_by_label = defaultdict(int)
        kept_by_label = defaultdict(int)
        repeated_kept_by_label = defaultdict(int)
        for item in cleaned:
            candidate_by_label[ALLOWED[item.program]] += 1
        for item in selected:
            kept_by_label[ALLOWED[item.program]] += 1
            repeated_kept_by_label[ALLOWED[item.program]] += int(item.repeated)
        record.update(status='ok', source_status_sha256=sha256(source_status_path),
                      raw_sha256=sha256(raw_path),
                      aligned_sha256=sha256(aligned_path), output_sha256=sha256(output_path),
                      **raw_stats, aligned_notes=len(tagged),
                      duplicate_notes_merged=duplicates, reattacks_merged=reattacks,
                      repeated_notes_after_merge=repeated,
                      **selection_stats, **audited,
                      candidate_by_label=dict(candidate_by_label),
                      kept_by_label=dict(kept_by_label),
                      repeated_kept_by_label=dict(repeated_kept_by_label))
    except Exception as exc:
        record.update(status='error', error=f'{type(exc).__name__}: {exc}',
                      traceback=traceback.format_exc())
    atomic_json(target / 'duration_priority_status.json', record)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--start', type=int, required=True)
    parser.add_argument('--end', type=int, required=True)
    args = parser.parse_args()
    with (ROOT / 'manifest.tsv').open(newline='', encoding='utf-8') as f:
        songs = list(csv.reader(f, delimiter='\t'))
    if len(songs) != 70 or not (1 <= args.start <= args.end <= 70):
        raise ValueError('Expected 70 songs and a valid inclusive range')
    records = []
    for index in range(args.start, args.end + 1):
        folder, song_id, _ = songs[index - 1]
        record = run_song(index, folder, song_id)
        records.append(record)
        print(f"{index}/70 {folder}/{song_id}: {record['status']}", flush=True)
    summary = {'range': [args.start, args.end], 'songs': len(records),
               'ok': sum(r['status'] == 'ok' for r in records),
               'failed': sum(r['status'] != 'ok' for r in records),
               'method': {'coverage': 'raw.mid sounding-time union / song duration',
                          'repeat': '3 same-pitch strikes after reattack merge; gaps 0.375-2 beats; span <=4 beats',
                          'score': '0.05 + coverage_fraction + 0.35*repeated + 0.005*already_active',
                          'hands': 'two hands, <=5 notes and <=14 semitones per hand; held notes included'},
               'script_sha256': sha256(Path(__file__)),
               'piano_playable_sha256': sha256(PLAYABLE_CODE), 'records': records}
    atomic_json(OUT / f'summary_{args.start}_{args.end}.json', summary)
    if summary['failed']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
