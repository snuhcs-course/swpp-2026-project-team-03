"""align.py 단위 테스트. Beat This! 모델 없이 가짜 박 배열로 검증한다.

Written with Claude (AI); reviewed by Soobin Jo.
"""
import sys
from pathlib import Path

import numpy as np
import pretty_midi
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from align import (align_midi, align_pretty_midi, beat_levels, choose_triplet_beats,  # noqa: E402
                   compute_beat_offset, detect_compound, drum_bar_phase, estimate_beats_per_bar,
                   estimate_bpm, fix_beats, triplet_share)


def make_midi(notes):
    """notes: [(pitch, start, end)] → 피아노 한 트랙짜리 PrettyMIDI"""
    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(program=0)
    for pitch, s, e in notes:
        inst.notes.append(pretty_midi.Note(velocity=100, pitch=pitch, start=s, end=e))
    pm.instruments.append(inst)
    return pm


def test_bpm_from_even_beats():
    beats = np.arange(0, 10, 0.5)  # 0.5 s 간격 = 120 BPM
    bpm, _ = estimate_bpm(beats)
    assert bpm == pytest.approx(120.0)


def test_bpm_ignores_outlier_intervals():
    beats = np.array([0.0, 0.5, 1.0, 1.5, 1.6, 2.1, 2.6, 5.0])  # 0.1 s, 2.4 s 간격은 제외
    bpm, _ = estimate_bpm(beats)
    assert bpm == pytest.approx(120.0)


def test_no_valid_interval_raises():
    with pytest.raises(ValueError):
        estimate_bpm(np.array([0.0, 0.05, 0.1]))


def test_first_downbeat_becomes_bar_start():
    beats = np.arange(0, 10, 0.5)
    downbeats = beats[1::4]  # 두 번째 박부터 다운비트
    assert compute_beat_offset(beats, downbeats) == 3
    assert compute_beat_offset(beats, []) == 0


# ----------------------------------------------------------------------
# 박자 추정 (다운비트 사이 박 수)
# ----------------------------------------------------------------------
@pytest.mark.parametrize("n", [2, 3, 4, 5, 6, 7])
def test_meter_from_regular_downbeats(n):
    beats = np.arange(0, 30, 0.5)
    assert estimate_beats_per_bar(beats, beats[1::n]) == n


def test_meter_defaults_to_four_without_enough_downbeats():
    beats = np.arange(0, 10, 0.5)
    assert estimate_beats_per_bar(beats, []) == 4
    assert estimate_beats_per_bar(beats, beats[:1]) == 4


def test_meter_defaults_to_four_when_no_usable_gap():
    """다운비트가 매 박마다 찍히면(간격 1) 쓸 만한 간격이 없으므로 4"""
    beats = np.arange(0, 10, 0.5)
    assert estimate_beats_per_bar(beats, beats) == 4


def test_meter_ignores_occasional_wrong_downbeats():
    """마디 중간 다운비트(2+2)와 놓친 다운비트(8)가 섞여도 4로 본다"""
    beats = np.arange(0, 100, 0.5)
    idx = [0, 4, 8, 10, 12, 16, 24, 28, 32, 36]   # 간격 4,4,2,2,4,8,4,4,4
    assert estimate_beats_per_bar(beats, beats[idx]) == 4


def test_meter_tie_prefers_four():
    beats = np.arange(0, 30, 0.5)
    idx = [0, 3, 6, 10, 14]                        # 3,3,4,4
    assert estimate_beats_per_bar(beats, beats[idx]) == 4


def test_offset_uses_meter():
    beats = np.arange(0, 10, 0.5)
    assert compute_beat_offset(beats, beats[2::3], beats_per_bar=3) == 1


