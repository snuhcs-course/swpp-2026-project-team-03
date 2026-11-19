# 공개 주소로 서버 열기 (USB 없이)

폰을 노트북에 USB로 꽂지 않아도, APK만 깔면 어디서든(와이파이·LTE) 앱이 서버에 붙게 하는 설정이다.
2026-11-18부터 이 방식으로 운영 중이다. 예전 USB 방식(`adb reverse`)은 [../DEPLOY_ko.md](../DEPLOY_ko.md)의 D절에 있다.

## 1. 구조

```
폰 (어디서든)
 │  http://team3.swpp-2026-b.snu.ac.kr   ← APK에 이 주소와 API 키가 들어 있음
 ▼
수업 공개 HAProxy → 팀 서버 swpp-b nginx :80          (nginx-rocky.conf)
 │  127.0.0.1:18081 로 넘김
 ▼
[노트북] SSH 역방향 터널: 팀 서버 18081 → 노트북 8081   (tunnel.sh)
 ▼
[노트북] kubectl port-forward: 노트북 8081 → pod/rocky-api :8000
 ▼
gpu22 클러스터 rocky-api pod (볼륨 rocky-data, 노드 ford)
   곡이 들어오면 [노트북] agent가 GPU pod(rocky-midi-…)를 만들어 처리
```

- 노트북이 맡는 일은 세 가지다: port-forward, SSH 터널, agent.
- 노트북이 꺼지면 서버와 데이터는 그대로지만, 앱의 모든 기능(로그인 포함)이 멈춘다.
- 노트북은 **학교 와이파이 또는 학교 VPN**에 있어야 한다. 팀 서버 SSH는 학교 밖에서 막혀 있다. 클러스터(kubectl)는 집에서도 된다.
- 터널은 **한 번에 노트북 한 대만** 열 수 있다 (팀 서버 18081 포트를 같이 쓴다). agent는 여러 대에서 켜도 된다.

## 2. 파일

| 파일 | 놓는 곳 | 내용 |
|---|---|---|
| `nginx-rocky.conf` | 팀 서버 `/etc/nginx/sites-available/rocky` (+ `sites-enabled/rocky` 링크) | 업로드 200MB, 타임아웃 300초, `X-Rocky-Key` 전달 |
| `tunnel.sh` | 다리 역할 노트북 | 끊기면 자동으로 다시 연결하는 SSH 역방향 터널 |
| `../k8s/ws2/api-pod.yaml` | 클러스터 | `ROCKY_API_KEY`를 Secret `rocky-api-key`에서 읽음 |

## 3. 처음 한 번만 하는 설정

### 3-1. API 키 Secret (클러스터)

```bash
# 키 끝에 줄바꿈이 들어가면 맞는 키도 401이 난다. --from-literal 로 만들 것
k22 create secret generic rocky-api-key --from-literal=ROCKY_API_KEY="$(tr -d '\n' < api-key)"
k22 delete pod rocky-api && k22 apply -f server/k8s/ws2/api-pod.yaml
```

- `/health`를 뺀 모든 요청에 헤더 `X-Rocky-Key`가 필요해진다.
- 키 값은 git, 문서, 단톡방에 올리지 않는다. 필요한 사람에게 개인 메시지로 준다.

### 3-2. 팀 서버 nginx

```bash
scp server/deploy/nginx-rocky.conf swpp-b:/tmp/rocky
ssh swpp-b 'sudo mv /tmp/rocky /etc/nginx/sites-available/rocky &&
  sudo ln -sf /etc/nginx/sites-available/rocky /etc/nginx/sites-enabled/rocky &&
  sudo rm -f /etc/nginx/sites-enabled/default &&
  sudo nginx -t && sudo systemctl reload nginx'
```

- 팀 서버는 IPv6를 지원하지 않아서 `listen [::]:80` 줄을 넣으면 `nginx -t`가 실패한다.

### 3-3. APK

```bash
./gradlew assembleDebug -Procky.serverUrl=http://team3.swpp-2026-b.snu.ac.kr -Procky.apiKey=$(cat api-key)
```

- 앱 '서버 설정' 화면에 저장한 값이 빌드 값보다 우선한다. 예전에 `localhost`가 저장된 폰은 설정을 지우거나 앱 데이터를 지운다.

