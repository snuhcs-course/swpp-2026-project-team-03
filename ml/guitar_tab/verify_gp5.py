"""Read a skyline .gp5 back and check it against the lead/rhythm MIDI.

    python verify_gp5.py song.gp5 skyline_lead_rhythm.mid

Checks every bar's length, that no chord is wider than 4 frets, and that the pitches at
every onset match the MIDI track with the same index.

Written with Claude (AI); reviewed by Soobin Jo.
"""
import collections
import sys

import guitarpro as gp
import pretty_midi

LEN16 = {1: 16, 2: 8, 4: 4, 8: 2, 16: 1, 32: 0.5}


def beat_len16(beat):
    L = LEN16[beat.duration.value]
    return L * 1.5 if beat.duration.isDotted else L


def main(gp_path, mid_path):
    song = gp.parse(gp_path)
    pm = pretty_midi.PrettyMIDI(mid_path)
    spb16 = 60 / pm.get_tempo_changes()[1][0] / 4
    ok = True
    print(f"{gp_path.split('/')[-1]}: tempo {song.tempo}, measures {len(song.measureHeaders)}, tracks {len(song.tracks)}")
    for ti, track in enumerate(song.tracks):
        tuning = {s.number: s.value for s in track.strings}
        bar16 = song.measureHeaders[0].timeSignature.numerator * 4
        bad_bars, onsets, pos = 0, collections.defaultdict(set), 0
        span_bad = 0
        for m in track.measures:
            total = 0
            for b in m.voices[0].beats:
                if b.status == gp.BeatStatus.normal:
                    new = [n for n in b.notes if n.type == gp.NoteType.normal]
                    for n in new:
                        onsets[pos].add(tuning[n.string] + n.value)
                    fr = [n.value for n in new if n.value > 0]
                    if fr and max(fr) - min(fr) > 4:
                        span_bad += 1
                total += beat_len16(b)
                pos += beat_len16(b)
            if total != bar16:
                bad_bars += 1
        # compare with MIDI track of the same index (onset grid in 16ths)
        ref = collections.defaultdict(set)
        if ti < len(pm.instruments):
            for n in pm.instruments[ti].notes:
                ref[round(n.start / spb16)].add(n.pitch)
        same = sum(1 for k in ref if onsets.get(k) == ref[k])
        moved = sum(1 for k in ref if k in onsets and onsets[k] != ref[k])
        missing = sum(1 for k in ref if k not in onsets)
        print(f"  [{track.name}] onsets {len(onsets)} · bars with wrong length {bad_bars} · chords wider than 4 frets {span_bad} · "
              f"vs MIDI: same pitches {same}/{len(ref)}, different {moved}, missing {missing}")
        ok &= bad_bars == 0
    return ok


if __name__ == "__main__":
    sys.exit(0 if main(sys.argv[1], sys.argv[2]) else 1)