def test_three_four_song_gets_three_four_bars():
    beats = np.arange(0, 20, 0.5)                  # 120 BPM
    downbeats = beats[1::3]                        # 두 번째 박부터 3박마다
    midi = make_midi([(60, 0.5, 1.0), (62, 2.0, 2.5)])
    out, r = align_pretty_midi(midi, beats, downbeats)
    assert r.beats_per_bar == 3 and r.beat_offset == 2
    ts = out.time_signature_changes
    assert len(ts) == 1 and (ts[0].numerator, ts[0].denominator) == (3, 4)
    # 첫 다운비트(0.5 s)의 음표가 마디 시작(3박 = 1.5 s)에 온다
    starts = sorted(n.start for n in out.instruments[0].notes)
    assert starts[0] == pytest.approx(1.5)
    assert starts[1] == pytest.approx(3.0)        # 다음 다운비트(2.0 s) → 2마디 시작


def test_four_four_unchanged_with_regular_downbeats():
    beats = np.arange(0, 20, 0.5)
    out, r = align_pretty_midi(make_midi([(60, 0.5, 1.0)]), beats, beats[1::4])
    assert r.beats_per_bar == 4
    assert (out.time_signature_changes[0].numerator, out.time_signature_changes[0].denominator) == (4, 4)


def test_notes_snap_to_sixteenth_grid():
    beats = np.arange(0, 10, 0.5)
    pm = make_midi([(60, 0.53, 0.98)])  # 박에서 살짝 어긋난 음
    out, r = align_pretty_midi(pm, beats, beats[::4])
    note = out.instruments[0].notes[0]
    sixteenth = 60.0 / r.bpm / 4
    assert note.start / sixteenth == pytest.approx(round(note.start / sixteenth))
    assert note.start == pytest.approx(0.5)


def test_tempo_rewritten_to_detected_bpm():
    beats = np.arange(0, 20, 60 / 91)  # 91 BPM
    out, r = align_pretty_midi(make_midi([(60, 1.0, 2.0)]), beats, beats[::4])
    assert r.bpm == pytest.approx(91.0, rel=1e-3)
    _, tempi = out.get_tempo_changes()
    assert tempi[0] == pytest.approx(91.0, rel=1e-3)
    ts = out.time_signature_changes[0]
    assert (ts.numerator, ts.denominator) == (4, 4)


def test_zero_length_note_gets_sixteenth():
    beats = np.arange(0, 10, 0.5)
    out, r = align_pretty_midi(make_midi([(60, 1.0, 1.01)]), beats, beats[::4])
    note = out.instruments[0].notes[0]
    assert note.end - note.start == pytest.approx(60.0 / r.bpm / 4)


def test_instruments_and_note_count_kept():
    pm = make_midi([(60, 0.5, 1.0), (64, 1.0, 1.5)])
    drums = pretty_midi.Instrument(program=0, is_drum=True, name="Drums")
    drums.notes.append(pretty_midi.Note(velocity=90, pitch=36, start=0.5, end=0.6))
    pm.instruments.append(drums)
    out, r = align_pretty_midi(pm, np.arange(0, 10, 0.5), [])
    assert r.note_count == 3
    assert [i.is_drum for i in out.instruments] == [False, True]


def test_too_few_beats_raises():
    with pytest.raises(ValueError):
        align_pretty_midi(make_midi([(60, 0, 1)]), [1.0], [])


def test_align_midi_file_roundtrip(tmp_path):
    src = tmp_path / "in.mid"
    make_midi([(60, 0.52, 1.0)]).write(str(src))
    dst = tmp_path / "out" / "aligned.mid"
    beats = list(np.arange(0, 10, 0.5))
    r = align_midi(src, dst, beats=beats, downbeats=beats[::4])
    assert dst.exists() and r.note_count == 1


def test_align_midi_needs_beats_or_audio(tmp_path):
    src = tmp_path / "in.mid"
    make_midi([(60, 0, 1)]).write(str(src))
    with pytest.raises(ValueError):
        align_midi(src, tmp_path / "o.mid")


def test_notes_outside_beat_range():
    beats = np.arange(1.0, 5.0, 0.5)  # 박은 1~4.5 s 구간에만 있음
    pm = make_midi([(60, 0.0, 0.5), (62, 6.0, 6.5)])
    out, _ = align_pretty_midi(pm, beats, beats[::4])
    starts = [n.start for n in out.instruments[0].notes]
    assert starts[0] == 0.0           # 첫 박 이전 → 0초로 고정
    assert starts[1] > max(beats) - 1  # 마지막 박 이후 → 같은 템포로 연장


