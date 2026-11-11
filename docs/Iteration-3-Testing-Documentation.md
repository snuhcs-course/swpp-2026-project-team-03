# ROCKY Iteration 3 — Unified Pipeline Testing Documentation

검증일: 2026-11-05 · 범위: Python 오케스트레이션, 연결 모듈의 파일 계약, SGS Pod 형식, 보관된 결과물

## 1. 기준과 범위

[Iteration 2 Testing Documentation](https://github.com/snuhcs-course/swpp-2026-project-team-03/wiki/Testing-Documentation)의 단위·통합·AI 모듈·인수 테스트 구분을 따른다. Wiki의 Iteration 2 실적(앱 unit 41개, UI 12개)은 **번들 데모**의 결과이며 아래의 실제 음원 처리 검증 수치에 합산하지 않는다. Wiki가 초안으로 둔 AI 평가 세트·임계값은 `ml/eval-set`의 `eval/README.md` (`7618d93`, 2026-11-03)에서 T1–T6으로 사전 선언되었다. 이번 문서는 실제 실행한 검사와 아직 실행하지 않은 평가를 구분한다.

이 저장소는 모듈을 하나의 Git 브랜치로 모두 merge한 형태가 아니다. `unified.py`는 SGS의 별도 경로에 설치한 beat alignment, guitar TAB, MIDI-GPT, GP5-to-PDF를 호출한다. 그러므로 오케스트레이터 테스트 통과만으로 해당 모델의 추론 품질이나 서버 설치 버전의 일치를 증명할 수 없다.

| 대상 | 확인한 ref | 관련 PR / 상태 (11/05) | 이번 검증 |
| --- | --- | --- | --- |
| unified 기준선 | `ml/unified-pipeline` `49c070d` | [#8 Pod 문서](https://github.com/snuhcs-course/swpp-2026-project-team-03/pull/8) → 이 브랜치, 열림 | pytest 21개 |
| 피아노 병합 통합 | `integration/piano-stem-merge` `a6c6290` | [#9](https://github.com/snuhcs-course/swpp-2026-project-team-03/pull/9) → unified, 열림; 원본 [#6](https://github.com/snuhcs-course/swpp-2026-project-team-03/pull/6) | 최신 연결 브랜치의 회귀 테스트에 포함 |
| 지연 시간·악기별 MP3 수정 | `perf/pipeline-latency` `736432a` | [#11](https://github.com/snuhcs-course/swpp-2026-project-team-03/pull/11) → piano 통합, 열림 | pytest 25개, 산출물 검사 도구 추가 |
| 박자 보정 | `ml/beat-alignment` `f09a0a9` | [#3](https://github.com/snuhcs-course/swpp-2026-project-team-03/pull/3), 열림 | pytest 72개 |
| 기타·베이스 TAB | `ml/guitar-tab` `bf84fe8` | [#7](https://github.com/snuhcs-course/swpp-2026-project-team-03/pull/7), 열림 | pytest 84개, 저장 GP5 운지 검사 |
| MIDI-GPT 진입점 | `feature/midigpt` `d8b12fe` | [#4](https://github.com/snuhcs-course/swpp-2026-project-team-03/pull/4), 열림 | `prep_song.py` 고정 MIDI 입력 smoke; 모델 추론 제외 |
| GP5 → PDF | `ml/gp5-to-pdf` `647e19c` | 별도 PR 없음 | JS 문법, 기존 PDF 18개 무결성·페이지 검사; 신규 웹 변환 제외 |

## 2. 환경과 재현 명령

로컬 Windows, Python 3.12.14, Node 24.22.1, Poppler `pdfinfo`에서 실행했다. 격리된 Python 환경에는 `pytest 8.4.2`, `pytest-cov 7.1.0`, `coverage 7.17.2`, `pretty_midi 0.2.11`, `mido 1.3.3`, `numpy 2.2.6`, `soundfile 0.13.1`, `PyGuitarPro 0.11`, `tuttut 0.0.6` (`--no-deps`), `networkx 3.7`, `matplotlib 3.11.2`, `PyYAML 6.0.3`을 사용했다. 모델 가중치와 자격 증명은 로컬 테스트에 사용하지 않았다.

브랜치별 checkout에서 다음을 실행한다. `tuttut`는 해당 브랜치 README의 Python 3.12 설치 지침대로 오래된 의존성 고정을 적용하지 않는다.

```powershell
python -m venv .test-venv
.\.test-venv\Scripts\python.exe -m pip install pytest==8.4.2 pytest-cov==7.1.0 pretty_midi==0.2.11 numpy==2.2.6 soundfile==0.13.1 PyGuitarPro==0.11 networkx==3.7 matplotlib==3.11.2 PyYAML==6.0.3
.\.test-venv\Scripts\python.exe -m pip install --no-deps tuttut==0.0.6

# ml/unified-pipeline 및 perf/pipeline-latency 각각에서
.\.test-venv\Scripts\python.exe -m pytest ml/pipeline/tests -q
# ml/beat-alignment에서
.\.test-venv\Scripts\python.exe -m pytest ml/beat_align/tests -q
# ml/guitar-tab에서
.\.test-venv\Scripts\python.exe -m pytest ml/guitar_tab/tests -q -rs
# ml/gp5-to-pdf에서
node --check ml/gp5_to_pdf/convert.js
```

최신 브랜치의 `tests/verify_iteration3_artifacts.py`는 읽기 전용이다. `--run`은 반복 지정할 수 있고 PDF 검증에는 `pdfinfo`, TAB 운지 검증에는 `PyGuitarPro`가 필요하다.

```powershell
$py = '.\.test-venv\Scripts\python.exe'
$results = 'C:\Users\USER\AndroidStudioProjects\rocky-validation-guitar2-score-fix-20261104'
$runs = @('tests/verify_iteration3_artifacts.py')
Get-ChildItem -LiteralPath $results -Directory | ForEach-Object { $runs += @('--run', $_.FullName) }
& $py @runs --tab-root $results
& $py tests/verify_iteration3_artifacts.py --run 'C:\Users\USER\AndroidStudioProjects\rocky-pipeline-performance-20261104\integrated_output' --gp5-manifest 'C:\Users\USER\AndroidStudioProjects\Rocky\ml\gp5_to_pdf\results\manifest.json'
# 별도로 checkout한 feature/midigpt 모듈 경로를 지정한다.
& $py tests/verify_midigpt_prep.py '<feature-midigpt checkout>\ml\midigpt'
```

MIDI-GPT의 고정 fixture smoke는 `classify(0,26,33,48)`와 드럼 분류, 가장 오래 지속되는 템포 선택, 한 곡의 `piano/guitar/bass/drums/other_00.mid` 분리 및 MIDI 재열기를 확인한다. 모델 추론은 호출하지 않는다.

Wiki 초안의 P1·P2·P4는 이 준비 단계 smoke와 대응하고, P5의 파트 추가·기존 트랙 보존은 unified pytest의 mock 통합 사례로 확인했다. P3의 정답 MIDI 대비 평가 지표 동일 입력 검사와 실제 모델의 생성 품질은 이번 로컬 실행 대상이 아니다.

## 3. 실행 결과

| 검사 | 결과 | 확인 내용 |
| --- | --- | --- |
| unified 기준선 pytest (`49c070d`) | **21/21 통과** | stem·lineup 분기, resume/실패 기록, 악보 발행 mock |
| 최신 연결 브랜치 pytest (`736432a`) | **25/25 통과** | 피아노 병합, 병렬 전사·출판, MP3용 MuseScore 악기 패치, 산출물 계약 mock |
| beat alignment pytest (`f09a0a9`) | **72/72 통과** | beat/downbeat 정렬, 드럼 기준 보정, MIDI fixture |
| guitar TAB pytest (`bf84fe8`) | **84/84 통과, skip 0** | skyline 분리, 운지·GP5 생성, 베이스, 피아노 처리; 의존성 설치 전의 2 skip은 설치 후 해소 |
| MIDI-GPT 준비 단계 | **통과** | 분류·템포·5개 파트 파일; 생성 모델 자체는 실행하지 않음 |
| `compileall` / `node --check` | **통과** | 최신 pipeline Python 문법 / GP5 변환 JS 문법 |
| SGS 활성 YAML 4개 | **통과** | 모두 `kind: Pod`, `ferrari`, 기존 PVC `/data` 마운트; GPU Pod는 GPU 1개 제한. `legacy/` Job은 적용 대상에서 제외 |
| `ml/gp5-to-pdf/results` | **18/18 통과** | 기존 변환 PDF의 SHA-256과 `pdfinfo` 페이지 수가 manifest와 일치 |
| 저장된 12곡 결과 (`rocky-validation-guitar2-score-fix-20261104`) | **12/12 파일 무결성 통과** | 총 PDF 80개·MP3 80개, MIDI 재열기, 각 파일 크기·SHA-256·PDF 페이지·MP3 헤더·출처 해시 |
| 저장된 1곡 지연 시간 실험 (`integrated_output`) | **1/1 파일 무결성 통과** | pipeline contract 10, PDF 7개·MP3 7개, MIDI 5트랙 |
| T6 기타·베이스 운지, 저장된 12곡 | **관측 범위에서 통과** | GP5 34개: 기타 onset 14,286개, 베이스 onset 7,451개; 불가능한 onset·음역 초과·베이스 화음 0개 |

### Python pipeline line coverage

`perf/pipeline-latency`의 pipeline 코드 commit `736432a`에서 같은 25개 테스트를 다시 실행해 측정했다. `pytest-cov`의 기본 합계는 **테스트 코드도 포함**하므로 목표 판정에 사용하지 않았다. 아래는 테스트 파일을 제외한 실행 가능한 Python 줄의 수치다. 모델 패키지 내부나 별도 브랜치 모듈은 이 분모에 포함되지 않는다.

| `ml/pipeline` 파일 | 실행된 줄 / 대상 줄 | Coverage |
| --- | ---: | ---: |
| `unified.py` | 390 / 452 | 86.3% |
| `publish_scores.py` | 301 / 362 | 83.1% |
| `separate_bs_roformer.py` | 102 / 122 | 83.6% |
| `transcribe_with_progress.py` | 63 / 71 | 88.7% |
| **현재 pipeline 실행 경로 4개 합계** | **856 / 1,007** | **85.0% — 70% 목표 통과** |
| 실험 전용 `bench_transcription.py` | 0 / 65 | 0% |
| 이전 Demucs용 `separate_stems.py` | 0 / 37 | 0% |
| **폴더의 모든 최상위 Python 스크립트 합계** | **856 / 1,109** | **77.2% — 70% 목표 통과** |

```powershell
# perf/pipeline-latency checkout에서, pytest-cov를 설치한 Python으로 실행
python -m pytest ml/pipeline/tests -q --cov=ml/pipeline --cov-report=term-missing
# 생성된 .coverage를 사용하며, 테스트 파일을 분모에서 제외
python -m coverage report --omit='*/tests/*'
# 현재 unified.py가 호출하는 네 파일만 별도로 집계
python -m coverage report --include='*/ml/pipeline/unified.py,*/ml/pipeline/publish_scores.py,*/ml/pipeline/separate_bs_roformer.py,*/ml/pipeline/transcribe_with_progress.py'
```

이는 **line coverage**이지 branch coverage나 실제 모델 추론 성공률이 아니다. mock으로 모델·변환 프로세스를 대체한 줄도 실행된 줄로 계산된다.

SGS의 기존 `rocky-files` Pod에서 `/data/pipeline`을 읽기 전용으로 확인했다. `publish_scores.py`는 로컬 `736432a`와 SHA-256이 같았다. `unified.py`는 서버의 CRLF와 로컬의 LF 차이로 바이트 해시만 달랐고, 639개 코드 줄을 비교했을 때 내용 차이는 0개였다. 이 비교는 배포된 두 스크립트의 일치를 뜻하며 전체 설치 패키지·모델 가중치 또는 이번 세션의 새 GPU 실행을 뜻하지 않는다.

기존 `eval/t6_tab.py` (`ml/eval-set` `7618d93`)도 실행해 기타 11,390 onset·베이스 7,451 onset에서 0건을 확인했다. 이 스크립트는 `guitar_generated/`를 순회하지 않아 생성된 두 번째 기타 GP5 10개·2,896 onset을 세지 않는다. 이번 검증 도구는 그 경로까지 검사했다. 이 차이는 T6 도구의 커버리지 문제이며 저장된 GP5에서 불가능한 운지가 발견된 것은 아니다.

## 4. 판정의 한계와 남은 검증

**코드·파일 계약 검사는 통과했다. 최신 코드의 전체 GPU 추론과 발행을 이번 세션에서 새로 실행했다고 판정하지 않는다.** 저장된 12곡은 pipeline contract 8과 score contract 4의 과거 결과이고, 11/04 지연 시간 실험의 1곡은 pipeline contract 10이지만 score contract 4이다. 현재 `736432a`의 MP3 발행 계약은 **version 5**이므로 위 무결성 검사는 새 악기 패치의 실제 MP3 음색을 검증하지 않는다. 해당 변경은 pytest의 MuseScore 호출·악기 표기 검사까지만 확인했다. 악기별 MP3를 직접 듣는 M1, 실제 PDF 가독성 M2와 공유 M3도 이번 검사에 포함하지 않았다.

`ml/eval-set`의 사전 선언 기준과 비교하면 T1–T3 및 T1′–T3′의 RWC F1 비교는 이번 세션에서 재실행하지 않았다. T4의 `band14` 100% 성공은 저장된 결과가 12곡뿐이라 충족 여부를 말할 수 없다. T5는 과거 Immigrant Song 1곡에서 GPU 303.55초·출판 약 67초가 기록되었으나, 3분 곡 14개에 대한 현재 기준 측정은 아니다. T6은 기타·베이스 12곡의 저장 GP5만 검사했으며 실제 키보드 악보의 연주 가능성은 별도 검증이 필요하다. GP5 → PDF는 신규 Tabtify 업로드를 실행하지 않았고 기존 18개 PDF의 무결성만 확인했다.

Wiki의 AT1–AT5 앱·서버 인수 시나리오도 이 모듈 검사의 범위 밖이다. 앱의 실제 업로드·상태 조회·결과 다운로드와 모바일 재생·공유에는 별도 시스템 검증이 필요하다.

Wiki는 서버·pipeline 테스트를 push/PR 때 실행하도록 계획했지만, 이 브랜치에는 `.github`의 pipeline CI workflow가 없다. 따라서 이번 로컬 성공이 향후 PR의 자동 통과를 뜻하지 않는다. 모델·가중치·서비스 버전이 바뀌면 새 출력 디렉터리에서 실제 1곡 GPU → score contract 5 PDF/MP3 생성과 청취 확인을 먼저 실행하고, `eval/eval_set.csv`의 고정 세트로 T1–T6을 보고해야 한다.
