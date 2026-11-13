# ROCKY 서버 SGS 배포·시연 안내 (처음 하는 사람용)

```
폰1 ─USB─ 노트북1(재욱, 계정 gpu05) ─port-forward─ 워크스페이스 1의 rocky-api ─ GPU(ferrari)
폰2 ─USB─ 노트북2(채연, 계정 gpu22) ─port-forward─ 워크스페이스 2의 rocky-api ─ GPU(ford)
```
- 11/4 시연은 두 노트북 모두 gpu05 하나로 했다 (그날 순서는 `DEMO_jaewook_ko.md`). **gpu22는 11/4 저녁 B·C 단계 완료** — 수빈 볼륨 `rocky-data`에 복사(여유 약 7.4G), `rocky-api` 가동. 파이프라인을 바꾸면 두 볼륨 모두 반영
- **팀 계정은 Pod는 만들 수 있지만 권한(Role/RoleBinding)은 못 준다 (11/3 확인).** 그래서 서버 Pod가 GPU Pod를 직접 못 만들고,
  **각 노트북에서 도는 agent(`server/agent/rocky_agent.py`)가 노트북 로그인 권한으로 GPU·PDF Pod를 대신 띄운다.**
  시연 중에는 노트북마다 터미널 2개(port-forward, agent)를 켜 둔다
- 워크스페이스마다 GPU가 1개라서, 폰마다 다른 워크스페이스에 붙이면 두 곡이 동시에 만들어진다
- 앱의 서버 주소는 두 폰 모두 기본값 `http://localhost:8000` 그대로 (각 폰이 자기 노트북의 8000번으로 감)
- 워크스페이스 2가 준비되지 않으면 두 폰 모두 워크스페이스 1에 붙여도 된다 (곡은 한 번에 1개씩 차례로)

| | 워크스페이스 1 | 워크스페이스 2 |
|---|---|---|
| 계정 | gpu05 | gpu22 |
| 이름 | ws-qt1ja5byz6220 | ws-xkblzn1w9n5c2 |
| 상태 | 모델·환경 설치 완료 (볼륨 `muscriptor-data`, ferrari) | 비어 있음 → **B단계에서 볼륨 만들고 1의 데이터를 복사** |
| 이 안내의 매니페스트 | `server/k8s/*.yaml` | `server/k8s/ws2/*.yaml` (ford) |

---

## A. 노트북 준비 (두 노트북 모두, 한 번만)

### A-1. 프로그램 설치 (맥 터미널)
```bash
brew --version          # 버전이 나오면 Homebrew 있음. 없으면 https://brew.sh 의 설치 한 줄을 먼저 실행
brew install kubectl kubelogin
kubectl version --client
kubectl oidc-login --version
```
- adb (Android Studio에 들어 있음). 터미널을 열 때마다 쓰기 귀찮으면 `~/.zshrc` 맨 아래에 이 줄을 추가
```bash
export PATH="$HOME/Library/Android/sdk/platform-tools:$PATH"
adb version
```
  `adb: command not found` 이면 Android Studio → Settings → Languages & Frameworks → Android SDK → **SDK Tools** 탭 → **Android SDK Platform-Tools** 체크 → Apply

### A-2. kubeconfig 받기
- 계정(gpu05, gpu22)은 팀 공용 계정이라 **여러 노트북에서 같은 계정으로 로그인해도 된다** (재욱 노트북과 채연 노트북 모두 gpu05 가능)
- 노트북에서 **한 계정만** 쓸 거면 TA 안내대로 `~/.kube/config` 로 저장하고, 아래 명령의 `k5` 대신 그냥 `kubectl` 을 써도 된다
1. 브라우저에서 https://id.snucse.org 에 개인 계정으로 로그인돼 있으면 **먼저 로그아웃** (다른 계정이 자동 로그인되는 걸 막음. 시크릿 창도 좋음)
2. https://sgs.snucse.org 에 팀 계정으로 로그인 → 워크스페이스 페이지 아래쪽에서 **kubeconfig 다운로드**
2. 파일 이름을 계정별로 바꿔서 `~/.kube/` 에 둔다
   - 워크스페이스 1 → `~/.kube/gpu05.yaml`
   - 워크스페이스 2 → `~/.kube/gpu22.yaml`
```bash
mkdir -p ~/.kube
mv ~/Downloads/<받은 파일> ~/.kube/gpu22.yaml     # 파일 이름은 실제 받은 이름으로
```

