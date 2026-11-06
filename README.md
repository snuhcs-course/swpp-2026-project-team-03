# ROCKY — Working Demo (Iteration 3 · 휴리스틱 평가용)

> 어떤 곡이든, 우리 밴드 악보로.
> 밴드 악보 제작을 위한 안드로이드 앱의 로그인, 악보 만들기, 진행상황, 보관함, 나의 밴드 흐름을 시연합니다.
> 올린 음원은 서버를 거쳐 SGS GPU에서 AI 파이프라인으로 처리되고, 만들어진 악보(PDF·MIDI)와 음원(MP3)이 앱에 표시됩니다.

Team 3 (영양실조) · 김채연, 박재욱, 조수빈, 홍순형

---

## 1. How to run

### 개발·실행 환경
앱은 Android Studio 2026.1.3으로 작업하고 에뮬레이터에서 확인했습니다. 프로젝트에 고정된 도구·플랫폼 버전과 확인한 개발 환경은 다음과 같습니다.

| 항목 | 버전·요구사항 |
|---|---|
| IDE | Android Studio 2026.1.3 (build AI-261.26222.65.2613.15948027), 내장 JDK(JBR) 25.0.2 |
| 빌드 | Gradle Wrapper 9.5.0, Android Gradle Plugin 9.3.3 |
| 언어 / UI | Kotlin 2.2.10, Jetpack Compose (Material 3), Java 11 소스 호환성 |
| Android SDK | compile/target SDK 37, min SDK 26 (Android 8) |
| 실행 기기 | API 26 이상 Android Emulator 또는 Android 기기 (팀 시연 기기: 갤럭시, Android 13). 확인한 에뮬레이터: Medium Phone, Android 16 (API 36, Google Play, arm64-v8a), Android Emulator 37.1.11 |
| 서버 | Python 3.12, FastAPI (`server/`), SGS 팀 워크스페이스의 CPU Pod `rocky-api` |
| AI 파이프라인 | SGS GPU Pod (NVIDIA A100), `ml/pipeline/unified.py` (서버가 요청하면 노트북 agent가 Pod를 띄움) |
| 서버 연결용 노트북 | macOS, kubectl, kubelogin, adb, Python 3.8 이상. 확인한 환경: macOS 27.2 (Apple Silicon), kubectl 1.32.2, kubelogin 1.34.0, adb (platform-tools 37.0.1), Python 3.14.3 |

### 실행 방법

**A. 앱만 실행하기 (서버 없이, 데모 곡)**
1. 이 저장소를 받아요.
   ```bash
   git clone https://github.com/snuhcs-course/swpp-2026-project-team-03.git
   cd swpp-2026-project-team-03
   git switch iteration-3-demo
   ```
2. Android Studio에서 저장소 루트 폴더를 열고 Android SDK 37을 설치하거나 설치 안내에 따라 설정합니다. Gradle Sync를 완료합니다. 로컬 SDK 경로는 각자 `local.properties`에 설정하며 이 파일은 Git에 포함하지 않습니다.
3. API 26 이상 에뮬레이터 또는 USB 디버깅된 기기를 선택해 `app`을 실행합니다.
4. 새 설치에서는 이메일 회원가입(인증번호는 화면에 표시) 후 로그인됩니다. **새 악보 → 악기 선택 → 데모 곡으로 체험하기 → 원곡 밴드 구성 → 악보 만들기 시작**을 누르고, **진행상황** 탭에서 완료된 악보를 눌러 결과 화면을 확인합니다. 데모 곡은 서버 없이 미리 준비한 결과를 보여줍니다.
5. 밴드 기능을 바로 보려면 **나의 밴드 → 참여하기**에서 데모 초대 코드 `BAND33`을 입력합니다.

**B. 실제 음원을 AI 파이프라인으로 처리하기 (서버 연결)**

