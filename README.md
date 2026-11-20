# ROCKY — Working Demo (Iteration 4 · Hardening and UAT)

> 어떤 곡이든, 우리 밴드 악보로.
> 밴드 곡을 올리면 우리 밴드 악기(또는 내 악기 하나)의 악보와 음원을 만들어 주는 안드로이드 앱입니다.
> 올린 음원은 ROCKY 서버를 거쳐 SGS GPU에서 AI 파이프라인으로 처리되고, 만들어진 악보(PDF)와 음원(MP3)을 앱에서 보고 들으며 밴드와 공유합니다.

Team 3 (영양실조) · 김채연, 박재욱, 조수빈, 홍순형

Iteration 4에서는 새 기능보다 **이미 만든 기능을 하나로 합치고, 실제 폰에서 처음부터 끝까지 안정적으로 돌아가게 하는 것**에 집중했습니다. 휴리스틱 평가(Iteration 3)와 UAT(11/16 테스터 2명, 11/18 TA)에서 나온 문제를 고쳤고, USB 연결 없이 폰에서 바로 쓸 수 있게 서버를 공개 주소로 열었습니다.

---

## 1. How to run

### 개발·실행 환경

| 항목 | 버전·요구사항 |
|---|---|
| IDE | Android Studio 2026.1.3 (build AI-261.26222.65.2613.15948027), 내장 JDK(JBR) 25.0.2 |
| 빌드 | Gradle Wrapper 9.5.0, Android Gradle Plugin 9.3.3 |
| 언어 / UI | Kotlin 2.2.10, Jetpack Compose (Material 3, BOM 2026.02.01), Java 11 소스 호환성 |
| Android SDK | compile/target SDK 37, min SDK 26 (Android 8) |
| 실행 기기 | API 26 이상 Android 기기 또는 에뮬레이터. 팀 시연 기기: Galaxy S22, Galaxy S23 Ultra. 확인한 에뮬레이터: Medium Phone, Android 16 (API 36, arm64-v8a) |
| 서버 | Python 3.12, FastAPI + SQLite (`server/`), SGS 팀 워크스페이스(gpu22)의 CPU Pod `rocky-api` |
| AI 파이프라인 | 곡마다 SGS GPU Pod(`rocky-midi-*`, NVIDIA A100)와 CPU Pod(`rocky-pdf-*`)를 `rocky-api`가 직접 만들어 처리 |
| 공개 주소 | `http://team3.swpp-2026-b.snu.ac.kr` (팀 서버 nginx → SSH 역방향 터널 → `rocky-api`) |
| 공개 주소를 잇는 노트북 | macOS, kubectl + kubelogin, OpenSSH. 학교 네트워크(또는 VPN)에서 `kubectl port-forward`와 SSH 터널을 켜 둠 |

### 실행 방법

**A. 폰에서 바로 써 보기 (USB 필요 없음)**

1. 팀에게 공개 주소가 들어간 APK를 받아 설치합니다. 처음이면 "출처를 알 수 없는 앱" 설치를 허용합니다.
2. 앱을 열고 이메일로 회원가입합니다(인증번호 없음). 와이파이·LTE 어디서든 됩니다.
3. 홈에서 **밴드 합주용**(우리 밴드 악기) 또는 **개인 연습용**(내 악기 하나)을 고릅니다 → 악기를 고르고 → 곡(MP3·WAV·FLAC·OGG)을 올립니다 → **악보 만들기 시작**.
4. **만드는 중** 탭에서 단계·퍼센트·남은 시간을 보다가, 완료되면 결과를 엽니다. 완료된 곡은 **보관함**에 자동으로 저장됩니다. GPU가 비어 있으면 3분 곡이 약 5분 걸립니다.

**B. 소스에서 빌드하기**

1. 저장소를 받고 이 브랜치로 바꿉니다.
   ```bash
   git clone https://github.com/snuhcs-course/swpp-2026-project-team-03.git
   cd swpp-2026-project-team-03
   git switch iteration-4-demo
   ```