### A-3. 두 계정을 섞이지 않게 쓰는 단축 명령
두 계정은 로그인 토큰 저장 위치(`~/.kube/cache/oidc-login`)가 같아서 섞이면 `Forbidden` 이 난다.
아래처럼 계정마다 저장 위치를 나눈 단축 명령 `k5`, `k22` 를 만든다 (`~/.zshrc` 에 추가하면 계속 쓸 수 있음).
```bash
mkdir -p ~/.kube/home22
alias k5='kubectl --kubeconfig $HOME/.kube/gpu05.yaml'
alias k22='env HOME=$HOME/.kube/home22 kubectl --kubeconfig $HOME/.kube/gpu22.yaml'
```
로그인 확인 (브라우저가 열리면 해당 계정으로 로그인. **다른 계정이 자동 로그인되면 시크릿 창**에서):
```bash
k5 auth whoami          # 워크스페이스 1 계정
k22 auth whoami         # 워크스페이스 2 계정
```
- 노트북에 한 계정만 쓰면 그 단축 명령 하나만 만들어도 된다
- 그래도 Forbidden 이고 오류에 다른 계정 `User "id:..."` 가 보이면: `rm -rf ~/.kube/cache/oidc-login ~/.kube/home22/.kube/cache/oidc-login` 후 다시 로그인

### A-4. 권한 확인
```bash
k5 auth can-i create pods        # yes 여야 함 (roles·rolebindings는 no여도 괜찮음 — agent 방식)
python3 --version                # agent 실행용. 3.8 이상이면 OK (맥 기본 또는 conda)
```

### A-5. 코드 받기
```bash
cd ~
git clone -b feature/app-server-v2 https://github.com/snuhcs-course/swpp-2026-project-team-03 rocky-app-server
cd ~/rocky-app-server
```
(이미 받았다면 `cd ~/rocky-app-server && git pull`)

---

## B. 워크스페이스 2 준비 (오늘 한 번, 노트북 하나에서 — 두 계정 모두 로그인된 노트북)

### B-1. 파일 Pod 만들기 (볼륨은 수빈이 만든 `rocky-data`를 씀 — 50Gi 할당량이라 새 볼륨은 못 만듦)
```bash
cd ~/rocky-app-server
k22 get pod rocky-files || k22 apply -f server/k8s/ws2/files-pod.yaml
k22 wait --for=condition=Ready pod/rocky-files --timeout=300s
k22 get pvc,pod                 # rocky-data: Bound, rocky-files: Running
k22 exec rocky-files -- df -h /data      # 여유 20G 이상이어야 함
```
- `rocky-data`에 있는 수빈 폴더(models, envs, par, rwc 등)는 건드리지 않는다. 복사 전에 수빈에게 알리기

### B-2. 워크스페이스 1의 모델·환경을 2로 복사
먼저 크기 확인 (워크스페이스 1에 rocky-files 가 없으면 `k5 apply -f server/k8s/files-pod.yaml`):
```bash
k5 get pod rocky-files || k5 apply -f server/k8s/files-pod.yaml
k5 exec rocky-files -- du -sh /data/model /data/bsrofo /data/pipeline /data/cache /data/rocky-unified
```
복사 (워크스페이스 1 → 노트북 → 워크스페이스 2로 **흘려 보내기만 하고 노트북 디스크에는 저장하지 않는다** — 노트북 여유 공간은 필요 없음. 약 15 GB, 네트워크에 따라 10~40분. **노트북이 잠들지 않게**, 충전기 연결):
```bash
export COPYFILE_DISABLE=1
# 1) 작은 것부터
k5 exec rocky-files -- tar -C /data -cf - model bsrofo pipeline | k22 exec -i rocky-files -- tar -C /data -xf -
# 2) 패키지 캐시 + 실행 환경 (서로 연결된 파일이 있어서 한 번에)
k5 exec rocky-files -- tar -C /data -cf - --exclude=rocky-unified/runs --exclude=rocky-unified/app cache rocky-unified \
  | k22 exec -i rocky-files -- tar -C /data -xf -
# 3) 확인: 두 워크스페이스 크기가 비슷해야 함
k22 exec rocky-files -- du -sh /data/model /data/bsrofo /data/pipeline /data/cache /data/rocky-unified
k22 exec rocky-files -- ls /data/rocky-unified/.venv/bin/python /data/model/model.safetensors
```
- 중간에 끊기면 그 줄만 다시 실행 (덮어쓰기라 괜찮음)

