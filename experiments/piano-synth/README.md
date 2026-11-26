# 피아노·신스 채보와 연주 가능 MIDI 실험

GPU05에서 수행한 ROCKY 개발 실험의 **실행 당시 Python 코드**와 방법 요약이다. 운영 파이프라인에 연결하거나 모델을 재학습한 변경은 아니다. 원곡, 분리 stem, 곡별 명단, 채보·출력 MIDI, 로그, 자격 증명은 이 브랜치에 포함하지 않는다. 기타 개수 독립 시험 세트는 사용하지 않았다.

## 공통 입력과 처리

70곡 개발 입력에서 BS-RoFormer가 만든 `piano.wav`와 `other.wav`는 프레임 수·샘플레이트·채널 수가 같음을 확인한 후 샘플별로 더했다. MuScriptor 악기 힌트는 다음과 같다.

| 입력 | MuScriptor 악기 힌트 | MIDI 계약 |
| --- | --- | --- |
| `other.wav` | `synth_strings`, `synth_lead`, `synth_pad`, `brass_section` | 4개 라벨/GM 프로그램을 유지하는 MIDI |
| `piano.wav + other.wav` | `acoustic_piano`, `electric_piano`, `organ`, 위 신스 후보 4종 | 7개 라벨/GM 프로그램을 유지하는 MIDI |

라벨 유지 단계는 MuScriptor 채보 → `rule_gates.gate_stem`으로 소리가 약한 구간의 음표 제거 → `align.detect_beats`와 `align.align_midi`로 Beat This! 박 정렬 순서다. **초기 70곡 출력에는 별도의 드럼 기준 음 시각 보정이 없었다.** 라벨 유지 MIDI에는 한 사람이 연주하기 위한 두 손 제한을 적용하지 않았다. `brass_section`은 이 실험에서 신스 후보 힌트로 지정한 라벨이며, 음원의 실제 합성 방식이 확인된 것은 아니다.

후속 연주 가능 출력은 정렬된 7악기 음표를 단일 GM program 0 건반 트랙으로 축약한다. 소스 라벨은 선택·점수 계산과 상태 기록에 쓰며 최종 단일 트랙에는 남지 않는다. 지속음까지 포함해 손당 동시 최대 5음, 손당 14반음 범위, 전체 동시 최대 10음으로 제한한다. 이는 악보의 실제 연주 품질을 보증하는 검사가 아니다.

## 실험별 코드와 차이

| 단계 | 코드 | 대상·출력 | 핵심 규칙 |
| --- | --- | --- | --- |
| stem 준비 | `01_separation/batch_separate.py` | 개발 70곡, piano/other WAV | 기존 BS-RoFormer 분리를 독립 실행 |
| Other 단독 | `02_transcription/other_transcribe_20261124.py` | 70곡, 4라벨 MIDI | other stem 채보·약음 제거·박 정렬 |
| Piano+Other | `02_transcription/piano_other_transcribe_20261124.py` | 70곡, 7라벨 MIDI | 두 stem 합성 후 채보·약음 제거·박 정렬 |
| 초창기 연주 가능 축약 | `03_playable_baselines/piano_other_playable_20261124.py`, `piano_other_priority_by_bar_20261124.py` | 70곡, 단일 건반 MIDI | 전 악기 병합 또는 마디별 피아노 계열 우선. 피아노 계열이 없는 마디에서 신스 후보 사용 |
| 실험 5: 연주 분량·반복음 | `04_duration_repeat/piano_other_duration_priority_20261125.py` | 70곡, 단일 건반 MIDI | 원시 채보의 악기별 **발음 시간 합집합/곡 길이**로 전곡 우선순위를 정함. 같은 음높이 3회 이상 반복하는 리프 후보에 가산점 0.35. 충돌 시 점수와 두 손 제한으로 선별 |
| 라이브 확장 | `04_duration_repeat/live_three_duration_priority.py` | 추가 3곡, 단일 건반 MIDI | 같은 실험 5 규칙. 이 초기 출력에도 드럼 기준 보정은 없음 |
| 드럼 보정 재실행 | `05_drum_sync/run.py` | 70+3곡, 드럼 보정 7라벨 MIDI와 실험 5 축약 MIDI | 원곡을 다시 분리해 드럼만 채보·약음 제거. 7라벨 MIDI와 드럼 MIDI를 합쳐 `align_midi(..., drum_sync=True)` 실행 후 드럼 트랙 제거. Beat This!는 `no_vocals.wav` 사용 |
| 마디당 한 악기 | `06_bar_instrument/run.py` | 73곡, 두 변형 | `global_repeat`: 전곡 분량 G + 0.35×마디 반복음 비율. `global_local_repeat`: 0.6G + 0.4×**현재 마디** 분량 + 0.35×마디 반복음 비율. 점수 1위 악기만 마디에 선택 |
| 공통음·악기 간 음형 | `07_consensus_motif/run.py` | 73곡, 두 변형 | 위 마디 분량형을 바탕으로 서로 다른 악기에서 같은 음높이·50ms 이내 시작의 공통음 대표 1개를 추가. 두 번째 변형은 악기 간 반복 음형에도 0.35 가산 |
| 앞뒤 2마디·최대 2악기 | `08_core_local_window/run.py` | **핵심 24곡만**, 세 변형 | L은 현재 마디와 앞뒤 2마디의 발음 시간 비율. `all_labels_local`: 모든 라벨 병합, 음표 점수 0.6G+0.4L+반복음. `two_labels_global`: 마디당 G+반복음 상위 2라벨. `two_labels_local`: 마디당 0.6G+0.4L+반복음 상위 2라벨 |

