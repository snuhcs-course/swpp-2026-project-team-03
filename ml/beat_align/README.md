# beat_align — Beat This! 박자 정렬

MuScriptor가 쓴 MIDI는 템포가 기본값 120 BPM이고 박자표가 없어서, 마디선이 실제 음악과 맞지 않습니다.
이 모듈은 [Beat This!](https://github.com/CPJKU/beat_this)로 원곡의 박·다운비트를 찾고, 모든 음표를 그 박 위로 옮겨 **템포 하나 + 박자 하나**의 MIDI로 다시 씁니다. 박자는 다운비트 사이의 박 수로 정합니다.

```
Song ─┬─ Demucs ─ MuScriptor ─┐
      └─ Beat This! ──────────┴─▶ beat_align ─▶ MIDI-GPT / Render
```

## 동작

1. 원곡 오디오에서 박과 다운비트 시각(초)을 찾는다 (`detect_beats`)
2. **(자동) 겹박자 감지:** 박 간격에 "한 박"과 "그 2/3"이 둘 다 많고(10% 이상), 박 안의 음이 셋잇단 자리에 많으면(12% 이상) 12/8·6/8로 보고 박을 점4분음표 단위로 다시 센다 (`detect_compound` → `fix_beats`)
3. BPM: 박 간격 중앙값 ±8% 안의 간격 평균. 0.2 s 미만·2.0 s 초과 간격은 제외 (`estimate_bpm`)
4. 다운비트 사이의 박 수를 세어, 가장 많이 나온 값을 곡 전체의 마디당 박 수로 정한다 (`estimate_beats_per_bar`). 다운비트가 2개 미만이면 4
5. 첫 다운비트가 1마디 첫 박이 되도록 박 번호를 민다 (`compute_beat_offset`)
6. **(자동) 마디선 확인:** 드럼 MIDI의 스네어가 2·4박, 킥이 1박에 더 잘 오는 마디 시작이 있으면 그쪽으로 옮긴다 (`drum_bar_phase`, 점수가 0.25 이상 좋아질 때만)
7. 각 음표의 시작·끝을 박 좌표로 바꿔 16분음표(겹박자는 점4분음표의 1/6) 단위로 맞추고, 새 BPM 기준 초로 되돌린다
8. 길이가 0이 된 음표는 한 칸 길이로 늘리고, 정한 박자표(예: 4/4, 12/8)를 넣어 저장한다

자동 판별(2, 6)은 기본으로 켜져 있고 `--no-auto-meter`로 끕니다. 11곡(4/4 10곡, 12/8 1곡)에서 판매 악보의 박자표와 모두 맞았고, BPM 오차는 평균 0.4%였습니다 (2026-10-30).

## 설치

Python 3.10 이상.

```bash
cd beat_align
pip install -r requirements.txt
```

GPU를 쓰려면 CUDA 버전에 맞는 `torch`를 먼저 설치하세요. GPU가 없으면 자동으로 CPU에서 돕니다 (느림).

## 사용법

> 아래의 `song.wav`, `muscriptor.mid`, `song_aligned.mid` 등은 **예시 파일명**입니다. 실제 파일 경로로 바꿔 쓰면 됩니다 (예: `--audio "data/Sweet Child O Mine.wav"`). 경로에 공백이 있으면 따옴표로 감싸세요.

### 명령줄

```bash
# 원곡 오디오로 박을 찾아서 바로 보정
python align.py --midi muscriptor.mid --audio song.wav --out song_aligned.mid

# 찾은 박을 JSON으로 저장해 두기 (다음부터 모델 없이 재사용)
python align.py --midi muscriptor.mid --audio song.wav --out song_aligned.mid --save-beats song_beats.json

# 저장한 박 JSON으로 보정 (GPU·모델 불필요)
python align.py --midi muscriptor.mid --beats song_beats.json --out song_aligned.mid
```

옵션: `--device auto|cuda|cpu` (기본 `auto`)

### 여러 곡 한 번에 (일괄 처리)

```bash
# 원곡 오디오 폴더로 박을 찾아서 보정 (모델은 한 번만 불러옴)
python align.py --midi-dir muscriptor_outputs/ --audio-dir audio/ --out-dir aligned/

# 저장해 둔 박 JSON 폴더로 보정 (GPU·모델 불필요)
python align.py --midi-dir muscriptor_outputs/ --beats-dir beat_results/ --out-dir aligned/
```

- **매핑:** 곡 이름이 같은 MIDI와 오디오(또는 박 JSON)를 한 쌍으로 처리합니다.
  - MIDI 곡 이름: `midi-dir/곡.mid`이면 파일 이름, `midi-dir/곡/muscriptor_large.mid`(MuScriptor 출력 구조)이면 폴더 이름
  - 오디오: `곡.wav` (`.mp3 .flac .ogg .m4a`도 인식) · 박 JSON: `곡_beats.json` 또는 `곡.json`
  - 이름 끝의 `__no_vocals`(Demucs 출력)는 무시하고, 한글 파일명의 맥/윈도우 인코딩 차이도 맞춰 줍니다. 그래서 `곡.wav` 원곡과 `곡__no_vocals/muscriptor_large.mid`가 짝지어집니다.
- **출력:** `out-dir/곡_aligned.mid`. 오디오로 박을 찾았다면 `out-dir/곡_beats.json`도 저장합니다 (다음엔 `--beats-dir out-dir/`로 재사용).
- 한 곡이 실패해도 나머지는 계속 처리하고, 마지막에 성공·실패와 짝이 없는 파일을 알려 줍니다. 실패한 곡이 있으면 종료 코드 1.

```
[1/10] OK   21 Guns - Green Day · BPM 81.08 · 4/4 · notes 4392
...
완료: 성공 10 · 실패 0 / 짝지어진 곡 10
```

출력 예: `BPM 91.02 · 4/4 · notes 2841 · beat offset 3 → song_aligned.mid`

### Python

```python
from align import align_midi, detect_beats

# 오디오로 바로
result = align_midi("muscriptor.mid", "aligned.mid", audio_path="song.wav")
print(result.bpm, result.note_count)

# 박을 따로 구해서 (여러 MIDI에 재사용할 때)
beats, downbeats = detect_beats("song.wav")
align_midi("muscriptor.mid", "aligned.mid", beats=beats, downbeats=downbeats)
```

박 JSON 형식: `{"beats": [초, ...], "downbeats": [초, ...]}`

### 자동 판별을 끄거나 직접 정하는 옵션

자동 판별이 틀렸을 때, 판매 악보 등으로 템포와 박자를 알고 있을 때 씁니다. `--no-auto-meter`만 일괄 처리에서도 쓸 수 있고, 나머지는 한 곡 모드 전용입니다.

| 옵션 | 하는 일 | 언제 |
|---|---|---|
| `--no-auto-meter` | 겹박자 감지와 드럼 기준 마디선을 끈다 | 자동 판별 결과가 이상할 때 비교용 |
| `--bpm 108` | 박 간격이 실제 박의 1배·2/3배·1/2배·2배 중 어디인지 보고, 박을 이 템포로 다시 센다 (`fix_beats`) | Beat This!가 일부 구간을 1.5배·2배로 찍어서 템포가 틀어질 때 |
| `--compound` | (자동 판별 대신) 한 박을 점4분음표로 보고 16분음표 6칸(8분음표 3칸)으로 맞춘다. 박자표는 n/8 (4박 → 12/8, 2박 → 6/8), MIDI 템포는 4분음표 기준이라 x1.5 | 12/8, 6/8 곡. `--bpm`은 점4분음표 기준 |
| `--triplets` | 박마다 16분음표 칸과 셋잇단 8분음표 칸 중 음들에 확실히 더 맞는 쪽을 고른다 (`choose_triplet_beats`) | 4/4 곡 안에 셋잇단이 섞여 있을 때. `--compound`와 같이 쓰면 무시 |
| `--downbeat-shift -1` | (자동 판별 대신) 마디선을 박 단위로 옮긴다 (+1 한 박 늦게, -1 한 박 일찍) | Beat This!가 마디 첫 박을 다른 박에 찍었을 때 (예: 스네어가 1·3박에 옴) |

```bash
# 적재 - 우연을 믿어요 (판매 악보: 12/8, 점4분음표 = 108). 옵션 없이 자동으로:
python align.py --midi jaejae.mid --beats jaejae_beats.json --out jaejae_aligned.mid
# BPM 107.85 · 12/8 (dotted quarter = 107.85) · notes 4451 · beat offset 1 · bar shift -1 → jaejae_aligned.mid
# 같은 결과를 직접 지정하면:
python align.py --midi jaejae.mid --beats jaejae_beats.json --out jaejae_aligned.mid --bpm 108 --compound --downbeat-shift -1
```

`--bpm`의 박 다시 세기는 같은 배수가 3개 이상 이어진 구간만 믿고, 구간 사이의 애매한 간격은 세지 않습니다. 대신 지금까지 센 정박으로 맞춘 직선(시각 = t0 + 번호 x 한 박)으로 다음 구간의 시작 번호를 정해서, 애매한 간격이 쌓여도 박 위치가 밀리지 않게 합니다.

## 입력 주의

- **`--audio`에는 보컬을 지우기 전 원곡을 넣습니다.** 
- MIDI는 MuScriptor 출력처럼 초 단위 시간이 실제 오디오와 맞는 파일이어야 합니다.

## 한계

- 곡 전체를 **템포 하나, 박자 하나**로 가정합니다. 템포가 바뀌거나 곡 중간에 박자가 바뀌는 곡은 마디가 어긋날 수 있습니다.
- 박자는 다운비트 사이 박 수의 최빈값입니다. Beat This!가 다운비트를 가끔 더 찍거나 놓쳐도 결과는 흔들리지 않지만, 진짜 변박은 따라가지 못합니다.
  - 마디마다 다운비트 간격을 박자로 쓰는 방식도 10곡으로 시험했지만, 잘못 찍힌 다운비트 때문에 4/4 곡 사이에 2/4·1/4·7/4 마디가 수십 개씩 생겨 쓰지 않았습니다 (2026-10-23).
- 겹박자 감지 기준(10%, 12%)은 12/8 곡 하나(적재)로 정했습니다. 6/8, 12/8 곡을 더 모아 확인해야 합니다. Beat This!가 겹박자 곡을 처음부터 끝까지 한 단위로만 찍으면 "두 박 단위" 지표가 낮아 놓칠 수 있습니다.
- 드럼 기준 마디선은 스네어 2·4박 백비트를 가정합니다. 드럼이 없거나 킥·스네어가 박 위에 잡히지 않는 곡(예: High)은 Beat This! 마디선을 그대로 씁니다. 하프타임(스네어가 3박) 곡은 잘못 옮길 수 있습니다.
- 셋잇단이 섞인 4/4 곡은 자동으로 처리하지 않습니다 (`--triplets`를 직접 써야 함).
- `--bpm`, `--compound`, `--triplets`, `--downbeat-shift`는 곡마다 정해야 해서 일괄 처리에서는 쓸 수 없습니다.
- `--triplets`는 박 단위로 고르므로, 한 마디 안에서 16분음표 박과 셋잇단 박이 섞여 악보가 복잡해질 수 있습니다.
- 첫 박 이전의 음표는 0초로 붙습니다.

## 테스트

모델 없이 가짜 박 배열로 박자 추정, 보정 로직, 일괄 처리, 곡별 옵션, 자동 판별을 검사합니다 (60개).

```bash
python -m pytest -q --cov=align --cov-report=term-missing
```

2026-10-30 기준: 60 passed, `align.py` 커버리지 95%.
테스트하지 않는 부분은 Beat This! 모델을 실제로 부르는 `detect_beats()`와 CLI의 `--audio` 경로입니다. GPU와 모델 다운로드가 필요해서 단위 테스트에서 제외했고, 통합 테스트에서 다룰 예정입니다.

## 노트북에서 바뀐 점

`beat_this.ipynb` (Colab)의 `correct_midi()` 로직을 그대로 옮겼고, 아래만 바꿨습니다.

동일성 확인 (2026-10-21): `10곡 test`의 MuScriptor MIDI 10곡과 Colab에서 저장한 Beat This! 박 JSON으로 `python align.py --midi-dir ... --beats-dir ...`를 돌려, Colab 노트북이 만든 `corrected_midi/`와 비교 → 10/10곡에서 음표(악기·음높이·시작·끝·세기)와 템포가 완전히 일치.

| 노트북 | 모듈 |
|---|---|
| Google Drive 마운트, 고정 경로, zip·파일명 규칙 | 경로를 인자로 받음 |
| `device="cuda"` 고정 | `auto` (GPU 없으면 CPU) |
| 셀 전역 변수(`beat_results`, `matched_songs`)에 의존 | 함수 하나로 import 가능 |
| `__no_vocals.wav`로 박 검출 | 원곡 오디오로 박 검출 |
| 셀에서 10곡 일괄 처리 | `--midi-dir` 일괄 처리 (모델 한 번만 로드) |
| 테스트 없음 | pytest 21개 |