---

## C. 서버 올리기 (워크스페이스마다)

워크스페이스 1은 `k5` 와 `server/k8s/`, 워크스페이스 2는 `k22` 와 `server/k8s/ws2/` 를 쓴다.
아래는 워크스페이스 1 예시. **2는 `k5`→`k22`, `server/k8s/api-pod.yaml`→`server/k8s/ws2/api-pod.yaml` 로 바꿔서 똑같이.**
```bash
cd ~/rocky-app-server
export COPYFILE_DISABLE=1

# 1) 서버 코드를 볼륨(/data/server)으로
tar -C server -cf - rocky_server requirements.txt | k5 exec -i rocky-files -- bash -c 'mkdir -p /data/server && tar -C /data/server -xf -'

# 2) 파이프라인이 최신(BS-RoFormer)인지: 1 이상이면 OK
k5 exec rocky-files -- grep -c bsroformer /data/pipeline/unified.py

# 3) 서버 Pod (rbac.yaml은 쓰지 않음 — 권한이 없어서 agent 방식)
k5 apply -f server/k8s/api-pod.yaml
k5 logs -f rocky-api        # 1~2분 뒤 "Uvicorn running on http://0.0.0.0:8000" 가 보이면 Ctrl+C
```
- 서버 코드를 다시 올릴 때: 1) 실행 → `k5 delete pod rocky-api` → `k5 apply -f server/k8s/api-pod.yaml`
- **PDF 도구 설치 파일 (워크스페이스마다 한 번):** PDF·키 변경 Pod는 MuseScore 3·Poppler를 `/data/cache/pdf-debs`의 .deb로 설치하고, 없을 때만 우분투 미러에서 받는다 (11/12 미러 연결이 끊겨 GPU 단계가 끝난 곡이 PDF에서 실패했음). 그 폴더는 이렇게 만든다
  ```bash
  k5 apply -f server/k8s/pdf-debs-pod.yaml      # 2는 k22, server/k8s/ws2/pdf-debs-pod.yaml
  k5 logs -f rocky-pdf-debs                     # 마지막 줄 "pdf-debs ready: ..." 확인 후 Ctrl+C
  k5 delete pod rocky-pdf-debs
  ```
  PDF Pod가 미러 설치 실패처럼 일시적인 이유로 실패하면(로그에 `ROCKY_TRANSIENT_FAILURE`, 종료 코드 75) 서버가 20초 뒤 PDF만 다시 시도한다 (최대 3번, 15분 안에서만, GPU 단계는 다시 안 함). 시간 초과·agent 없음·코드 오류는 다시 시도하지 않는다.

---

## D. 폰 연결 (시연할 때마다, 각 노트북에서)

터미널 1 (켜 둔다, 노트북1은 `k5`, 노트북2는 `k22`):
```bash
k5 port-forward pod/rocky-api 8080:8000      # 노트북 8080 (8000은 kubelogin 로그인과 부딪혀서 피함)
```
터미널 2 (켜 둔다 — GPU·PDF Pod를 띄우는 agent):
```bash
cd ~/rocky-app-server
python3 server/agent/rocky_agent.py --api http://localhost:8080        # ~/.kube/config 계정으로
# 워크스페이스 2(노트북2): env HOME=$HOME/.kube/home22 python3 server/agent/rocky_agent.py --api http://localhost:8080 --kubeconfig ~/.kube/gpu22.yaml
```
"할 일을 기다려요"가 보이면 정상. 곡이 들어오면 "Pod 생성 → 끝: Succeeded"가 찍힌다.

터미널 3:
```bash
curl localhost:8080/health        # {"ok":true}
adb devices                       # 폰이 "device" 로 보여야 함 (폰에서 USB 디버깅 허용)
adb reverse tcp:8000 tcp:8080     # 폰의 8000(앱 기본 주소) → 노트북 8080
```
- 케이블이 빠지거나 폰을 재부팅하면 `adb reverse` 를 다시. port-forward 가 끊기면 터미널 1 을 다시 (로그인이 만료되면 브라우저가 다시 뜸)
- 두 노트북이 같은 워크스페이스(gpu05)에 붙어 있으면 agent는 **한 노트북에서만** 켜도 되고, 둘 다 켜도 요청은 한 쪽만 처리한다
- agent를 `k22` 계정으로 돌릴 때는 로그인 토큰 위치도 맞춰야 한다:
  `env HOME=$HOME/.kube/home22 python3 server/agent/rocky_agent.py --kubeconfig ~/.kube/gpu22.yaml`