def test_beats_json_roundtrip(tmp_path):
    from align import load_beats, save_beats
    path = tmp_path / "b.json"
    save_beats(path, [0.5, 1.0], [0.5])
    assert load_beats(path) == ([0.5, 1.0], [0.5])


def test_cli_with_saved_beats(tmp_path, capsys):
    from align import main, save_beats
    src, beats_json, dst = tmp_path / "in.mid", tmp_path / "b.json", tmp_path / "out.mid"
    make_midi([(60, 0.52, 1.0)]).write(str(src))
    beats = list(np.arange(0, 10, 0.5))
    save_beats(beats_json, beats, beats[::4])
    main(["--midi", str(src), "--beats", str(beats_json), "--out", str(dst)])
    assert dst.exists()
    assert "BPM 120.00" in capsys.readouterr().out


# ----------------------------------------------------------------------
# 일괄 처리
# ----------------------------------------------------------------------
def _write_song(root, name, nested=True):
    """MuScriptor 구조(곡/muscriptor_large.mid) 또는 평평한 구조(곡.mid)로 MIDI 생성"""
    path = root / name / "muscriptor_large.mid" if nested else root / f"{name}.mid"
    path.parent.mkdir(parents=True, exist_ok=True)
    make_midi([(60, 0.52, 1.0)]).write(str(path))
    return path


def test_song_key_normalizes_names():
    import unicodedata
    from align import song_key
    nfd = unicodedata.normalize("NFD", "흰수염고래 - YB__no_vocals")
    assert song_key(nfd) == "흰수염고래 - YB"


def test_collect_midis_both_layouts(tmp_path):
    from align import collect_midis
    _write_song(tmp_path, "A__no_vocals", nested=True)
    _write_song(tmp_path, "B", nested=False)
    assert set(collect_midis(tmp_path)) == {"A", "B"}


def test_batch_with_beats_dir(tmp_path):
    from align import align_batch, save_beats
    midi_dir, beats_dir, out_dir = tmp_path / "midi", tmp_path / "beats", tmp_path / "out"
    beats = list(np.arange(0, 10, 0.5))
    for name in ["Song A__no_vocals", "Song B__no_vocals", "Only MIDI"]:
        _write_song(midi_dir, name)
    beats_dir.mkdir()
    for name in ["Song A__no_vocals", "Song B", "Only Beats"]:
        save_beats(beats_dir / f"{name}_beats.json", beats, beats[::4])

    report = align_batch(midi_dir, out_dir, beats_dir=beats_dir, log=lambda *_: None)
    assert report.succeeded == ["Song A", "Song B"]
    assert report.midi_only == ["Only MIDI"] and report.source_only == ["Only Beats"]
    assert (out_dir / "Song A_aligned.mid").exists()


def test_batch_continues_after_failure(tmp_path):
    from align import align_batch, save_beats
    midi_dir, beats_dir = tmp_path / "midi", tmp_path / "beats"
    _write_song(midi_dir, "Good"); _write_song(midi_dir, "Bad")
    beats_dir.mkdir()
    save_beats(beats_dir / "Good_beats.json", list(np.arange(0, 10, 0.5)), [0.0])
    save_beats(beats_dir / "Bad_beats.json", [1.0], [])  # 박 1개 → 실패
    report = align_batch(midi_dir, tmp_path / "out", beats_dir=beats_dir, log=lambda *_: None)
    assert report.succeeded == ["Good"] and set(report.failed) == {"Bad"}