여기서 G/L은 **음표 개수**가 아니라 해당 시간 구간에 악기가 실제로 울린 시간의 합집합 비율이다. 반복음 규칙은 중복·재타건 정리 후 같은 높이의 음이 4박 이내 3회 이상, 음 사이 0.375–2박 간격일 때 적용한다. 마디당 한·두 악기 변형은 마디 경계의 지속음을 분할한 뒤 악기를 선택한다. 공통음은 두 손 제약과 충돌하면 제거될 수 있다.

## 재현 계약

이 파일들은 GPU05의 원래 디렉터리와 마운트를 기대하는 **실행 당시 스냅샷**이다. 새 환경에서 그대로 실행하기 전에 입력을 준비하고 상단 경로 상수와 출력 위치를 별도 실험 경로로 지정해야 한다. 70곡 실행에는 `manifest.tsv`의 3열(`folder`, 내부 song ID, 원곡 확장자)을 사용한다. 핵심 24곡 실행에는 별도의 3열(`folder`, 내부 song ID, 표시 제목) manifest가 필요하다. 실제 명단과 원곡은 Git에 포함하지 않는다.

- GPU05 의존성: 기존 ROCKY Python 환경의 `pretty_midi`, `soundfile`, MuScriptor 모델, BS-RoFormer, `rule_gates.py`, `ml/beat_align/align.py`, `ml/guitar_tab/piano_playable.py`, Beat This! checkpoint. 새 모델 가중치나 운영 코드를 이 브랜치에 복사하지 않는다.
- Pod에서 `/experiment`에 스크립트를 마운트할 때 `04_duration_repeat/piano_other_duration_priority_20261125.py`를 같은 경로에 둔다. `07_consensus_motif/run.py`와 `08_core_local_window/run.py`는 `06_bar_instrument/run.py`를 `/experiment/bar_base.py`라는 이름으로도 필요로 한다.
- 인덱스별 실행 예: `python /experiment/piano_other_transcribe_20261124.py --start 1 --end 24`; `python /experiment/run.py --start 1 --end 24`. 후자의 `run.py`는 실행할 실험에 맞춰 하나만 마운트한다. 라이브 최초 실행 스크립트는 `--song L15|P03|P07`을 받는다. 73곡 실험은 1–70을 개발 곡, 71–73을 라이브 입력으로 해석한다. 핵심 창 실험은 1–24만 받는다.
- 단계별 입력: 원곡 → `01_separation`의 piano/other WAV → `02_transcription`의 `raw.mid`, `gated.mid`, `aligned.mid` → 축약 MIDI. `05_drum_sync`부터는 드럼 보정된 `raw.mid`·`aligned.mid`와 완료 상태를 후속 MIDI 편집의 입력으로 재사용한다. `06`–`08`은 분리·채보·박 정렬을 다시 실행하지 않는다.
- 실행 전에 코드·설정·모델과 입력의 해시를 기록한다. 곡별 `status.json`/요약에 성공·실패, 입력·출력 해시, 음표 수, 드럼 이동 수 또는 선택 라벨을 남기고 MIDI를 다시 읽어 두 손 제약을 검사한다. 실행은 새 Pod/ConfigMap/출력 경로에서만 한다.

## 검증, UAT, 롤백

기존 GPU05 실행의 **Alpha 기술 검증**: 드럼 보정 73곡은 세 Pod가 정상 종료했고 73개 상태가 완료였다. 7라벨 정렬 MIDI는 73개 모두 읽기·라벨 검사를 통과했다. 보정 가능한 음표가 있던 69곡에서 음 시각 이동이 있었고 4곡은 약음 제거 뒤 7라벨 음표가 0개였다. 실험 5 축약 MIDI 73개는 직렬화·재읽기·두 손 제한 감사를 통과했다. 이후 공통음/음형 변형은 146개 MIDI, 핵심 24곡 세 변형은 72개 MIDI의 읽기·두 손 감사가 통과했다. 핵심 두 악기 변형은 음표가 있는 모든 마디에서 선택 라벨 수 1–2개였다.

**Beta 청취·연주 UAT는 완료되지 않았다.** 대표 곡을 같은 구간에서 나란히 들어 박 맞음, 메인 멜로디·리프 보존, 악기 전환 자연스러움, 실제 두 손 연주 가능성을 평가해야 한다. 음표 수·해시·제약 통과는 음악 품질의 우열 근거가 아니다.

롤백은 새 축약 MIDI를 사용하지 않고 직전 드럼 보정 실험 5 MIDI 또는 기존 ROCKY 출력으로 선택을 되돌리는 것이다. 이 브랜치는 운영 배포를 변경하지 않으며, PVC의 기존 입력·결과 정리는 별도 영향 범위 확인이 필요하다.
