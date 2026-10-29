# MIDI-GPT — 원곡에 없는 악기 파트 생성

담당: 김채연

ROCKY 파이프라인에서 **원곡에 없는 악기 파트를 새로 만드는 단계**예요.

```
음원 → Demucs(보컬 제거) → MuScriptor(채보) → Beat This!(박자 정렬) → [MIDI-GPT: 없는 악기 생성] → 악보
```

원곡에 있는 악기는 채보 결과를 그대로 쓰고, 사용자가 고른 악기 중 원곡에 없는 것만 이 단계에서 생성해요.

- 모델: [midigpt](https://pypi.org/project/midigpt/) 0.4.2 (Metacreation-Lab), `yellow_medium`
  - 코드는 MIT, 모델 가중치는 **CC-BY-NC-4.0**(비상업적 이용, 출처 표시)이라 저장소에 올리지 않아요.
  - 가중치는 Hugging Face에서 **라이선스 동의 + 토큰**이 있어야 받을 수 있어요 (아래 "모델 다운로드 권한").
- 실행 환경: Python 3.10 이상, GPU 권장 (Colab T4에서 확인). CPU로도 돌지만 오래 걸려요.

## 폴더 구조
```
generate_missing.py   파이프라인에서 쓰는 진입점: MIDI 한 곡 + 악기 → 생성 결과
prep_song.py          MIDI를 악기별 파일로 나누기 (악기 번호 기준 분류, 템포 하나로 통일)
generate_part.py      MIDI-GPT 생성 본체 (폴더 단위, 재시도 로직 포함)
experiments/          Iteration 1 모델 검증 코드 (BabySlakh 평가, 논문 재현, 데이터 찾기)
results/              Iteration 1 평가 결과 (CSV, 엑셀)
docs/notes.md         진행 기록과 결과 해석
```

## 설치
```bash
cd ml/midigpt
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

### 모델 다운로드 권한 (처음 한 번)
MIDI-GPT 모델은 라이선스 동의 후에만 받을 수 있어요.
1. https://huggingface.co/Metacreation/MIDI-GPT 에서 로그인 후 라이선스에 동의
2. Hugging Face → Settings → Access Tokens → **Read** 토큰 생성
3. 실행 전에 토큰 설정 (**토큰은 절대 git에 올리지 않기**)
   - 터미널/서버: `export HF_TOKEN=hf_...` (쿠버네티스는 Secret으로 넣어도 됨)
   - Colab: 왼쪽 🔑 보안 비밀에 `HF_TOKEN` 추가 → 노트북 액세스 켜기 → 셀에서
     ```python
     from google.colab import userdata; import os
     os.environ['HF_TOKEN'] = userdata.get('HF_TOKEN')
     ```
- 토큰은 팀원마다 각자 만들어 쓰고 공유하지 않기
- 수업 GPU/CPU 파드는 종료되면 모델 파일도 사라져서, 새 파드마다 다시 다운로드돼요
- `401` / `GatedRepoError`가 나면 라이선스 동의 또는 `HF_TOKEN` 설정을 확인하세요

## 사용법
```bash
# 한 곡에 피아노 추가
python generate_missing.py song.mid piano

# 한 곡에 여러 악기 (악기마다 따로 생성)
python generate_missing.py song.mid piano guitar --out gen_results

# 여러 곡 한 번에
python generate_missing.py --jobs jobs.csv --out gen_results
```

`jobs.csv` 예시:
```
file,instruments
songs/time-bomb.mid,piano
songs/yoru-ni-kakeru.mid,guitar
```

결과 (`gen_results/`):

| 파일 | 내용 |
|---|---|
| `<곡>__+<악기>_band.mid` | 원곡 트랙 전부 + 생성한 악기 |
| `<곡>__+<악기>_only.mid` | 생성한 악기 파트만 (악보용) |

환경 변수:

| 이름 | 기본값 | 뜻 |
|---|---|---|
| `ROCKY_SEED` | 0 | 같은 입력과 같은 seed면 같은 결과 |
| `ROCKY_MODEL` | yellow_medium | 모델 크기 |
| `ROCKY_DEVICE` | 자동 | `cuda` 또는 `cpu` |
| `ROCKY_BARS` | 0 | 앞 N마디만 생성 (0 = 곡 전체) |

## 동작 규칙
- **악기 분류**는 General MIDI 악기 번호로 해요.

  | 악기 | 기준 |
  |---|---|
  | 피아노 | 0~7 |
  | 기타 | 24~31 |
  | 베이스 | 32~39 |
  | 드럼 | 10번 채널 |
  | 그 외 | other로 남김 |

- **원곡 트랙은 지우지 않아요.** 생성하려는 악기로 분류된 트랙이 이미 있어도(예: 신스가 기타 번호로 저장된 경우) 그대로 두고, 새 파트를 추가해요.
- **템포**: MIDI-GPT는 곡 전체에 템포 하나만 지원해요. 그래서 가장 오래 쓰인 템포 하나로 맞춰요. Beat This! 단계에서 이미 템포 하나의 4/4로 정리된 MIDI가 들어오는 것을 전제로 해요.
- **생성 실패 시** 조건을 점점 풀면서 최대 4번 다시 시도해요. 네 번째 시도는 동시음 수 제한을 끄고 생성해요.

## 알려진 한계 (Iteration 1 평가)
- 생성된 파트는 원곡보다 음 수가 1/2~1/3 수준이고, 음을 길게 끄는 경향이 있어요.
- 트랙이 많은 곡에서는 2048토큰 창 때문에 빈 마디가 생겨요. 특히 드럼에서 심해요.
- 자세한 수치는 [`docs/notes.md`](docs/notes.md)와 `results/`에 있어요.

## Iteration 1 실험 다시 돌리기
```bash
# BabySlakh(babyslakh_16k)를 data/ 에 풀어 둔 뒤
python generate_part.py data/babyslakh_16k                         # 20곡 × 4악기 생성 → step5_out/
python experiments/eval_generation.py step5_out                    # CP·GS·PCHE 지표
python experiments/rank_tracks.py && python experiments/make_eval_xlsx.py
```