2. 서버 주소와 API 키를 넣습니다. 키는 Git에 올리지 않으니 팀에게 개인 메시지로 받습니다. `local.properties`(커밋하지 않음)에 적거나 Gradle 속성으로 넘깁니다.
   ```properties
   # local.properties
   rocky.serverUrl=http://team3.swpp-2026-b.snu.ac.kr
   rocky.apiKey=<팀에게 받은 키>
   ```
   ```bash
   ./gradlew assembleDebug -Procky.serverUrl=http://team3.swpp-2026-b.snu.ac.kr -Procky.apiKey=<팀에게 받은 키>
   ```
3. Android Studio에서 저장소 루트를 열고 Gradle Sync 후 `app`을 실행합니다. 로그인 화면 아래 **연결 설정**에서 연결 상태를 확인할 수 있고, 여기에 저장한 주소·키가 빌드 값보다 우선합니다.

**C. 서버 운영 (팀원용)**

- 서버(`rocky-api`)와 데이터는 SGS 워크스페이스에 올라가 있습니다. 공개 주소를 열어 두려면 노트북 한 대가 학교 네트워크에서 `kubectl port-forward`와 SSH 터널을 켜 두어야 합니다. 순서와 문제 해결은 [`server/deploy/README.md`](server/deploy/README.md)에 있습니다.
- Iteration 3까지 필요했던 노트북 agent는 이제 쓰지 않습니다. `rocky-api`가 워크스페이스 서비스 계정으로 GPU·PDF Pod를 직접 만들기 때문에, 노트북이 꺼져도 이미 시작한 곡은 끝까지 처리됩니다.
- 처음 설정(kubeconfig, API 키 Secret, 팀 서버 nginx)은 [`server/deploy/README.md`](server/deploy/README.md)와 [`server/DEPLOY_ko.md`](server/DEPLOY_ko.md)를 봅니다.

