"""Generated (MIDI-GPT) parts go on the aligned grid and, for keyboard, get the two-hand limits.

Needs ml/beat_align and ml/guitar_tab next to ml/pipeline (the /data/rocky-unified/ml layout);
skipped when they are not there.
"""
import sys
from pathlib import Path

import pretty_midi
import pytest

ML = Path(__file__).resolve().parents[2]
if not ((ML / "beat_align").is_dir() and (ML / "guitar_tab").is_dir()):
    pytest.skip("ml/beat_align or ml/guitar_tab not found", allow_module_level=True)
sys.path.insert(0, str(ML / "pipeline"))
sys.path.insert(0, str(ML / "beat_align"))
sys.path.insert(0, str(ML / "guitar_tab"))
from align import snap_to_reference  # noqa: E402
import piano_playable  # noqa: E402
from unified import normalize_generated  # noqa: E402


def _aligned(bpm=160.0, beats=32):
    ref = pretty_midi.PrettyMIDI(initial_tempo=bpm, resolution=480)
    ref.time_signature_changes.append(pretty_midi.TimeSignature(4, 4, 0))
    d = pretty_midi.Instrument(0, is_drum=True)
    d.notes = [pretty_midi.Note(100, 36, k * 60 / bpm, k * 60 / bpm + 0.05) for k in range(beats)]
    ref.instruments.append(d)
    return ref


def test_normalize_generated_snaps_to_the_aligned_grid(tmp_path):
    ref = _aligned(160)
    cell = 60 / 160 / 4
    gen = pretty_midi.PrettyMIDI(initial_tempo=160)
    piano = pretty_midi.Instrument(0, name="Piano")
    piano.notes = [pretty_midi.Note(80, 60 + k % 5, k * 2 * cell + 0.035, k * 2 * cell + 0.035 + cell)
                   for k in range(40)]
    gen.instruments.append(piano)
    src = tmp_path / "gen.mid"
    gen.write(str(src))
    out = tmp_path / "piano.mid"
    stats = normalize_generated(src, "piano", ref, ref.get_end_time() + 1, out, snap=snap_to_reference)
    assert stats["snap"]["mean_offgrid_16ths_before"] > 0.05
    for n in pretty_midi.PrettyMIDI(str(out)).instruments[0].notes:
        assert abs(n.start / cell - round(n.start / cell)) < 1e-3


def test_generated_nine_note_chord_becomes_playable():
    gen = pretty_midi.PrettyMIDI(initial_tempo=120)
    piano = pretty_midi.Instrument(0)
    piano.notes = [pretty_midi.Note(80, p, 0.0, 1.0) for p in (36, 43, 48, 52, 55, 60, 64, 67, 72)]
    gen.instruments.append(piano)
    out, _ = piano_playable.process(gen)
    assert len(out.instruments[0].notes) <= 2 * piano_playable.HAND_NOTES
    assert len(out.instruments[0].notes) < 9
