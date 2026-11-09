# Android Emulator에서 Iteration 3 기능 확인

2026-11-08 기준: 앱·서버 변경은 `feat/score-key-transpose`(PR #13, 취소 기능 PR #12 위에 쌓인 브랜치)에 있고, GP5 PDF의 로컬 alphaTab 통합은 `feat/gp5-alphatab-pipeline`(PR #14)에 있다. SGS 공유 볼륨의 `publish_scores.py`와 `convert.js`는 PR #14와 해시가 같고, `rocky-api`는 PR #13의 서버 코드로 실행 중이다. 배포 상태가 바뀌면 먼저 버전을 다시 확인한다.

## 준비

1. Android Studio에서 `feat/score-key-transpose` checkout의 프로젝트 루트를 **새 창으로** 연다. 과거 `rocky-app-my-band-emulator` checkout에서 `Update Project → Merge`를 사용하지 않는다.
2. SGS에 로그인된 `kubectl`의 현재 context가 팀 namespace `ws-qt1ja5byz6220`를 가리키는지 확인한다.
3. Android Studio의 기기 선택에서 Emulator를 시작하고 `app`을 실행한다.

노트북에서 터미널 두 개를 열고 각각 저장소 루트로 이동한다. `kubectl`이 PATH에 없다면 설치 경로를 PATH에 넣는다. kubeconfig가 기본 위치가 아니라면 두 터미널에 `KUBECONFIG` 환경 변수를 설정한다. 토큰 값은 명령줄이나 채팅에 넣지 않는다.

터미널 1 — 켜 둔다:

```powershell
kubectl -n ws-qt1ja5byz6220 get pod rocky-api
kubectl -n ws-qt1ja5byz6220 port-forward pod/rocky-api 8080:8000
```

터미널 2 — 켜 둔다:

```powershell
python server/agent/rocky_agent.py --api http://127.0.0.1:8080
```

터미널 3에서 연결을 확인한다:

```powershell
Invoke-RestMethod http://127.0.0.1:8080/health
```

에뮬레이터 앱의 음원 업로드 화면 아래 `서버 설정`에 `http://10.0.2.2:8080`을 입력하고 `연결 확인`을 누른다. Android Emulator의 `10.0.2.2`는 개발 PC의 `127.0.0.1`을 가리킨다([Android 공식 문서](https://developer.android.com/studio/run/emulator-networking-address)). 실제 USB 휴대폰에서는 기존 `adb reverse` 절차를 사용한다.

## 확인 순서

1. **alphaTab:** 기타·베이스를 포함한 악보를 생성하고, 전체 밴드 및 악기별 PDF·MP3가 열리는지 확인한다. 데모 곡은 서버 변환 검증에 쓰지 않는다.
2. **취소:** 두 곡을 요청해 한 곡이 처리 중이고 다음 곡이 대기하는 상태를 만든다. 진행 중인 곡의 `취소`를 누르면 Pod 종료 확인 후 카드가 사라지고 다음 곡이 시작되는지 확인한다. 대기 중인 곡도 취소해 큐에서 빠지는지 확인한다.
   - agent가 아직 요청을 받아 가지 않은 곡은 취소 직후 큐에서 빠져 다음 곡이 시작되어야 한다. 이미 받아 간 경우에는 Pod 삭제 확인을 기다린다.
   - 중단을 위해 `kubectl delete pod`만 실행하지 않는다. 연결이 돌아온 agent가 요청을 다시 받아 Pod를 재생성할 수 있으므로 앱의 취소 또는 `POST /jobs/<작업번호>/cancel`을 사용한다.
3. **키 변경:** 완료된 서버 악보를 `보관함에 저장`한 뒤 열어 `−한 키`, `−반 키`, `+반 키`, `+한 키`를 눌러 본다. 변경 후 전체·악기별 PDF, 재생 MP3, 내보내기 파일이 같은 키를 사용하는지 확인한다. 드럼 타격음은 음높이를 이동하지 않으므로 드럼 MP3의 소리는 같을 수 있다.
   - 원키에서 `−한 키`를 세 번 빠르게 누르면 **선택 −6반음**으로 표시되고 악보는 아직 원키여야 한다. `−6반음 적용`을 한 번 누른 뒤에만 서버 요청이 하나 시작되고, 완료 후 악보·음원이 −6반음으로 바뀌는지 확인한다. `선택 취소`는 서버 요청 없이 현재 키로 돌아가야 한다.
   - 낮은 개방현이 포함된 기타 GP5로 `−반 키`를 요청한다. 결과 PDF 첫 페이지의 `String tuning (top to bottom)`이 원본보다 각 줄에서 반음 낮아졌고 줄 순서·옥타브가 맞는지 확인한다. 같은 GP5의 다른 기타 트랙에 개방현 문제가 없다면 그 트랙의 튜닝은 유지되고 프렛만 이동해야 한다. PDF 헤더와 첫 악보 줄이 겹치거나 잘리지 않는지도 확인한다. 이 표기 확인에는 alphaTab 변환기 수정 버전이 필요하다.

키 변경은 GPU가 아닌 CPU Pod에서 원본 MIDI·GP5를 이동하고 `publish_scores.py`로 PDF·MP3를 다시 만든다. 모든 파일이 내려온 뒤에만 앱의 보관함 결과가 새 버전으로 바뀐다. 서버의 원본은 그대로 남는다. 한 곡의 `+1`반음 종단 시험에서는 밴드 전체와 기타·베이스·피아노·드럼의 PDF 5개와 MP3 5개가 생성됐고 계약 해시가 모두 일치했다.

테스트가 끝나면 진행 중인 작업이 없는지 확인하고 두 터미널에서 `Ctrl+C`로 agent와 port-forward만 종료한다. PVC나 기존 Pod를 삭제하지 않는다.
