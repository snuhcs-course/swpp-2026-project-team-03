from pathlib import Path
import mido

# 현재 Python 파일이 있는 폴더
BASE_DIR = Path(__file__).resolve().parent

# MIDI 파일 100개가 들어 있는 폴더
MIDI_DIR = BASE_DIR / "rwc-music rwc-annotations main 01_annotations_preprocessed-MIDI_aligned_RWC-P"

# 확인할 RWC 곡 번호 (1~100번 전체)
SONG_NUMBERS = list(range(1, 101))

valid_songs = []
invalid_songs = []
unknown_songs = []

print("=" * 65)
print("RWC MIDI 박자표 검사")
print("=" * 65)

for num in SONG_NUMBERS:

    song_id = f"RWC_P{num:03d}"
    midi_path = MIDI_DIR / f"{song_id}.mid"

    # 파일 존재 여부 확인
    if not midi_path.exists():
        print(f"⚠️ {song_id}: MIDI 파일을 찾을 수 없음")
        unknown_songs.append(song_id)
        continue

    # MIDI 파일 읽기
    midi = mido.MidiFile(str(midi_path))

    # 모든 트랙에서 박자표 이벤트 추출
    time_signatures = []

    for track in midi.tracks:
        for msg in track:
            if msg.type == "time_signature":
                ts = (msg.numerator, msg.denominator)
                time_signatures.append(ts)

    # 중복을 제외한 박자표 목록
    unique_signatures = list(dict.fromkeys(time_signatures))

    # 판정
    if not time_signatures:
        status = "⚠️ 박자표 정보 없음"
        unknown_songs.append(song_id)

    elif all(ts == (4, 4) for ts in time_signatures):
        status = "✅ 전체 4/4"
        valid_songs.append(song_id)

    else:
        status = "❌ 변박 포함"
        invalid_songs.append(song_id)

    # 출력
    signature_text = ", ".join(
        f"{num}/{den}" for num, den in unique_signatures
    )

    print(f"{song_id:<10} | {status:<12} | {signature_text}")


# 최종 요약
print("\n" + "=" * 65)
print("최종 결과")
print("=" * 65)

print(f"\n✅ 전체 4/4 곡 ({len(valid_songs)}개)")
print(", ".join(valid_songs) if valid_songs else "없음")

print(f"\n❌ 변박 포함 곡 ({len(invalid_songs)}개)")
print(", ".join(invalid_songs) if invalid_songs else "없음")

print(f"\n⚠️ 확인 불가 ({len(unknown_songs)}개)")
print(", ".join(unknown_songs) if unknown_songs else "없음")