def test_batch_with_audio_dir_uses_detector(tmp_path, monkeypatch):
    import align
    midi_dir, audio_dir, out_dir = tmp_path / "midi", tmp_path / "audio", tmp_path / "out"
    _write_song(midi_dir, "Song__no_vocals")
    audio_dir.mkdir(); (audio_dir / "Song.wav").write_bytes(b"")  # 원곡 이름 ↔ __no_vocals MIDI
    beats = list(np.arange(0, 10, 0.5))
    calls = []
    monkeypatch.setattr(align, "detect_beats", lambda p, device="auto": (calls.append(p) or (beats, beats[::4])))
    report = align.align_batch(midi_dir, out_dir, audio_dir=audio_dir, log=lambda *_: None)
    assert report.succeeded == ["Song"] and len(calls) == 1
    assert (out_dir / "Song_beats.json").exists()


def test_batch_needs_exactly_one_source(tmp_path):
    from align import align_batch
    with pytest.raises(ValueError):
        align_batch(tmp_path, tmp_path / "out")


def test_cli_batch_and_mode_errors(tmp_path):
    from align import main, save_beats
    midi_dir, beats_dir, out_dir = tmp_path / "midi", tmp_path / "beats", tmp_path / "out"
    _write_song(midi_dir, "X")
    beats_dir.mkdir()
    beats = list(np.arange(0, 10, 0.5))
    save_beats(beats_dir / "X_beats.json", beats, beats[::4])
    assert main(["--midi-dir", str(midi_dir), "--beats-dir", str(beats_dir), "--out-dir", str(out_dir)]) == 0
    assert (out_dir / "X_aligned.mid").exists()
    with pytest.raises(SystemExit):  # 한 곡/여러 곡 옵션을 섞으면 오류
        main(["--midi", "a.mid", "--midi-dir", str(midi_dir), "--out-dir", str(out_dir), "--beats-dir", str(beats_dir)])


# ----------------------------------------------------------------------
# --bpm: 1.5배·2배로 찍힌 박을 실제 템포로 다시 세기
# ----------------------------------------------------------------------
def _detected_with_fast_section(T=0.5):
    """120 BPM 곡. 8~16박 구간을 Beat This!가 2/3 간격(180 BPM)으로 찍은 상황"""
    slow1 = np.arange(0, 8) * T                       # 0.0 ~ 3.5
    fast = 8 * T + np.arange(0, 13) * T * 2 / 3        # 4.0 ~ 8.0 (실제 8박 = 찍힌 12간격)
    slow2 = 16 * T + np.arange(1, 9) * T               # 8.5 ~ 12.0
    return np.concatenate([slow1, fast, slow2])


def test_fix_beats_recounts_two_thirds_section():
    det = _detected_with_fast_section()
    assert len(det) == 29                                           # 고치기 전: 실제 25박보다 4개 많음
    new, _ = fix_beats(det, [0.0, 2.0], 120)
    assert np.allclose(new, np.arange(0, 25) * 0.5, atol=1e-6)    # 0.5 s 간격 25박
    assert estimate_bpm(new)[0] == pytest.approx(120)


def test_fix_beats_keeps_phase_across_unclear_intervals():
    T = 0.5
    a = np.arange(0, 10) * T
    messy = np.array([5.1, 5.35, 5.9])                  # 애매한 간격 (세지 않음)
    b = 6.5 + np.arange(0, 10) * T                      # 6.5 s = 13번째 박
    new, _ = fix_beats(np.concatenate([a, messy, b]), [], 120)
    assert np.isclose(new, 6.5).any() and np.isclose(new, 11.0).any()
    assert np.allclose(np.diff(new)[-9:], T)


def test_fix_beats_rebuilds_downbeats_from_meter():
    beats = np.arange(0, 20) * 0.5
    new, down = fix_beats(beats, beats[1::4], 120)      # 다운비트가 2번째 박부터 4박마다
    assert np.allclose(down, new[1::4])


def test_fix_beats_needs_matching_intervals():
    with pytest.raises(ValueError):
        fix_beats(np.arange(0, 10) * 0.5, [], 95)       # 0.5 s 간격은 95 BPM 박의 1, 2/3, 1/2, 2배와 모두 15% 넘게 다름


def test_fix_beats_too_few_beats():
    with pytest.raises(ValueError):
        fix_beats([1.0], [], 120)


