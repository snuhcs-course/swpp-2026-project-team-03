# guitar_tab — skyline 리드/리듬 분리 + TAB (비교 기준선)

MuScriptor는 기타 두 대를 한 파트로 합쳐 채보하는 경우가 많아서, 그대로 TAB으로 바꾸면 손이 닿지 않는 운지가 나옵니다.
이 스크립트는 합쳐진 기타 파트를 리드와 리듬으로 나누고, 각 파트를 칠 수 있는 TAB으로 만듭니다.

**비교 기준선(baseline)입니다.** 팀의 guitar-guitar 분리 모듈을 대신하지 않고, 그 결과를 같은 지표로 비교하기 위한 출발점입니다.

```
beat_align 출력 MIDI ─▶ 조율 결정 ─▶ skyline 분리 ─▶ 화음 줄이기 ─▶ tuttut 운지 ─▶ .gp5 / .txt / .mid
```

## 동작

1. **조율:** 기타 음의 99% 이상이 들어가는 조율을 표준 → 반음 내림 → Drop D 순서로 고릅니다. 그래도 음역 밖인 음은 옥타브를 옮깁니다.
2. **skyline 분리:** 같은 시각에 시작하는 음 중 가장 높은 음을 리드로, 나머지를 리듬으로 보냅니다. 리드는 단선율로 만듭니다(다음 리드 음에서 끊음).
3. **화음 줄이기:** 리듬 화음은 최대 6음, 개방현을 뺀 운지가 4프렛 안에 들어가야 합니다. 안 되면 가장 낮은 음과 가장 높은 음은 남기고 가운데 음부터 뺍니다.
4. **운지:** [tuttut](https://github.com/natecdr/tuttut)(HMM + Viterbi)로 줄·프렛을 고릅니다. 손 이동 벌점 `b=0.1` (기본값 1보다 이동을 강하게 막음).
5. **출력:** 리드·리듬 두 트랙 MIDI, 텍스트 TAB, Guitar Pro 파일(.gp5). .gp5에는 tuttut가 고른 줄·프렛이 그대로 들어갑니다.

skyline 규칙은 멜로디 추출 연구의 기준선에서 가져왔습니다. 조율 결정, 화음 줄이기(4프렛), 건너뜀 지표(5프렛)는 이번에 정한 규칙이라 문헌 근거가 없습니다.

## 설치

```bash
cd guitar_tab
pip install -r requirements.txt
pip install --no-deps tuttut==0.0.6   # tuttut의 옛 버전 고정(numpy 1.23 등)이 Python 3.12+에서 설치되지 않음
```

## 사용법

```bash
python skyline_tab.py "song_aligned.mid" out/song/            # 합쳐진 상태 TAB까지 (비교용)
python skyline_tab.py "song_aligned.mid" out/song/ --no-merged # 리드·리듬만 (빠름)
python verify_gp5.py "out/song/song - skyline lead+rhythm.gp5" out/song/skyline_lead_rhythm.mid
```

출력 (`out/song/`):

| 파일 | 내용 |
|---|---|
| `곡명 - skyline lead+rhythm.gp5` | 리드·리듬 두 트랙 TAB. MuseScore, TuxGuitar, Guitar Pro로 열기 |
| `곡명 - merged.gp5` | 나누기 전 합쳐진 상태의 TAB (`--no-merged`면 없음) |
| `skyline_lead_rhythm.mid` | 리드·리듬 두 트랙 MIDI |
| `tab_lead.txt`, `tab_rhythm.txt`, `tab_merged.txt` | 텍스트 TAB |

MIDI에는 줄·프렛 정보가 없어서, MuseScore에서 MIDI를 TAB 보표로 바꾸면 MuseScore가 운지를 새로 정합니다. 이 스크립트의 운지를 보려면 `.gp5`를 여세요.

## 결과 (`results/`, 10곡)

입력은 `ml/beat_align`으로 정렬한 MuScriptor large 출력(10곡 테스트셋)입니다. 곡별 폴더에는 `.gp5`와 텍스트 TAB이 있고, 전체 숫자는 `results/summary.csv`에 있습니다.

리드·리듬 MIDI(`skyline_lead_rhythm.mid`)는 저장소 `.gitignore`가 `*.mid`를 제외해서 올리지 않았습니다. 필요하면 위 사용법대로 스크립트를 다시 돌리면 됩니다. MIDI는 실행 직후(곡당 1초 안에) 먼저 저장되고, TAB 계산은 그 뒤에 몇 분 걸립니다. `verify_gp5.py`로 검증할 때도 이 MIDI가 필요합니다.

손이 5프렛 넘게 건너뛰는 비율 (연속한 운지 위치 사이, 개방현 제외):

| 곡 | 합쳐진 상태 | 리드 | 리듬 |
|---|---|---|---|
| 한 페이지가 될 수 있게 - DAY6 | 10.8% | 0.6% | 0.9% |
| Sweet Child O Mine - Guns N Roses | 7.8% | 2.0% | 3.6% |
| 흰수염고래 - YB | 3.0% | 0.9% | 2.1% |
| Yoru ni Kakeru - YOASOBI | 1.5% | 0.6% | 1.9% |
| Time-Bomb - All Time Low | 1.5% | 1.1% | 1.8% |
| High - 5 Seconds of Summer | 1.3% | 1.1% | 5.7% |
| Heavy Is the Crown - Linkin Park | 1.0% | 1.2% | 0.8% |
| 21 Guns - Green Day | 0.4% | 0.7% | 0.0% |
| Rain - SID | — | 0.6% | 0.8% |
| Holding Out For A Hero - Bonnie Tyler | — | 2.1% | 0.7% |

- 합쳐진 상태가 칠 수 없던 곡(DAY6, Sweet Child O Mine, 흰수염고래)은 나누면 크게 좋아집니다. 원래 1% 안팎인 곡은 나눠도 비슷하거나 나빠질 수 있습니다(High 리듬).
- Rain, Holding Out For A Hero는 합쳐진 상태 TAB 계산이 너무 오래 걸려(1시간 이상) `--no-merged`로 돌렸습니다.
- 모든 .gp5를 `verify_gp5.py`로 확인했습니다: 음 높이가 MIDI와 전부 같고, 마디 길이 오류와 4프렛을 넘는 화음이 없습니다.

## 한계

- 반주만 나오는 구간에서는 반주 화음의 맨 위 음이 리드로 가서, 리드가 반주 윗선을 따라 칩니다.
- 반주가 리프보다 높거나 두 기타가 같은 음역에서 교차하면 거꾸로 나뉩니다.
- 리드가 높은 프렛(17~20)에 놓이는 경우가 있습니다. 손 이동은 적지만 연주자들이 흔히 쓰는 위치와 다를 수 있습니다.
- 건너뜀 비율은 텍스트 TAB에서 잰 간이 지표라 실제 연주 난이도를 다 반영하지 않습니다.
- tuttut 계산은 동시음이 많을수록 급격히 느려집니다. 리드·리듬은 곡당 몇 분, 합쳐진 상태는 곡에 따라 1시간 이상.
- .gp5의 곡 제목은 cp1252만 저장되므로 한글 제목은 로마자로 씁니다(파일 이름은 한글 그대로).

## 테스트

```bash
python -m pytest -q --cov=skyline_tab --cov-report=term-missing
```

2026-10-23 기준: 46 passed, `skyline_tab.py` 커버리지 76%.
tuttut를 부르는 `tab()`과 `main()`은 단위 테스트에서 제외했습니다(TAB 객체는 가짜로 대신함). 10곡 실행과 `verify_gp5.py`로 통합 확인했습니다.
