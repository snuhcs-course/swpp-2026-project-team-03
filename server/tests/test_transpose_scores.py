"""Rule based key changes preserve timing, drums and playable TAB notes."""

import copy
import guitarpro
import pretty_midi
import pytest

from rocky_server.transpose_scores import transpose_gp5, transpose_midi


def test_midi_moves_pitched_tracks_and_keeps_drums(tmp_path):
    score = pretty_midi.PrettyMIDI(initial_tempo=120)
    score.key_signature_changes.append(pretty_midi.KeySignature(0, 0))
    for pitch, drum in ((60, False), (38, True)):
        track = pretty_midi.Instrument(program=0, is_drum=drum)
        track.notes.append(pretty_midi.Note(90, pitch, 0.25, 0.75))
        score.instruments.append(track)
    source, output = tmp_path / "source.mid", tmp_path / "output.mid"
    score.write(str(source))
    transpose_midi(source, output, 2)
    shifted = pretty_midi.PrettyMIDI(str(output))
    assert [t.notes[0].pitch for t in shifted.instruments] == [62, 38]
    assert [t.notes[0].start for t in shifted.instruments] == pytest.approx([0.25, 0.25], abs=.001)
    assert shifted.key_signature_changes[0].key_number == 2


def gp5_with_note(path, *, string=1, fret=3):
    song = guitarpro.models.Song()
    voice = song.tracks[0].measures[0].voices[0]
    beat = guitarpro.models.Beat(voice)
    voice.beats.append(beat)
    beat.notes.append(guitarpro.models.Note(beat, string=string, value=fret,
                                            type=guitarpro.NoteType.normal))
    guitarpro.write(song, str(path))


def note_pitch(song):
    track = song.tracks[0]
    note = track.measures[0].voices[0].beats[0].notes[0]
    return next(s.value for s in track.strings if s.number == note.string) + note.value


@pytest.mark.parametrize("step", [-2, -1, 1, 2])
def test_gp5_moves_pitch_and_keeps_playable_fret(tmp_path, step):
    source, output = tmp_path / "source.gp5", tmp_path / "output.gp5"
    gp5_with_note(source)
    before = guitarpro.parse(str(source))
    transpose_gp5(source, output, step)
    after = guitarpro.parse(str(output))
    assert note_pitch(after) - note_pitch(before) == step
    note = after.tracks[0].measures[0].voices[0].beats[0].notes[0]
    assert 0 <= note.value <= after.tracks[0].fretCount
    assert [s.value for s in after.tracks[0].strings] == [s.value for s in before.tracks[0].strings]
    assert after.key != before.key


def test_low_open_string_uses_retuning_when_downshift_cannot_be_fretted(tmp_path):
    source, output = tmp_path / "source.gp5", tmp_path / "output.gp5"
    gp5_with_note(source, string=6, fret=0)
    before = guitarpro.parse(str(source))
    transpose_gp5(source, output, -1)
    after = guitarpro.parse(str(output))
    assert note_pitch(after) == note_pitch(before) - 1
    assert after.tracks[0].strings[-1].value == before.tracks[0].strings[-1].value - 1


def test_retuning_is_limited_to_the_track_with_an_open_low_note(tmp_path):
    source, output = tmp_path / "source.gp5", tmp_path / "output.gp5"
    gp5_with_note(source, string=6, fret=0)
    song = guitarpro.parse(str(source))
    second = copy.deepcopy(song.tracks[0])
    second.number = 2
    second.measures[0].voices[0].beats[0].notes[0].value = 5
    song.tracks.append(second)
    guitarpro.write(song, str(source))
    before = guitarpro.parse(str(source))
    transpose_gp5(source, output, -1)
    after = guitarpro.parse(str(output))
    assert len(after.tracks) == 2
    assert after.tracks[0].strings[-1].value == before.tracks[0].strings[-1].value - 1
    assert [s.value for s in after.tracks[1].strings] == [s.value for s in before.tracks[1].strings]
    assert after.tracks[1].measures[0].voices[0].beats[0].notes[0].value == 4


@pytest.mark.parametrize("second_track", [False, True])
@pytest.mark.parametrize("bass", [False, True])
def test_retuned_first_track_keeps_transposed_key_signature(tmp_path, second_track, bass):
    source, output = tmp_path / "source.gp5", tmp_path / "output.gp5"
    gp5_with_note(source, string=4 if bass else 6, fret=0)
    song = guitarpro.parse(str(source))
    if bass:
        song.tracks[0].strings = [guitarpro.models.GuitarString(i + 1, pitch)
                                  for i, pitch in enumerate((43, 38, 33, 28))]
    song.key = guitarpro.KeySignature.GMajor
    song.measureHeaders[0].keySignature = guitarpro.KeySignature.GMajor
    if second_track:
        other = copy.deepcopy(song.tracks[0])
        other.number = 2
        other.measures[0].voices[0].beats[0].notes[0].value = 5
        song.tracks.append(other)
    guitarpro.write(song, str(source))

    transpose_gp5(source, output, -1)
    after = guitarpro.parse(str(output))
    assert after.measureHeaders[0].keySignature == guitarpro.KeySignature.FMajorSharp
    assert after.tracks[0].measures[0].header.keySignature == guitarpro.KeySignature.FMajorSharp