### 노트북 한 대로 두 워크스페이스를 동시에 시험할 때 (포트를 나눔)
```bash
k5  port-forward pod/rocky-api 8080:8000                     # 워크스페이스 1 → 노트북 8080
k22 port-forward pod/rocky-api 8081:8000                     # 워크스페이스 2 → 노트북 8081
python3 server/agent/rocky_agent.py --api http://localhost:8080
env HOME=$HOME/.kube/home22 python3 server/agent/rocky_agent.py --api http://localhost:8081 --kubeconfig ~/.kube/gpu22.yaml
adb -s <폰1> reverse tcp:8000 tcp:8080                        # 폰1 → 워크스페이스 1
adb -s <폰2> reverse tcp:8000 tcp:8081                        # 폰2 → 워크스페이스 2 (앱 주소는 그대로 localhost:8000)
```
- agent를 껐다 켜도 괜찮다: 돌던 GPU Pod는 끝까지 돌고, 다시 켠 agent가 이어서 결과를 확인한다
- **곡을 중단할 때는 앱의 취소 버튼 또는 `POST /jobs/<작업번호>/cancel`을 사용한다.** agent가 잠시 끊긴 사이 `kubectl delete pod`만 실행하면, 다음 agent가 같은 요청의 Pod를 다시 만들어 작업을 이어 간다. API의 취소 완료를 확인한 뒤 Pod 상태를 점검한다.

## E. 앱에서 확인
1. 홈 → 밴드 합주용(또는 개인 연습용) → 악기 고르기 → 곡 올리기 화면 맨 아래 **연결 설정: http://localhost:8000** → **연결 확인** → `연결됨 ✓`
2. 30초가 넘는 짧은 곡 선택 → 악보 만들기 시작 → 만드는 중 탭
3. 완료되면 카드를 눌러 악보(PDF)·듣기(MP3) 확인 → **보관함에 저장**

## F. 문제가 생기면
| 증상 | 확인 |
|---|---|
| 앱: "서버에 연결할 수 없어요" | 터미널 1의 port-forward, `adb reverse tcp:8000 tcp:8080`, `curl localhost:8080/health` |
| port-forward: "address already in use" | 이미 켜진 port-forward 또는 로그인 대기 중인 kubelogin. `lsof -nP -iTCP:8080 -sTCP:LISTEN` 로 확인 후 `kill <PID>` |
| 진행상황이 "노트북 연결(agent)을 기다리는 중" | 터미널 2의 agent가 꺼져 있음 → 다시 실행 |
| agent: "kubectl create 실패" | 로그인 만료일 수 있음 → `kubectl auth whoami` 로 다시 로그인 후 agent 재실행 |
| "GPU를 다른 작업이 쓰고 있어서 기다리는 중" | 같은 워크스페이스에 다른 GPU Pod가 있음. `k5 get pods` 로 확인 |
| "GPU 차례를 기다리는 중" 이 오래 | 그 노드(ferrari/ford)의 GPU를 다른 팀이 쓰는 중 (11/1 저녁 ferrari 40분 대기) |
| "서버에서 처리하다 멈췄어요 (...)" | `k5 logs rocky-api`, `k5 exec rocky-files -- tail -50 /data/rocky-unified/app/<작업번호>.log`, `k5 exec rocky-files -- cat /data/rocky-unified/runs/<작업번호>/manifest.json` |
| 워크스페이스 2의 GPU Pod 오류 | B-2 복사가 끝났는지(크기 비교), 모델 경로 확인 |
| 시연 중 서버가 안 되면 | 데모 곡·데모 결과는 11/11에 앱에서 뺐음. 미리 만들어 보관함에 저장해 둔 악보로 시연 |

- 곡마다 결과는 `/data/rocky-unified/runs/<작업번호>/` 에 남는다 (분리 음원은 끝나면 지움)
- **시연 전에 실제 곡 2~3개를 미리 돌려 각 폰 보관함에 저장**해 두면 평가자가 기다리지 않는다
- 평가 시간에는 팀원들에게 GPU Pod를 띄우지 말라고 공유
