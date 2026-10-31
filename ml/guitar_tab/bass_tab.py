"""Bass TAB with tuttut (no split).

1. takes every bass-program note (MIDI programs 32-39) of a beat-aligned MIDI,
2. keeps only the lowest note at each onset (a bass line, not chords),
3. moves notes outside the bass range by octaves (fold_range),
4. chooses string/fret with tuttut (same weights as the guitar, b=0.1),
5. writes bass.mid, tab_bass.txt and "<title> - bass.gp5".

Tuning (auto, default): follows the guitar of the same MIDI, because a band tunes together.
skyline_tab.choose_tuning picks the guitar tuning (standard / half step down / drop D) and the bass
gets the 4-string version of it; no guitar notes -> 4-string standard. --tuning overrides it.

    python bass_tab.py song_aligned.mid out_dir/ [--tuning auto|bass_standard|bass_half_step_down|bass_drop_d|bass5_standard]

Input: beat-aligned MIDI from ml/beat_align. Reuses the helpers of skyline_tab.py.

Written with Claude (AI); reviewed by Soobin Jo.
"""
import argparse
from pathlib import Path

import pretty_midi

import skyline_tab as st

BASS_TUNINGS = {  # thin -> thick, MIDI numbers
    "bass_standard": [43, 38, 33, 28],          # G2 D2 A1 E1
    "bass_half_step_down": [42, 37, 32, 27],
    "bass_drop_d": [43, 38, 33, 26],
    "bass5_standard": [43, 38, 33, 28, 23],     # + low B0
}
GUITAR_TO_BASS = {"standard": "bass_standard", "half_step_down": "bass_half_step_down", "drop_d": "bass_drop_d"}
BASS_PROGRAM = 33  # electric bass (finger)

st.TUNINGS.update(BASS_TUNINGS)
st.NAMES.update({k: [pretty_midi.note_number_to_name(p) for p in v] for k, v in BASS_TUNINGS.items()})


def bass_notes(pm):
    return sorted((n for i in pm.instruments if 32 <= i.program <= 39 and not i.is_drum for n in i.notes),
                  key=lambda n: (n.start, n.pitch))


def choose_bass_tuning(pm):
    """Bass tuning that follows the guitar tuning. Returns (bass_tuning, guitar_tuning or None)."""
    g = st.guitar_notes(pm)
    if not g:
        return "bass_standard", None
    gt = st.choose_tuning([n.pitch for n in g])
    return GUITAR_TO_BASS[gt], gt


def bass_line(notes, tuning):
    """Lowest note per onset, folded into the tuning's range. Returns (notes, stats)."""
    lowest = {}
    for n in sorted(notes, key=lambda n: (n.start, n.pitch)):
        lowest.setdefault(round(n.start, 4), n)
    out = [pretty_midi.Note(100, st.fold_range(n.pitch, tuning), n.start, n.end) for n in lowest.values()]
    folded = sum(o.pitch != n.pitch for o, n in zip(out, lowest.values()))
    return out, {"notes_in": len(notes), "chord_notes_dropped": len(notes) - len(out), "octave_folded": folded}


def main(src, out_dir, tuning="auto"):
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pm = pretty_midi.PrettyMIDI(src)
    if tuning == "auto":
        tuning, gt = choose_bass_tuning(pm)
        print(f"tuning auto: guitar {gt or 'none'} -> {tuning}")
    notes, s = bass_line(bass_notes(pm), tuning)
    print(f"bass notes {len(notes)} · tuning {tuning} {st.NAMES[tuning]} · "
          f"chord notes dropped {s['chord_notes_dropped']} (kept lowest per onset) · octave-folded {s['octave_folded']}")
    if not notes:
        print("no bass notes: nothing written")
        return s
    bass = st.part_midi(pm, notes, "Bass", program=BASS_PROGRAM)
    bass.write(str(out_dir / "bass.mid"))
    p, t = st.tab(bass, "tab_bass", tuning, out_dir)
    n, big, med = st.jump_stats(p)
    print(f"  TAB bass: {n} fretted events · jumps >5 frets: {big} ({big / max(n - 1, 1) * 100:.1f}%) · median move {med:.1f} frets")

    ts = pm.time_signature_changes[0] if pm.time_signature_changes else None
    num, den = (ts.numerator, ts.denominator) if ts else (4, 4)
    title = Path(src).stem.replace("_aligned", "")
    gp5 = out_dir / f"{title} - bass.gp5"
    ev = st.track_events(t, bass.instruments[0].notes, pm.resolution // 4)
    st.write_gp5(gp5, title, pm.get_tempo_changes()[1][0], num, tuning, [("Bass", ev)], den)
    import guitarpro as gp
    song = gp.parse(str(gp5))
    song.tracks[0].channel.instrument = BASS_PROGRAM   # write_gp5 sets a guitar sound
    gp.write(song, str(gp5))
    return s


def cli(argv=None):
    p = argparse.ArgumentParser(description="Bass TAB (lowest note per onset) with tuttut + Guitar Pro export")
    p.add_argument("midi", help="beat-aligned MIDI (ml/beat_align output)")
    p.add_argument("out_dir", help="output folder")
    p.add_argument("--tuning", choices=["auto"] + sorted(BASS_TUNINGS), default="auto",
                   help="auto (default): follow the guitar tuning of the same MIDI; or a fixed bass tuning")
    a = p.parse_args(argv)
    main(a.midi, a.out_dir, a.tuning)


if __name__ == "__main__":
    cli()
