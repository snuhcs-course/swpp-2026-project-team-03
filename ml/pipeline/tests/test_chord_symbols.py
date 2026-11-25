from pathlib import Path
import sys

import pretty_midi
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chord_symbols import estimate_chords
from publish_scores import gp5_score


def song(bars, bpm=120):
    """Each bar is 4/4 (2 s at 120 BPM) and lists (pitches, start beat, beats)."""
    midi = pretty_midi.PrettyMIDI(initial_tempo=bpm)
    midi.time_signature_changes.append(pretty_midi.TimeSignature(4, 4, 0))
    track = pretty_midi.Instrument(29)
    beat = 60 / bpm
    for index, events in enumerate(bars):
        for pitches, at, length in events:
            start = (index * 4 + at) * beat
            track.notes.extend(pretty_midi.Note(90, p, start, start + length * beat) for p in pitches)
    midi.instruments.append(track)
    return midi


def whole(*pitches):
    return [(pitches, 0, 4)]


def names(chords):
    return {bar: [name for _, name in found] for bar, found in chords.items()}


def test_common_chords_are_named():
    midi = song([whole(48, 60, 64, 67), whole(45, 60, 64, 69), whole(43, 59, 62, 65, 67),
                 whole(40, 47, 52)])
    assert names(estimate_chords(midi)) == {0: ["C"], 1: ["Am"], 2: ["G7"], 3: ["E5"]}


def test_two_chords_in_one_bar_are_placed_on_each_half():
    midi = song([[((48, 60, 64, 67), 0, 2), ((43, 59, 62, 67), 2, 2)]])
    assert estimate_chords(midi) == {0: [(0.0, "C"), (0.5, "G")]}


def test_unclear_bar_stays_blank():
    midi = song([whole(*range(60, 72)), whole(60), whole(48, 60, 64, 67)])
    assert names(estimate_chords(midi)) == {2: ["C"]}


def test_flat_key_uses_flat_names():
    midi = song([whole(46, 58, 62, 65), whole(51, 58, 63, 67)])
    assert names(estimate_chords(midi)) == {0: ["Bb"], 1: ["Eb"]}




def test_gp5_keeps_chord_names(tmp_path):
    guitarpro = pytest.importorskip("guitarpro")
    source, target = tmp_path / "in.gp5", tmp_path / "out.gp5"
    from guitarpro import models
    tune = models.Song()
    measure = tune.tracks[0].measures[0]
    measure.voices[0].beats.append(models.Beat(measure.voices[0], start=measure.start))
    guitarpro.write(tune, str(source))
    gp5_score(source, target, [("Guitar", 29)], chords={0: [(0.0, "Am7")]}, score_bars=1)
    beat = guitarpro.parse(str(target)).tracks[0].measures[0].voices[0].beats[0]
    assert beat.effect.chord.name == "Am7"


def test_gp5_with_other_bar_count_gets_no_chords(tmp_path):
    guitarpro = pytest.importorskip("guitarpro")
    source, target = tmp_path / "in.gp5", tmp_path / "out.gp5"
    from guitarpro import models
    tune = models.Song()
    measure = tune.tracks[0].measures[0]
    measure.voices[0].beats.append(models.Beat(measure.voices[0], start=measure.start))
    guitarpro.write(tune, str(source))
    gp5_score(source, target, [("Guitar", 29)], chords={0: [(0.0, "C")]}, score_bars=9)
    beat = guitarpro.parse(str(target)).tracks[0].measures[0].voices[0].beats[0]
    assert beat.effect.chord is None