서버(`rocky-api`)는 SGS 팀 워크스페이스에 이미 올라가 있습니다. 시연할 때는 노트북에서 연결만 하면 됩니다. 처음 설정(kubectl·kubelogin·adb 설치, kubeconfig, 서버 올리기)은 [`server/DEPLOY_ko.md`](server/DEPLOY_ko.md), 시연 당일 순서는 [`server/DEMO_jaewook_ko.md`](server/DEMO_jaewook_ko.md)에 있습니다.

1. 폰에 앱을 설치하고 USB 디버깅을 켠 뒤 노트북에 연결합니다.
2. 노트북에서 터미널 3개를 엽니다 (1·2는 켜 둡니다).
   ```bash
   # 터미널 1: 서버 연결 (노트북 8080 → 서버 8000)
   kubectl port-forward pod/rocky-api 8080:8000
   # 터미널 2: GPU·PDF Pod를 띄우는 agent ("할 일을 기다려요"가 보이면 정상)
   python3 server/agent/rocky_agent.py --api http://localhost:8080
   # 터미널 3: 폰 연결
   curl localhost:8080/health          # {"ok":true}
   adb reverse tcp:8000 tcp:8080       # 폰의 8000(앱 기본 주소) → 노트북 8080
   ```
3. 앱에서 **새 악보 → 우리 밴드 구성 → 음원 업로드 화면 맨 아래 서버 설정 → 연결 확인 → `연결됨 ✓`**을 확인합니다.
4. 음원(MP3·WAV)을 선택 → 원곡 구성 입력 → 악보 만들기 시작 → **진행상황** 탭에서 단계·퍼센트·남은 시간을 보고, 완료되면 결과를 엽니다. GPU에서 곡 길이의 1~3배가 걸립니다.