# ----------------------------------------------------------------------
# --triplets: 박마다 16분음표 / 셋잇단 8분음표 칸 고르기
# ----------------------------------------------------------------------
def test_triplet_beat_detected():
    pos = [0, 1 / 3, 2 / 3, 1, 1.25, 1.5, 1.75]          # 0박: 셋잇단, 1박: 16분음표
    assert choose_triplet_beats(pos) == {0}


def test_triplet_needs_enough_offbeat_notes():
    assert choose_triplet_beats([0, 1 / 3, 1]) == set()   # 박 위가 아닌 음 1개뿐 → 판단 안 함


def test_ambiguous_beat_stays_sixteenth():
    assert choose_triplet_beats([0.29, 0.71]) == set()     # 1/4·1/3 사이, 셋잇단이 확실히 낫지 않음


def test_triplets_quantize_to_thirds():
    beats = np.arange(0, 10) * 0.5                        # 120 BPM
    pm = make_midi([(60, 1.0 + 0.5 / 3 + 0.01, 1.2), (62, 1.0 + 1.0 / 3 - 0.01, 1.4), (64, 2.125, 2.3)])
    out, r = align_pretty_midi(pm, beats, [0.0], triplets=True)
    starts = sorted(n.start for n in out.instruments[0].notes)
    assert starts[0] == pytest.approx(1.0 + 0.5 / 3) and starts[1] == pytest.approx(1.0 + 1.0 / 3)
    assert starts[2] == pytest.approx(2.125)              # 다른 박은 16분음표 그대로
    assert r.triplet_beats == 1


def test_triplets_off_by_default():
    beats = np.arange(0, 10) * 0.5
    pm = make_midi([(60, 1.0 + 0.5 / 3, 1.2), (62, 1.0 + 1.0 / 3, 1.4)])
    out, r = align_pretty_midi(pm, beats, [0.0])
    assert sorted(n.start for n in out.instruments[0].notes) == pytest.approx([1.125, 1.375])
    assert r.triplet_beats == 0


def test_zero_length_note_in_triplet_beat_gets_triplet_length():
    beats = np.arange(0, 10) * 0.5
    pm = make_midi([(60, 1.0 + 0.5 / 3, 1.0 + 0.5 / 3 + 0.01), (62, 1.0 + 1.0 / 3, 1.4)])
    out, _ = align_pretty_midi(pm, beats, [0.0], triplets=True)
    n = min(out.instruments[0].notes, key=lambda n: n.start)
    assert n.end - n.start == pytest.approx(0.5 / 3)


def test_cli_bpm_and_triplets(tmp_path, capsys):
    from align import main, save_beats
    midi = tmp_path / "in.mid"
    make_midi([(60, 1.0 + 0.5 / 3, 1.2), (62, 1.0 + 1.0 / 3, 1.4)]).write(str(midi))
    det = _detected_with_fast_section()
    save_beats(tmp_path / "b.json", list(det), [0.0, 2.0])
    out = tmp_path / "out.mid"
    assert main(["--midi", str(midi), "--beats", str(tmp_path / "b.json"), "--out", str(out),
                 "--bpm", "120", "--triplets"]) == 0
    printed = capsys.readouterr().out
    assert out.exists() and "BPM 120.00" in printed and "triplet beats 1" in printed


def test_cli_rejects_bpm_in_batch_mode(tmp_path):
    from align import main
    with pytest.raises(SystemExit):
        main(["--midi-dir", str(tmp_path), "--out-dir", str(tmp_path / "o"), "--beats-dir", str(tmp_path), "--bpm", "100"])


