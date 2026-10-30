# guitar_tab — skyline 리드/리듬 분리 + TAB (비교 기준선)

MuScriptor는 기타 두 대를 한 파트로 합쳐 채보하는 경우가 많아서, 그대로 TAB으로 바꾸면 손이 닿지 않는 운지가 나옵니다.
이 스크립트는 기타 파트가 두 대인지 판단해서, 두 대면 리드와 리듬으로 나누고 한 대면 그대로 두고, 각 파트를 칠 수 있는 TAB으로 만듭니다.

**비교 기준선(baseline)입니다.** 팀의 guitar-guitar 분리 모듈을 대신하지 않고, 그 결과를 같은 지표로 비교하기 위한 출발점입니다.

```
beat_align 출력 MIDI ─▶ 조율 결정 ─▶ 두 대인가? ─┬─ 예 ─▶ skyline 분리 ─▶ 화음 줄이기 ─▶ tuttut 운지 ─▶ .gp5 / .txt / .mid
                                               └─ 아니오 ──────────────▶ 화음 줄이기 ─▶ tuttut 운지 ─▶ .gp5 / .txt / .mid
```

## 동작

1. **조율:** 기타 음의 99% 이상이 들어가는 조율을 표준 → 반음 내림 → Drop D 순서로 고릅니다. 그래도 음역 밖인 음은 옥타브를 옮깁니다.
2. **두 대인지 판단 (자동 모드, 기본):** 아래 "두 대로 나눌지 정하는 규칙"을 보세요 (`decide_split`). `--split always`면 항상 나누고, `--split never`면 나누지 않습니다.
3. **skyline 분리 (두 대일 때):** 같은 시각에 시작하는 음 중 가장 높은 음을 리드로, 나머지를 리듬으로 보냅니다. 리드는 단선율로 만듭니다(다음 리드 음에서 끊음).
4. **화음 줄이기 (기본):** 리듬 파트, 합쳐진 상태 파트, 한 대 파트의 화음은 최대 6음, 개방현을 뺀 운지가 4프렛 안에 들어가야 합니다. 안 되면 가장 낮은 음과 가장 높은 음은 남기고 가운데 음부터 뺍니다. 같은 시각에 같은 음이 겹치면 하나로 합칩니다. `--no-chord-reduction`을 주면 화음을 줄이지 않습니다.
5. **운지:** [tuttut](https://github.com/natecdr/tuttut)(HMM + Viterbi)로 줄·프렛을 고릅니다. 손 이동 벌점 `b=0.1` (기본값 1보다 이동을 강하게 막음).
6. **출력:** MIDI, 텍스트 TAB, Guitar Pro 파일(.gp5). .gp5에는 tuttut가 고른 줄·프렛이 그대로 들어가고, 박자표는 입력 MIDI를 따릅니다(4/4, 12/8 등).

### 두 대로 나눌지 정하는 규칙

MuScriptor는 원곡의 기타 두 대를 한 트랙으로 합쳐 채보하기도 하고, 반대로 한 대가 친 화음에 음을 더 붙이기도 합니다. 그래서 기타 트랙 수만 보고는 두 대인지 알 수 없고, 채보된 음을 직접 봐야 합니다.

먼저 같은 순간에 시작하는 음들을 한 묶음으로 보고, 이 묶음을 기타 한 대로 잡을 수 있는지 확인합니다. 한 줄에 한 음씩, 개방현을 뺀 손가락 위치가 4프렛 안에 들어가야 잡을 수 있다고 봅니다. 이 검사는 화음을 줄이기 전에 합니다. 화음을 줄이고 나면 모든 묶음이 잡을 수 있게 바뀌기 때문입니다.

잡을 수 없는 묶음이 많다고 해서 곧바로 두 대라고 볼 수는 없습니다. 한 대가 친 화음에 음이 몇 개 더 붙어도 잡을 수 없게 되기 때문입니다. 그래서 묶음의 가장 낮은 음과 가장 높은 음이 2옥타브 넘게 벌어져 있는지도 봅니다. 기타 한 대로 한꺼번에 잡는 화음은 보통 6번 줄 개방현(E2)에서 1번 줄 개방현(E4)까지, 즉 2옥타브 안에 들어갑니다. 그보다 넓은 묶음이 자주 나오면 낮은 음역의 리듬 기타와 높은 음역의 리드 기타가 동시에 치고 있다는 뜻입니다.

두 조건을 모두 만족할 때만 두 대로 나눕니다. 잡을 수 없는 묶음이 5% 이상이고 2옥타브 넘게 벌어진 묶음이 6% 이상이면, skyline으로 리드와 리듬을 나눈 뒤 각각 tuttut로 운지를 정합니다. 그렇지 않으면 한 대로 보고, 화음 줄이기(최대 6음, 4프렛 안)만 한 뒤 바로 tuttut로 운지를 정합니다.

기준값은 원곡 기타 구성을 확인한 11곡으로 정했습니다 (2026-10-30). 서로 다른 파트를 치는 기타 두 대 곡은 2옥타브 초과 비율이 모두 8.3% 이상, 기타 한 대 곡은 모두 4.2% 이하였습니다. 같은 곡들로 기준을 정하고 확인했기 때문에, 새 곡에서도 맞는지는 계속 확인해야 합니다.

| 곡 | 원곡 기타 | 잡을 수 없는 묶음 | 2옥타브 초과 | 판정 |
|---|---|---|---|---|
| 한 페이지가 될 수 있게 | 2대 | 29.0% | 11.8% | 나눔 |
| Heavy Is the Crown | 2대 | 14.6% | 23.8% | 나눔 |
| 흰수염고래 | 2대 | 14.2% | 10.4% | 나눔 |
| Sweet Child O' Mine | 2대 | 9.6% | 13.0% | 나눔 |
| Time-Bomb | 2대 (같은 파트가 많음) | 6.6% | 9.3% | 나눔 |
| Rain | 확인 안 됨 | 10.7% | 7.1% | 나눔 |
| Yoru ni Kakeru | 1대 | 9.3% | 4.2% | 한 대 |
| Holding Out For A Hero | 1대 | 8.4% | 4.1% | 한 대 |
| High | 1대 | 1.0% | 0.2% | 한 대 |
| 21 Guns | 어쿠스틱 + 일렉 (같은 화음) | 0.6% | 1.9% | 한 대 |
| 적재 - 우연을 믿어요 (Demucs) | 확인 안 됨 | 0.4% | 0.6% | 한 대 |

skyline 규칙은 멜로디 추출 연구의 기준선에서 가져왔습니다. 조율 결정, 화음 줄이기(4프렛), 건너뜀 지표(5프렛)는 이번에 정한 규칙이라 문헌 근거가 없습니다.

## 설치

```bash
cd guitar_tab
pip install -r requirements.txt
pip install --no-deps tuttut==0.0.6   # tuttut의 옛 버전 고정(numpy 1.23 등)이 Python 3.12+에서 설치되지 않음
```

## 사용법

```bash
python skyline_tab.py "song_aligned.mid" out/song/              # 자동 모드: 두 대면 리드·리듬 + 합쳐진 상태 TAB, 한 대면 기타 TAB 하나
python skyline_tab.py "song_aligned.mid" out/song/ --no-merged   # 두 대일 때 합쳐진 상태 TAB은 건너뜀
python skyline_tab.py "song_aligned.mid" out/song/ --split always  # 항상 리드·리듬으로 나눔 (이전 동작)
python skyline_tab.py "song_aligned.mid" out/song/ --split never   # 항상 한 대로
python skyline_tab.py "song_aligned.mid" out/song/ --no-chord-reduction  # 화음을 줄이지 않음 (큰 곡은 1시간 이상)
python verify_gp5.py "out/song/song - skyline lead+rhythm.gp5" out/song/skyline_lead_rhythm.mid
```

출력 (`out/song/`):

| 파일 | 내용 |
|---|---|
| `곡명 - skyline lead+rhythm.gp5` | (두 대) 리드·리듬 두 트랙 TAB. MuseScore, TuxGuitar, Guitar Pro로 열기 |
| `곡명 - guitar.gp5`, `guitar.mid`, `tab_guitar.txt` | (한 대) 기타 한 트랙 TAB, 화음을 줄인 MIDI, 텍스트 TAB |
| `곡명 - merged.gp5` | 나누기 전 합쳐진 상태의 TAB (`--no-merged`면 없음) |
| `skyline_lead_rhythm.mid` | 리드·리듬 두 트랙 MIDI |
| `tab_lead.txt`, `tab_rhythm.txt`, `tab_merged.txt` | 텍스트 TAB |

MIDI에는 줄·프렛 정보가 없어서, MuseScore에서 MIDI를 TAB 보표로 바꾸면 MuseScore가 운지를 새로 정합니다. 이 스크립트의 운지를 보려면 `.gp5`를 여세요.

## 결과 (`results/`, 10곡)

입력은 `ml/beat_align`으로 정렬한 MuScriptor large 출력(10곡 테스트셋)입니다.

**이 결과는 자동 모드와 화음 줄이기 기본 적용 전에 만들었습니다.** 10곡 모두 리드·리듬으로 나눴고(지금의 `--split always`), 표의 "합쳐진 상태"는 화음을 줄이지 않은 TAB입니다(지금의 `--no-chord-reduction`). 지금 코드로 다시 돌리면 한 대로 판정되는 곡(Yoru ni Kakeru, Holding Out For A Hero, High, 21 Guns)은 기타 TAB 하나로 나옵니다. 곡별 폴더에는 `.gp5`와 텍스트 TAB이 있고, 전체 숫자는 `results/summary.csv`에 있습니다.

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
- Rain, Holding Out For A Hero는 합쳐진 상태 TAB 계산이 너무 오래 걸려(1시간 이상) `--no-merged`로 돌렸습니다. 이 때문에 합쳐진 상태 파트에도 화음 줄이기를 기본으로 넣었습니다. 예: 한 기타 트랙에 4366음인 곡에서 화음을 줄이지 않으면 15분 넘게 끝나지 않았고, 줄이면 리드·리듬·합쳐진 상태를 합쳐 1분 안에 끝났습니다(화음 안 음의 약 10%가 빠짐).
- 모든 .gp5를 `verify_gp5.py`로 확인했습니다: 음 높이가 MIDI와 전부 같고, 마디 길이 오류와 4프렛을 넘는 화음이 없습니다.

## 한계

- 반주만 나오는 구간에서는 반주 화음의 맨 위 음이 리드로 가서, 리드가 반주 윗선을 따라 칩니다.
- 반주가 리프보다 높거나 두 기타가 같은 음역에서 교차하면 거꾸로 나뉩니다.
- 리드가 높은 프렛(17~20)에 놓이는 경우가 있습니다. 손 이동은 적지만 연주자들이 흔히 쓰는 위치와 다를 수 있습니다.
- 건너뜀 비율은 텍스트 TAB에서 잰 간이 지표라 실제 연주 난이도를 다 반영하지 않습니다.
- tuttut 계산은 동시음이 많을수록 급격히 느려집니다. 화음을 줄이면 곡당 몇 분 안이고, `--no-chord-reduction`이면 합쳐진 상태가 곡에 따라 1시간 이상 걸립니다.
- 화음 줄이기는 음을 뺍니다. 합쳐진 상태 TAB은 MIDI의 모든 음을 담지 않습니다.
- .gp5의 곡 제목은 cp1252만 저장되므로 한글 제목은 로마자로 씁니다(파일 이름은 한글 그대로).

## 테스트

```bash
python -m pytest -q --cov=skyline_tab --cov-report=term-missing
```

2026-10-30 기준: 57 passed, `skyline_tab.py` 커버리지 74%.
tuttut를 부르는 `tab()`과 `main()`은 단위 테스트에서 제외했습니다(TAB 객체는 가짜로 대신함). 10곡 실행과 `verify_gp5.py`로 통합 확인했습니다.