## 4. 다리 역할 노트북 준비물

1. `kubectl`과 OIDC 로그인 플러그인(`kubectl oidc-login`), gpu22 kubeconfig (`~/.kube/gpu22.yaml`)
2. 팀 서버 SSH: 본인 swpp 계정과 키로 `~/.ssh/config`에 아래를 추가

   ```
   Host swpp-b-jump
     HostName 147.46.242.174
     Port 26022
     User swpp26jump
     IdentityFile <본인 키 경로>
     IdentitiesOnly yes

   Host swpp-b
     HostName 10.226.0.13
     HostKeyAlias swpp26t03.b
     User <본인 swpp 계정>
     IdentityFile <본인 키 경로>
     IdentitiesOnly yes
     ProxyJump swpp-b-jump
   ```

   - 처음 접속할 때 서버 열쇠 지문을 확인한다:
     - jump `[147.46.242.174]:26022` = `SHA256:jtsrQ7OgvzaaL7fSADAmEVWgGT2T+tMzuf3CeGL1RUM`
     - 팀 서버 `swpp26t03.b` = `SHA256:ifagWFJuTNc4Fa09Gx8eUyBB+oR1hIZ0xFkhDqema8I`
   - 확인: `ssh swpp-b hostname` → `swpp26t03`
3. API 키 (개인 메시지로 받기)

## 5. 켜는 순서

**0) 넘겨받을 때:** 기존 노트북에서 터널을 먼저 끄고 "껐어"를 받은 뒤 진행한다.

**터미널 1: 클러스터 연결** (멈추면 자동 재시작)

```bash
while true; do kubectl --kubeconfig ~/.kube/gpu22.yaml port-forward pod/rocky-api 8081:8000; sleep 2; done
```

- port-forward는 포트는 열려 있는데 응답이 없는 상태로 멈출 때가 있다(`error creating error stream … Timeout`). 그러면 Ctrl+C로 끊어 반복문이 다시 연결하게 한다.

**터미널 2: 팀 서버 터널**

```bash
server/deploy/tunnel.sh
```

**터미널 3: agent** (저장소 루트에서)

```bash
python3 server/agent/rocky_agent.py --kubeconfig ~/.kube/gpu22.yaml --api http://127.0.0.1:8081 --key '<API 키>'
```

**맥이라면 잠자기 방지:** `caffeinate -dimsu` (전원 연결, 덮개는 열어 둠)

## 6. 확인

| 확인 | 명령 | 정상 |
|---|---|---|
| 클러스터 연결 | `curl -s localhost:8081/health` | `{"ok":true}` |
| 공개 주소 | `curl -s http://team3.swpp-2026-b.snu.ac.kr/health` | `{"ok":true}` |
| 키 검사 | `curl -s -o /dev/null -w '%{http_code}' http://team3.swpp-2026-b.snu.ac.kr/bands` | `401` |
| 앱 요청 | `ssh swpp-b 'sudo tail /var/log/nginx/access.log'` | 폰 요청이 `Dalvik/…`로 찍힘 |

## 7. 문제가 생기면

| 증상 | 원인과 해결 |
|---|---|
| 앱: "서버에 연결할 수 없어요" | 6절 표를 위에서부터 확인하고, 끊긴 곳의 터미널을 다시 켠다 |
| 공개 주소가 `502 Bad Gateway` | nginx는 살아 있고 터널이 끊김. 터미널 2 확인 |
| 터널: `remote port forwarding failed` | 다른 노트북이 아직 터널을 열고 있음. 그쪽을 먼저 끈다 |
| 터널: `Connection reset` / `Network is unreachable` | 학교 밖 네트워크. 학교 와이파이나 VPN에 연결 |
| 브라우저 로그인 창이 뜸 | 클러스터 로그인 토큰 만료(약 1시간마다). 로그인하면 다시 돈다 |
| 앱만 401 | 폰 앱 '서버 설정'에 예전 주소나 빈 키가 저장됨. 지우고 다시 연다 |

## 8. 하면 안 되는 것

- API 키를 화면 출력, 파일, 커밋, 로그에 남기지 않는다.
- 터널을 두 개 열지 않는다.
- `rocky-api` pod나 볼륨 `rocky-data`를 이유 없이 지우지 않는다. 회원·밴드·보관함 데이터가 들어 있다.