# ----------------------------------------------------------------------
# --compound (12/8, 6/8), --downbeat-shift
# ----------------------------------------------------------------------
def test_compound_writes_twelve_eight_and_eighth_grid():
    beats = np.arange(0, 17) * 0.6                     # 점4분음표 = 100 BPM
    pm = make_midi([(60, 0.6 + 0.2 + 0.02, 1.0), (62, 0.6 + 0.4 - 0.02, 1.2), (64, 1.2 + 0.1 + 0.01, 1.5)])
    out, r = align_pretty_midi(pm, beats, beats[::4], compound=True)
    ts = out.time_signature_changes[0]
    assert (ts.numerator, ts.denominator) == (12, 8)
    assert out.get_tempo_changes()[1][0] == pytest.approx(150)   # 4분음표 기준 템포 = 100 x 1.5
    starts = sorted(n.start for n in out.instruments[0].notes)
    assert starts == pytest.approx([0.8, 1.0, 1.3])                # 8분음표(0.2 s), 16분음표(0.1 s) 칸
    assert r.triplet_beats == 0


def test_compound_two_beat_bars_are_six_eight():
    beats = np.arange(0, 13) * 0.6
    out, _ = align_pretty_midi(make_midi([(60, 0.6, 0.9)]), beats, beats[::2], compound=True)
    ts = out.time_signature_changes[0]
    assert (ts.numerator, ts.denominator) == (6, 8)


def test_downbeat_shift_moves_bar_start():
    beats = np.arange(0, 16) * 0.5
    _, r0 = align_pretty_midi(make_midi([(60, 1.0, 1.5)]), beats, beats[::4])
    _, r1 = align_pretty_midi(make_midi([(60, 1.0, 1.5)]), beats, beats[::4], downbeat_shift=-1)
    _, r2 = align_pretty_midi(make_midi([(60, 1.0, 1.5)]), beats, beats[::4], downbeat_shift=1)
    assert (r0.beat_offset, r1.beat_offset, r2.beat_offset) == (0, 1, 3)


def test_cli_compound_and_shift(tmp_path, capsys):
    from align import main, save_beats
    midi = tmp_path / "in.mid"
    make_midi([(60, 0.8, 1.0)]).write(str(midi))
    beats = list(np.arange(0, 17) * 0.6)
    save_beats(tmp_path / "b.json", beats, beats[::4])
    out = tmp_path / "out.mid"
    assert main(["--midi", str(midi), "--beats", str(tmp_path / "b.json"), "--out", str(out),
                 "--compound", "--downbeat-shift", "-1"]) == 0
    printed = capsys.readouterr().out
    assert "12/8" in printed and "beat offset 1" in printed
    pm = pretty_midi.PrettyMIDI(str(out))
    assert pm.time_signature_changes[0].numerator == 12



# ----------------------------------------------------------------------
# 템포 평균, 자동 판별 (12/8 감지, 드럼 기준 마디선)
# ----------------------------------------------------------------------
def test_bpm_uses_mean_of_intervals_near_median():
    # 실제 128 BPM(0.46875 s)을 0.02 s 단위로 찍으면 0.46/0.48이 섞인다. 중앙값만 쓰면 130.4
    true = np.arange(0, 64) * 60 / 128
    beats = np.round(true / 0.02) * 0.02
    assert np.median(np.diff(beats)) == pytest.approx(0.46)
    assert estimate_bpm(beats)[0] == pytest.approx(128, abs=0.3)


def drum_midi(snare_beats, kick_beats, T=0.5, extra=None):
    pm = pretty_midi.PrettyMIDI()
    d = pretty_midi.Instrument(program=0, is_drum=True)
    d.notes = [pretty_midi.Note(100, 38, k * T, k * T + 0.1) for k in snare_beats] + \
              [pretty_midi.Note(100, 36, k * T, k * T + 0.1) for k in kick_beats]
    pm.instruments.append(d)
    if extra:
        g = pretty_midi.Instrument(program=29)
        g.notes = [pretty_midi.Note(100, 60, t, t + 0.1) for t in extra]
        pm.instruments.append(g)
    return pm