AI 파이프라인 코드는 이 브랜치가 아니라 [`perf/pipeline-latency`](https://github.com/snuhcs-course/swpp-2026-project-team-03/tree/perf/pipeline-latency) 브랜치(PR #11, SGS에 배포된 코드)의 `ml/pipeline/`에 있습니다. 앱 브랜치와 git 기록이 이어져 있지 않아 이 브랜치에 합치지 않았습니다.

팀 계정은 서버에 Pod를 만드는 권한을 줄 수 없어서, 노트북에서 도는 agent가 노트북 로그인으로 GPU Pod를 대신 띄웁니다. 그래서 처리하는 동안 노트북의 터미널 1·2가 켜져 있어야 합니다.

---

## 2. What this demo demonstrates

### 구현한 화면과 사용자 흐름
하단 탭은 **새 악보 / 진행상황 / 보관함 / 나의 밴드** 네 개이고, 내 정보는 홈 오른쪽 위에서 엽니다.

| # | 화면 | 기능 |
|---|---|---|
| 0 | 로그인 · 회원가입 · 내 정보 | 이메일 회원가입(시연용 이메일 인증), 프로필 사진, 닉네임·연주 파트 수정, 다크/라이트 모드, 로그아웃 |
| 1 | 새 악보 – 악기 선택 | 피아노/드럼/베이스/기타 복수 선택. 기타는 칸 안의 `− 1대 +`로 최대 2대 |
| 2 | 새 악보 – 음원 업로드 | 기기에서 음원(MP3·WAV)을 골라 서버로 업로드, 또는 Immigrant Song 데모 곡 선택. 화면 아래에서 서버 주소 설정과 연결 확인 |
| 3 | 새 악보 – 원곡 밴드 구성 | 원곡에 있는 악기를 고르거나 "잘 모르겠어요" 선택. 원곡에 없는 파트는 AI 생성(✨)으로 표시 |
| 4 | 진행상황 | 서버의 실제 처리 상황을 단계(n/4), 퍼센트, 남은 시간으로 표시. GPU 대기·차례 대기도 안내. 여러 곡을 올리면 차례로 처리. 취소·지우기, 완료되면 알림 |
| 5 | 결과 | 서버에서 만든 전체/파트별 악보(PDF)와 오디오(MP3). 파트를 바꿔도 재생 위치 유지, 재생 위치에 맞춰 악보 자동 넘김. 보관함 저장, 밴드 공유 |
| 6 | 내보내기 | 밴드 PDF·MIDI·MP3와 파트별 PDF·MP3를 골라 공유 (카카오톡, 메일, 드라이브 등) |
| 7 | 보관함 | 회원별로 저장한 악보 목록. 이름 바꾸기, 삭제 |
| 8 | 나의 밴드 | 밴드 만들기·참여(초대 코드 6자리, 복사), 멤버와 파트 보기, 밴드에 악보 공유, 밴드 이름·악보 이름 수정 |

### Iteration 2 이후 바뀐 점
- **앱을 AI 파이프라인과 연결했습니다.** 올린 음원이 서버를 거쳐 SGS GPU에서 처리되고, 진행률과 결과(PDF·MIDI·MP3)가 앱에 내려옵니다.
  - 파이프라인: BS-RoFormer 6-stem 분리 → stem마다 MuScriptor 채보 → Beat This! 박자 정렬 → 기타·베이스 TAB → 원곡에 없는 악기만 MIDI-GPT로 생성 → 전체 악보 → PDF·MP3
  - 기타는 사용자가 고른 대수대로 나옵니다. 2대를 골랐을 때 원곡에 2대가 있으면 skyline으로 리드·리듬을 나누고, 원곡에 1대면 1대는 채보하고 나머지 1대는 생성합니다. 1대를 골랐는데 원곡에 2대가 있으면 한 사람이 칠 수 있게 합칩니다.
- 갤럭시(Android 13)에 설치되도록 최소 버전을 Android 14에서 Android 8로 낮췄습니다.
- 하단 탭 구조로 바꾸고, 악보 만들기를 백그라운드 작업으로 돌려 기다리는 동안 다른 화면을 쓸 수 있게 했습니다.
- 원곡 밴드 구성을 받아 AI가 새로 만든 파트를 곡마다 구분해 표시합니다.
- 보컬을 밴드 파트로 추가했습니다. 보컬은 밴드 전체 악보를 봅니다.
- 나의 밴드(밴드 만들기·참여·악보 공유)를 추가했습니다.
- 회원가입에 실시간 입력 검사, 이메일·닉네임 중복 확인, 시연용 이메일 인증, 프로필 사진을 넣었습니다. 연주 파트는 하나만 고릅니다.
- 내 정보에서 닉네임·파트·사진을 바꾸고 다크/라이트 모드를 고를 수 있습니다.
- 악기 아이콘을 새로 그리고, 안내 문구를 읽기 쉽게 바꿨습니다. 화면은 세로로 고정됩니다.

### 시연 범위와 한계
- 회원, 보관함, 밴드 데이터는 **이 기기 안에만** 저장되며 서버와 동기화되지 않습니다. 밴드는 같은 기기의 계정끼리만 함께 쓸 수 있습니다.
- 이메일 인증은 실제 메일을 보내지 않고 인증번호를 화면에 보여줍니다.
- 실제 처리는 SGS GPU를 쓰기 때문에 노트북에서 서버 연결과 agent가 켜져 있어야 합니다 (실행 방법 B). 워크스페이스마다 GPU가 1개라 곡은 한 번에 하나씩 차례로 처리됩니다.
- **데모 곡으로 체험하기**를 고르면 서버 없이 `app/src/main/assets/demo/`의 미리 만든 Immigrant Song 결과가 표시됩니다.
- 데모 곡의 MIDI는 별도로 생성한 `muscriptor+midigpt.mid`를 사용했습니다.
- 에뮬레이터에서 한글·이모티콘이 입력되지 않으면 화면 키보드(Gboard)에 한국어를 추가하세요. Mac 하드웨어 키보드로는 한글이 입력되지 않습니다.

---

## 3. Demo video

- Iteration 3 working demo — (영상 링크 추가 예정)
- [Iteration 2 working demo — 로그인과 Immigrant Song 시연](https://drive.google.com/file/d/1wVii7g0WqUVoUHAEtb1jWcls4gWSXsjV/view?usp=sharing)
- [Iteration 1 demo — 이전 버전 참고 영상](https://drive.google.com/file/d/16sLdD9x2Bg739iO0UaESiY7LWRzARTw-/view?usp=drive_link)

---

## 4. 데모 곡 결과 파일 바꾸는 법
서버 없이 보여주는 데모 곡의 결과는 `app/src/main/assets/demo/` 폴더에 있습니다. 이 폴더의 파일을 같은 이름으로 바꾸면 앱에 반영됩니다.

| 용도 | 파일 이름 |
|---|---|
| 밴드 악보 | `band-1.png`, `band-2.png`, … (MuseScore → 내보내기 → PNG, 이름 `band`) |
| 전체 재생 | `band.mp3` (또는 `.wav`, `.flac`) |
| 악기별 악보 | `piano-1.png`, `drums-1.png`, `bass-1.png`, `guitar-1.png`, … |
| 악기별 재생 | `piano.mp3`, `drums.mp3`, `bass.mp3`, `guitar.mp3` (또는 지원되는 다른 음원 형식) |
| 내보내기 | `band.pdf`, `band.mid` |

현재 악기별 악보와 음원은 데모 `band.mid`에서 각 파트를 분리해 MuseScore로 내보낸 파일입니다. 사용된 악보 파일은 MuseScore 4.7.5로 저장되었습니다.

데모 곡 제목과 데모 곡의 원곡 구성은 `app/src/main/java/com/team3/rocky/DemoData.kt`의 `SONG_TITLE`, `DEMO_ORIGINAL`에서 바꿉니다. 원곡에 없는 파트가 AI 생성(✨)으로 표시됩니다.

## 5. 코드 구조
```
app/src/main/java/com/team3/rocky/
├─ MainActivity.kt   앱 시작 (테마, 세로 고정, 화면 가장자리까지 그리기)
├─ RockyApp.kt       화면 이동, 하단 탭, 새 악보·진행상황·보관함 화면
├─ ResultScreens.kt  결과(악보 보기·재생), 내보내기 화면
├─ CommonUi.kt       테마(다크/라이트), 악기 아이콘, 프로필 사진
├─ DemoData.kt       데모 설정, 악기 구성 규칙, 보관함 저장(회원별), 파일 공유
├─ auth/
│  ├─ User.kt               회원 정보, 회원가입 입력값
│  ├─ SignUpValidator.kt    회원가입 입력 검사
│  ├─ EmailVerification.kt  시연용 이메일 인증번호 (6자리, 5분 유효)
│  ├─ PasswordHasher.kt     비밀번호 해시 (PBKDF2-HMAC-SHA256)
│  ├─ UserDatabase.kt       회원 DB (SQLite, rocky_users.db)
│  ├─ AuthRepository.kt     회원가입·로그인·로그아웃·정보 수정, 로그인 상태 유지
│  └─ AuthScreens.kt        로그인, 회원가입, 내 정보 화면
├─ band/
│  ├─ Band.kt               밴드·멤버·공유 악보, 밴드 이름·초대 코드 규칙
│  ├─ BandDatabase.kt       밴드 DB (SQLite, rocky_bands.db)
│  ├─ BandRepository.kt     밴드 만들기·참여·나가기·공유·이름 수정
│  └─ BandScreens.kt        나의 밴드 화면
└─ progress/
   ├─ JobProgress.kt        처리 단계·퍼센트·남은 시간 계산
   └─ ScoreJobs.kt          백그라운드 악보 만들기 작업 목록
app/src/main/assets/demo/   미리 넣어 둔 결과 파일
```

## 6. 회원 기능

### 회원가입 때 받는 정보
| 항목 | 필수 | 이유 |
|---|---|---|
| 이메일 | 필수 | 로그인 아이디. 나중에 Google·Apple 계정과 연결할 때도 기준이 됨 |
| 비밀번호 (+ 확인) | 필수 | 영문과 숫자를 포함해 8~64자, 공백 불가 |
| 닉네임 | 필수 | 앱 안에서 보이는 이름. 2~12자, 한글·영문·숫자·_, 다른 회원과 겹칠 수 없음 |
| 이메일 인증 | 필수 | 시연용: 인증번호를 화면에 보여줌. 서버가 생기면 실제 메일로 보냄 |
| 프로필 사진 | 선택 | 앱 안의 파일로 저장 |
| 연주하는 파트 | 선택 | 피아노·드럼·베이스·기타·보컬 중 하나. 밴드에서 내 파트로 보임 |
| 만 14세 이상 확인 | 필수 | 14세 미만은 개인정보 수집에 법정대리인 동의가 필요해서 지금은 가입을 막음 |
| 이용약관 · 개인정보 수집 동의 | 필수 | 동의한 시각을 저장함. 약관 문구는 시연용 요약이라 공개 전에 정식으로 써야 함 |

실명, 전화번호, 생년월일은 서비스에 쓰이지 않아 받지 않습니다.

### 동작
- 가입하면 바로 로그인되고 홈으로 갑니다.
- 로그인 상태는 앱을 껐다 켜도 유지됩니다. 홈 오른쪽 위 "내 정보"에서 닉네임·파트·사진을 바꾸고 로그아웃합니다.
- 닉네임과 이메일은 입력하는 동안 형식과 중복을 바로 확인합니다.
- 로그인에 실패하면 이메일이 없는 것인지 비밀번호가 틀린 것인지 구분하지 않고 같은 메시지를 보여줍니다.
- 보관함은 회원마다 따로 저장됩니다. 이 기능을 넣기 전에 저장한 악보는 보이지 않습니다.

### 저장 방식과 한계
- 회원 정보는 **이 기기 안의 SQLite DB**(`rocky_users.db`)에만 저장됩니다. 서버가 아직 없어서, 다른 기기에서는 같은 계정으로 로그인할 수 없습니다. 서버가 생기면 `UserDatabase`를 서버 API 호출로 바꾸면 됩니다.
- 비밀번호는 원문을 저장하지 않고 PBKDF2-HMAC-SHA256(반복 120,000회, 회원마다 다른 salt)으로 해시해 저장합니다.
- Google·Apple 로그인을 붙일 수 있도록 DB에 `auth_provider`, `provider_user_id` 칸을 미리 두었습니다. 지금은 모두 `EMAIL`입니다.
- 비밀번호 찾기, 회원 탈퇴는 아직 없습니다.

### 테스트
```bash
./gradlew :app:testDebugUnitTest            # 입력 검사·비밀번호 해시·이메일 인증·악기 구성·밴드 규칙·진행률·서버 API 응답 처리 (58개)
./gradlew :app:connectedDebugAndroidTest    # 에뮬레이터 필요: 회원 DB·밴드 DB·화면 흐름·서버 연결 e2e (15개)
cd server && pip install -r requirements-dev.txt && pytest -q   # 서버 API (42개)
```
세 가지 모두 push할 때마다 GitHub Actions(`.github/workflows/android-build.yml`)에서 자동으로 돌아갑니다. 에뮬레이터 테스트는 실제 서버 코드에 가짜 파이프라인(`server/tests/ci_fake_pipeline.py`)을 붙여 업로드부터 결과 화면까지 확인합니다.
화면 흐름 테스트는 회원가입 → 로그아웃 → 틀린 비밀번호 → 로그인 → 앱 재시작 후 로그인 유지까지 확인합니다. 시작할 때 기기의 회원 DB를 지우므로, 직접 만든 계정이 있는 기기에서는 돌리지 마세요.
