# ROCKY – Iteration 1 Demo (MVP)

> 어떤 곡이든, 우리 밴드 악보로.
> 음원을 올리면 피아노·드럼·베이스·기타 밴드 악보로 바꿔주고, 원곡에 없는 악기 파트는 AI가 새로 만들어주는 안드로이드 앱

Team 3 (영양실조) · 김채연, 박재욱, 조수빈, 홍순형

---

## 1. How to run

### 개발·실행 환경
| 항목 | 버전 |
|---|---|
| OS | macOS |
| IDE | Android Studio (버전 기입) |
| Language / UI | Kotlin, Jetpack Compose (Material 3) |
| Min SDK | API 24 (Android 7.0) |
| 테스트 기기 | Android Emulator (기기명 기입) / 실제 폰 (기종 기입) |

### 실행 방법
1. 이 저장소를 받아요.
   ```bash
   git clone <저장소 주소>
   cd <저장소 폴더>
   git checkout iteration-1-demo
   ```
2. Android Studio → **Open** → 이 폴더를 선택해요.
3. Gradle Sync가 끝날 때까지 기다려요.
4. 에뮬레이터 또는 USB 디버깅을 켠 안드로이드 폰을 선택하고 **▶ Run**을 눌러요.

---

## 2. What this demo demonstrates

### 구현한 화면 (사용자 흐름)
| # | 화면 | 기능 |
|---|---|---|
| 1 | 홈 | NEW(새 악보 만들기), STORAGE(보관함) |
| 2 | 악기 선택 | "당신을 위한 악보를 만드세요" – 피아노/드럼/베이스/기타 복수 선택 |
| 3 | 음원 업로드 | 기기에서 음원 파일 선택 또는 데모 곡 선택 |
| 4 | 처리 중 | 채보 중 → 박자 맞추는 중 → 밴드 편곡 중 단계 표시 |
| 5 | 결과 | 밴드 전체 또는 악기별 악보 보기·재생, AI 생성 악기 표시(✨), 저장 |
| 6 | 내보내기 | 악보 PDF·MIDI 파일 공유 (카카오톡, 메일, 드라이브 등) |

### 시연 범위 (중요)
- **화면 흐름과 저장·재생·공유 기능은 실제로 동작**합니다.
- 결과 화면에서 악기 버튼을 누르면 해당 악기의 악보와 음원으로 전환됩니다. 같은 버튼을 다시 누르면 밴드 전체 보기·재생으로 돌아갑니다.
- **AI 처리(채보·박자 정렬·편곡)는 아직 앱과 연결되지 않았습니다.** 어떤 파일을 업로드해도 `app/src/main/assets/demo/`에 미리 넣어 둔 결과가 표시됩니다.
- 미리 넣어 둔 결과 파일은 아래 모델들을 실제로 실행해서 만든 결과입니다. (사용한 곡·모델 기입)

### 이번 Iteration에서 검증한 것 (Technical feasibility)
| 검증 항목 | 결과 |
|---|---|
| MuScriptor로 음원 → 악기별 MIDI 채보 | (결과 기입) |
| MIDI-GPT로 없는 악기 파트 생성 (BabySlakh 20곡 × 4악기) | 80건 중 78건 생성 성공. 화성·조성은 원곡과 대체로 맞지만 음 밀도가 원곡보다 낮음 |
| 채보 MIDI를 악보로 볼 때의 문제 | 채보 결과가 실제 박자와 정렬되지 않아(기본 120 BPM) 셋잇단·붙임줄이 많은 악보가 됨 → 박자 추적(beat_this) 단계 필요 확인 |
| 생성 모델 후보 | REMI-z(밴드 편곡) 적용 검토 중 |

### 다음 Iteration 계획
- 음원 업로드 → 채보 → 박자 정렬 → 밴드 편곡을 서버에서 실제로 실행하고 앱과 연결
- 서버에서 생성한 악기별 악보·음원을 앱에 전달

---

## 3. Demo video
- 영상 링크: (YouTube 일부공개 / Google Drive 링크 기입)

---

## 4. 데모 결과 파일 바꾸는 법
`app/src/main/assets/demo/` 폴더의 파일을 같은 이름으로 바꾸면 앱에 반영됩니다.

| 용도 | 파일 이름 |
|---|---|
| 밴드 악보 | `band-1.png`, `band-2.png`, … (MuseScore → 내보내기 → PNG, 이름 `band`) |
| 전체 재생 | `band.mp3` (또는 `.wav`, `.flac`) |
| 악기별 악보 | `piano-1.png`, `drums-1.png`, `bass-1.png`, `guitar-1.png`, … |
| 악기별 재생 | `piano.mp3`, `drums.mp3`, `bass.mp3`, `guitar.mp3` (또는 지원되는 다른 음원 형식) |
| 내보내기 | `band.pdf`, `band.mid` |

현재 악기별 악보와 음원은 데모 `band.mid`에서 각 파트를 분리해 MuseScore로 내보낸 파일입니다.

데모 곡 제목과 AI 생성 악기 표시는 `app/src/main/java/com/team3/rocky/DemoData.kt`의 `SONG_TITLE`, `AI_GENERATED`에서 바꿉니다.

## 5. 코드 구조
```
app/src/main/java/com/team3/rocky/
├─ MainActivity.kt   앱 시작
├─ RockyApp.kt       화면 6개와 화면 이동
└─ DemoData.kt       데모 설정, 테마, 보관함 저장, 파일 공유
app/src/main/assets/demo/   미리 넣어 둔 결과 파일
```