def test_drum_bar_phase_finds_backbeat():
    # 박 1, 3, 5…에 스네어, 박 0, 4, 8…에 킥 → 마디 시작은 박 0
    start, scores = drum_bar_phase(drum_midi(range(1, 32, 2), range(0, 32, 4)), np.arange(0, 33) * 0.5, 4)
    assert start == 0 and scores[0] == pytest.approx(1.5)
    # 스네어가 0, 2, 4…(Beat This! 기준 1·3박)에 오면 시작이 한 박 옮겨진다
    start, _ = drum_bar_phase(drum_midi(range(0, 32, 2), range(3, 32, 4)), np.arange(0, 33) * 0.5, 4)
    assert start == 3


def test_drum_bar_phase_without_drums():
    assert drum_bar_phase(make_midi([(60, 0.5, 1.0)]), np.arange(0, 10) * 0.5, 4) == (0, {})


def test_auto_shift_fixes_wrong_downbeat_and_can_be_disabled():
    beats = np.arange(0, 33) * 0.5
    pm = drum_midi(range(0, 32, 2), range(3, 32, 4))          # Beat This! 다운비트(박 0)가 실제로는 4박
    _, r = align_pretty_midi(pm, beats, beats[::4])
    assert r.downbeat_shift == -1 and r.beat_offset == 1
    _, r = align_pretty_midi(pm, beats, beats[::4], auto_meter=False)
    assert r.downbeat_shift == 0 and r.beat_offset == 0
    _, r = align_pretty_midi(pm, beats, beats[::4], downbeat_shift=0)   # 직접 주면 그 값을 쓴다
    assert r.downbeat_shift == 0


def test_auto_shift_keeps_correct_downbeat():
    beats = np.arange(0, 33) * 0.5
    _, r = align_pretty_midi(drum_midi(range(1, 32, 2), range(0, 32, 4)), beats, beats[::4])
    assert r.downbeat_shift == 0


def _compound_song(T=0.6):
    """점4분음표 = 100 BPM(0.6 s) 12/8 곡. Beat This!가 절반 구간을 8분음표 2개(0.4 s)로 찍음.
    음은 8분음표(박의 1/3)마다."""
    slow = np.arange(0, 20) * T
    fast = 20 * T + np.arange(0, 31) * T * 2 / 3
    slow2 = 40 * T + np.arange(1, 21) * T
    det = np.concatenate([slow, fast, slow2])
    onsets = [k * T / 3 for k in range(0, 180)]
    return det, onsets


def test_beat_levels_and_triplet_share():
    det, onsets = _compound_song()
    v, level = beat_levels(det)
    assert v == pytest.approx(0.6, abs=0.01) and level > 0.3
    assert beat_levels(np.arange(0, 40) * 0.5)[1] == 0.0
    assert triplet_share([0.33, 0.67, 1.33, 1.67]) == 1.0
    assert triplet_share([0.25, 0.5, 0.75]) == 0.0
    assert triplet_share([0.0, 1.0]) == 0.0


def test_detect_compound():
    det, onsets = _compound_song()
    found, bpm, bar = detect_compound(det, onsets)
    assert found and bpm == pytest.approx(100, abs=2) and bar is None
    simple = np.arange(0, 60) * 0.5
    assert detect_compound(simple, [k * 0.125 for k in range(200)], simple[::4])[0] is False
    assert detect_compound([], [0.1]) == (False, 0.0, None)


def test_detect_compound_from_eighth_note_beats():
    # 점4분음표 = 0.9 s 겹박자를 Beat This!가 8분음표(0.3 s)마다 찍고, 다운비트를 6박마다 찍은 경우
    eighths = np.arange(0, 120) * 0.3
    found, bpm, bar = detect_compound(eighths, [k * 0.3 for k in range(100)], eighths[::6])
    assert found and bpm == pytest.approx(60 / 0.9, abs=0.5) and bar == 2
    # 같은 6박 마디라도 박이 느리면(4분음표 박의 6/4) 겹박자로 보지 않는다
    quarters = np.arange(0, 60) * 0.6
    assert detect_compound(quarters, [k * 0.6 for k in range(50)], quarters[::6])[0] is False