AI 파이프라인 코드는 앱과 git 기록이 이어져 있지 않아 이 브랜치에 넣지 않았습니다. 파이프라인은 [`ml/unified-pipeline`](https://github.com/snuhcs-course/swpp-2026-project-team-03/tree/ml/unified-pipeline)의 `ml/pipeline/`, 박자 정렬은 [`main`](https://github.com/snuhcs-course/swpp-2026-project-team-03/tree/main)의 `ml/beat_align/`, 기타·베이스 TAB은 [`ml/guitar-tab`](https://github.com/snuhcs-course/swpp-2026-project-team-03/tree/ml/guitar-tab)의 `ml/guitar_tab/`에 있습니다.

---

## 2. What this demo demonstrates

### 구현한 화면과 사용자 흐름

하단 탭은 **홈 / 만드는 중 / 보관함 / 내 밴드** 네 개입니다.

| # | 화면 | 기능 |
|---|---|---|
| 0 | 회원가입 · 로그인 · 내 정보 | 서버 계정(이메일), 약관 동의, 첫 실행 안내 슬라이드, 프로필 사진, 닉네임 수정, 로그아웃(만드는 중인 곡이 있으면 경고), 한국어/영어 |
| 1 | 홈 | **밴드 합주용** / **개인 연습용** 선택, "이렇게 만들어요" 안내 |
| 2 | 악기 선택 | 밴드 합주용: 피아노·드럼·베이스·기타(1~2대) 여러 개. 개인 연습용: 악기 하나. 원곡 구성은 묻지 않고 ROCKY가 곡을 듣고 판단 |
| 3 | 곡 올리기 | MP3·WAV·FLAC·OGG. 깨진 파일, 오디오가 아닌 파일, 30초 이하 파일은 올리기 전에 바로 안내. 곡 이름 수정 |
| 4 | 만드는 중 | 단계·퍼센트·남은 시간, 앞 곡을 기다리는 중이면 "대기 중", 취소, 완료·실패 알림. 실패하면 이유를 보여 주고 연결 문제일 때만 다시 시도 |
| 5 | 결과 | 전체 악보와 악기별 악보(PDF, 기타·베이스는 TAB 포함), 악기별 음원 재생. 재생 중인 마디 칠하기와 자동 넘김, 쪽 넘기기, 두 손가락 확대, 전체 화면, 키 바꾸기, AI가 만든 파트(✨) 표시, 사용 안내, 마지막 쪽 뒤 별점과 의견 |
| 6 | 보관함 | 완료된 곡 자동 저장. 선택 모드에서 여러 곡을 밴드에 공유하거나 삭제, 이름 바꾸기 |
| 7 | 내 밴드 | 밴드 만들기·참여(초대 코드), 최대 8명, 멤버마다 여러 악기, 밴드에 공유된 악보 보기 |

### Iteration 4에서 바뀐 점

**기능 완성과 통합**
- 회원, 밴드, 밴드에 공유한 악보, 별점이 **서버 DB**에 저장됩니다. 다른 폰에서도 같은 계정으로 들어갑니다 (PR #19, #24).
- **개인 연습용** 모드를 추가했습니다. 악기 하나만 고르고, 원곡에 있는 악기면 그 파트만 채보해서 더 빨리 끝납니다 (PR #26).
- **원곡 구성 입력을 없앴습니다.** ROCKY가 곡을 듣고 어떤 파트를 채보하고 어떤 파트를 AI로 만들지 정합니다. 기타 2대인 곡은 기타 1·2 악보가 따로 나옵니다.
- 처리 중인 곡 **취소**와 저장한 악보의 **키 바꾸기**를 넣었습니다 (PR #12, #13, #20).
- 악보 PDF를 외부 사이트(Tabtify) 대신 서버에서 **alphaTab**으로 직접 만들고, 기타 튜닝을 표시합니다 (PR #14, #21).
- 파이프라인이 밴드 곡이 아닌 입력(너무 짧거나 거의 무음, 밴드 악기 소리가 거의 없음)을 거부하고, 쉬는 구간에 잘못 찍힌 음을 지웁니다 (PR #15, #16).
- PDF 단계가 인터넷 문제로 실패하면 자동으로 다시 시도하고, 실패 이유를 사용자에게 알려 줍니다 (PR #25).

**휴리스틱 평가와 UAT에서 나온 문제 수정**
- 결과 화면을 정리했습니다: 악기 버튼 고정 배치, 쪽 넘기기, 재생 바는 아래, 핀치 줌·전체 화면 (PR #24, #27).
- 완료된 곡을 보관함에 **자동 저장**하고, 보관함 선택 모드로 밴드 공유·삭제를 메뉴 밖으로 꺼냈습니다 (PR #27).
- 실패 안내를 쉬운 말로 바꾸고, 문제 있는 파일은 올리기 전에 거릅니다 (PR #27, #36).
- 첫 실행 안내와 결과 화면 사용 안내를 넣었습니다. S22·S23 Ultra에서 글자가 잘리던 곳을 고쳤습니다 (PR #27).
- **악보 따라가기**를 다시 만들었습니다 (PR #33, #34, #35).
  - 서버가 PDF를 만들 때 마디마다 위치를 함께 저장하고, 앱은 그 위치에 맞춰 마디를 칠합니다.
  - 전체 악보에서 한 마디씩 밀리던 문제와 개인 연습에서 줄 단위로 칠하던 문제가 사라졌습니다.
  - 기타·베이스 TAB의 마디 번호를 빨간색에서 검은색으로 바꿨습니다.
  - 악기를 바꿀 때 첫 쪽이 바로 보이고, 한 번 본 악보는 다시 그리지 않습니다 (31쪽 전체 악보 기준 1~1.4초 → 첫 쪽 0.27초, 다시 열 때 즉시).

**배포**
- **USB 없이 폰에서 바로 씁니다.** 팀 서버의 공개 주소로 들어온 요청을 SSH 역방향 터널로 SGS의 `rocky-api`에 넘기고, 모든 요청에 API 키를 확인합니다 (PR #28).
- **노트북 agent를 없앴습니다.** `rocky-api`가 GPU·PDF Pod를 직접 만들고 지웁니다 (PR #28).

**테스트**
- 앱 단위 테스트, 에뮬레이터 UI 테스트, 서버 테스트가 push마다 GitHub Actions에서 돌아갑니다. 결과와 커버리지는 Wiki의 Testing Documentation 2.2에 있습니다.

### 시연 범위와 한계
- 공개 주소는 노트북 한 대가 학교 네트워크에서 port-forward와 SSH 터널을 켜 두어야 열립니다. 노트북 없이 상시 운영하려면 터널을 클러스터 안으로 옮겨야 하고, 조교님께 터널 전용 키 발급을 요청해 둔 상태입니다.
- 워크스페이스의 GPU를 곡마다 하나씩 쓰기 때문에, 여러 명이 동시에 올리면 차례로 처리됩니다.
- PR #27의 서버 쪽 변경(프로필 사진, 멤버당 여러 악기, 별점 의견)은 다음 서버 배포 때 반영됩니다. 원곡에 기타가 없는데 2대를 요청하면 1대만 만드는 파이프라인 변경은 PR #29(리뷰 중)에 있습니다.
- 보관함 목록과 내려받은 악보 파일은 폰에 저장됩니다. 같은 계정이어도 다른 폰에서는 보관함 목록이 보이지 않습니다.
- 원곡 녹음을 들으며 따라가는 기능은 UAT 이후 뺐습니다. 결과 화면은 악보로 합성한 음원만 재생합니다.

---

## 3. Demo video

- [Iteration 4 working demo](https://drive.google.com/file/d/1NBejZUPGWrlBinjzxhctGnso7HdQOWc5/view?resourcekey)
  - 2026-11-18(TA 미팅 전)에 찍은 영상입니다. 키 바꾸기와 Iteration 4의 UI 수정 등 그때까지 반영된 기능을 보여 줍니다.
  - 그 뒤 11/20에 병합한 변경은 영상에 없습니다: UAT 피드백 반영(PR #27), 악보 따라가기 재구현과 빠른 악기 전환(PR #33~#35), 노트북 agent 제거(PR #28).
- [Iteration 3 working demo](https://drive.google.com/file/d/1mpPb0rXEK5a93LJj82WM1YPhiAR9aUGR/view?usp=sharing)
- [Iteration 2 working demo](https://drive.google.com/file/d/1wVii7g0WqUVoUHAEtb1jWcls4gWSXsjV/view?usp=sharing)

---

## 4. 테스트

```bash
./gradlew :app:testDebugUnitTest            # 앱 단위 테스트 (마디 위치·악보 따라가기·입력 검사·서버 응답 처리 등)
./gradlew :app:connectedDebugAndroidTest    # 에뮬레이터 필요: 화면 흐름, 서버 연결 e2e
cd server && pip install -r requirements-dev.txt && pytest -q   # 서버 API
```

에뮬레이터 테스트는 실제 서버 코드에 가짜 파이프라인(`server/tests/ci_fake_pipeline.py`)을 붙여 업로드부터 결과 화면까지 확인합니다. 시작할 때 기기의 앱 데이터를 지우므로, 직접 쓰는 계정이 있는 기기에서는 돌리지 마세요.

## 5. 코드 구조

```
app/src/main/java/com/team3/rocky/
├─ RockyApp.kt         화면 이동, 하단 탭, 홈·악기 선택·곡 올리기·만드는 중·보관함
├─ ResultScreens.kt    결과 화면 (악보 보기, 재생, 마디 칠하기, 키 바꾸기, 별점)
├─ ScorePages.kt       악보 PDF를 한 쪽씩 그리고 기억해 두기
├─ score/              재생 시간 → 마디(MeasureClock), 서버 마디 위치(PrintedMeasures), 그림에서 마디선 찾기(ScoreLayout)
├─ server/             서버 API(RockyApi), 결과 내려받기·저장(ScoreStore)
├─ auth/  band/        회원, 밴드 (서버 DB)
└─ progress/           만드는 중 작업 목록, 진행률
server/
├─ rocky_server/       FastAPI 서버: 작업 큐, 결과 파일, 회원·밴드·별점 DB, GPU·PDF Pod 실행
├─ deploy/             공개 주소: 팀 서버 nginx 설정, SSH 터널, 운영 안내
└─ k8s/ws2/            SGS 워크스페이스에 올리는 rocky-api Pod
```
