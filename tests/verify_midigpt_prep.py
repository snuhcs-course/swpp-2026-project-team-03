"""Smoke-test feature/midigpt's input preparation without model inference."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import mido
import pretty_midi


def verify(module: Path) -> None:
    sys.path.insert(0, str(module))
    import prep_song

    assert [prep_song.classify(program, False) for program in (0, 26, 33, 48)] == [
        "piano", "guitar", "bass", "other"
    ]
    assert prep_song.classify(0, True) == "drums"
    tempos = [(0, mido.MetaMessage("set_tempo", tempo=500_000)),
              (480, mido.MetaMessage("set_tempo", tempo=400_000))]
    assert prep_song.main_tempo(tempos, 1920, 480) == (400_000, 2)

    with tempfile.TemporaryDirectory(prefix="rocky-midigpt-") as directory:
        root = Path(directory)
        midi = pretty_midi.PrettyMIDI()
        for name, program, drum in (("piano", 0, False), ("guitar", 26, False),
                                    ("bass", 33, False), ("drums", 0, True),
                                    ("other", 48, False)):
            track = pretty_midi.Instrument(program=program, is_drum=drum, name=name)
            track.notes.append(pretty_midi.Note(100, 36 if drum else 60, 0, 0.5))
            midi.instruments.append(track)
        source = root / "fixture.mid"
        midi.write(str(source))
        destination = root / "prepared"
        env = dict(os.environ, ROCKY_PREP_OUT=str(destination))
        subprocess.run([sys.executable, str(module / "prep_song.py"), str(source)],
                       env=env, check=True, capture_output=True, text=True)
        parts = destination / "Trackfixture" / "MIDI"
        expected = {"piano.mid", "guitar.mid", "bass.mid", "drums.mid", "other_00.mid"}
        assert {file.name for file in parts.glob("*.mid")} == expected
        for file in parts.glob("*.mid"):
            assert any(message.type == "note_on" and message.velocity > 0
                       for track in mido.MidiFile(file).tracks for message in track)
    print("MIDI-GPT prep contract: PASS (classification, tempo, five output parts)")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("module", type=Path, help="checkout's ml/midigpt directory")
    args = parser.parse_args()
    verify(args.module.resolve())


if __name__ == "__main__":
    main()