def test_eighth_note_beats_become_six_eight():
    eighths = np.arange(0, 120) * 0.3
    out, r = align_pretty_midi(make_midi([(60, k * 0.3, k * 0.3 + 0.2) for k in range(100)]), eighths, eighths[::6])
    ts = out.time_signature_changes[0]
    assert r.compound and (ts.numerator, ts.denominator) == (6, 8)
    assert r.bpm == pytest.approx(60 / 0.9, abs=0.5)


def test_fix_beats_counts_one_third_intervals():
    det = np.concatenate([np.arange(0, 5) * 0.9, 3.6 + np.arange(1, 31) * 0.3])   # 점4분음표 4간격, 이어서 8분음표 30개
    new, _ = fix_beats(det, [], 60 / 0.9)
    assert np.allclose(new, np.arange(0, 15) * 0.9, atol=1e-6)


def test_auto_compound_end_to_end():
    det, onsets = _compound_song()
    out, r = align_pretty_midi(make_midi([(60, t, t + 0.1) for t in onsets]), det, [0.0])
    assert r.compound and r.meter == "12/8"
    ts = out.time_signature_changes[0]
    assert (ts.numerator, ts.denominator) == (12, 8)
    _, r = align_pretty_midi(make_midi([(60, t, t + 0.1) for t in onsets]), det, [0.0], auto_meter=False)
    assert not r.compound and r.meter == "4/4"


def test_cli_no_auto_meter(tmp_path, capsys):
    from align import main, save_beats
    beats = list(np.arange(0, 33) * 0.5)
    drum_midi(range(0, 32, 2), range(3, 32, 4)).write(str(tmp_path / "in.mid"))
    save_beats(tmp_path / "b.json", beats, beats[::4])
    args = ["--midi", str(tmp_path / "in.mid"), "--beats", str(tmp_path / "b.json"), "--out", str(tmp_path / "o.mid")]
    assert main(args) == 0 and "bar shift -1" in capsys.readouterr().out
    assert main(args + ["--no-auto-meter"]) == 0 and "bar shift" not in capsys.readouterr().out


# ----------------------------------------------------------------------
# 드럼 기준 타이밍 보정 (align_midi에서 기본으로 켜짐)
# ----------------------------------------------------------------------
def test_align_midi_runs_drum_sync_by_default(tmp_path, capsys):
    from align import main, save_beats
    beats = np.arange(0, 33) * 0.5
    pm = pretty_midi.PrettyMIDI()
    d = pretty_midi.Instrument(program=0, is_drum=True)
    d.notes = [pretty_midi.Note(100, 38, t, t + 0.1) for t in beats[1::2]] + \
              [pretty_midi.Note(100, 36, t, t + 0.1) for t in beats[::4]]
    g = pretty_midi.Instrument(program=29)
    g.notes = [pretty_midi.Note(100, 60, t + 0.07, t + 0.3) for t in beats[:-1]]   # 기타가 70 ms 늦음
    pm.instruments += [d, g]
    pm.write(str(tmp_path / "in.mid"))
    save_beats(tmp_path / "b.json", list(beats), list(beats[::4]))
    r = align_midi(tmp_path / "in.mid", tmp_path / "o.mid", beats=list(beats), downbeats=list(beats[::4]))
    assert r.drum_sync is not None and r.drum_sync.moved_notes == 32
    s16 = 0.125
    on = [round(n.start / s16, 3) for n in pretty_midi.PrettyMIDI(str(tmp_path / "o.mid")).instruments[1].notes]
    assert all(x == int(x) and int(x) % 4 == 0 for x in on)                    # 모두 박 위로
    r = align_midi(tmp_path / "in.mid", tmp_path / "o2.mid", beats=list(beats), downbeats=list(beats[::4]),
                   drum_sync=False)
    assert r.drum_sync is None
    args = ["--midi", str(tmp_path / "in.mid"), "--beats", str(tmp_path / "b.json"), "--out", str(tmp_path / "o3.mid")]
    assert main(args) == 0 and "drum sync 32 notes" in capsys.readouterr().out
    assert main(args + ["--no-drum-sync"]) == 0 and "drum sync" not in capsys.readouterr().out
