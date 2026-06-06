# ngrok으로 GitHub 웹훅 → 로컬 테스트 (무조건 되는 방법) · 팀 공유용

> **목적**: 진짜 GitHub PR을 올렸을 때, 그 웹훅을 **내 노트북에서 도는 m1(localhost:8001)** 까지 받아
> 전체 파이프라인(m1 → m2/m3 → m4)을 로컬에서 진짜로 돌려본다.
>
> **이 문서 하나면**: ① 직접 따라 해도 되고, ② Claude 같은 에이전트에게 "이거 해줘" 하면 그대로 실행도 된다.
> (맨 아래 §"🤖 에이전트에게 시키기" 참고)

```
GitHub (PR 오픈) → 웹훅 → ngrok 공개주소(https://xxxx.ngrok-free.app)
   → 내 m1 (localhost:8001) /triggers/pr → api-core(ingest) → m2/m3 → m4
```

---

## ⚠️ 왜 이 방법인가 (전에 겪은 삽질 요약)
- **winget으로 깐 ngrok은 너무 옛날 버전(3.3.1)** → ngrok 서버가 거부함(`ERR_NGROK_121`, "agent too old", 최소 3.20.0 요구) + 설정파일 버전 충돌(`unknown version '3'`).
- **설치 폴더가 PATH에 안 잡혀** `ngrok: CommandNotFoundException` (특히 VS Code 통합 터미널은 재시작 전까지 옛 PATH 사용).

→ **해결 원칙 2가지 (이게 핵심):**
> ① **최신 ngrok**을 단순한 위치 `C:\ngrok` 에 **직접 설치** (winget 쓰지 않음)
> ② **항상 전체 경로 `C:\ngrok\ngrok.exe` 로 실행** (PATH 신경 안 씀 → 절대 "명령 못 찾음" 안 남)

---

## 0. 사전 조건
- 로컬 스택이 떠 있어야 함: **frontend(5173) · api-core(8000) · m1(8001) · m2(8003) · m3(8004) · m4(8005)**
- m1 webhook 검증 시크릿 = **루트 `.env` 의 `GITHUB_WEBHOOK_SECRET`** 값 (§5 웹훅 설정에 그대로 넣음)
- 본인 **ngrok authtoken** (https://dashboard.ngrok.com/get-started/your-authtoken 에서 복사)

---

## 1. ⭐ 최신 ngrok 설치 (PowerShell — 통째로 복붙)
```powershell
$dir = "C:\ngrok"
New-Item -ItemType Directory -Force -Path $dir | Out-Null
Invoke-WebRequest -Uri "https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-windows-amd64.zip" -OutFile "$dir\ngrok.zip"
Expand-Archive -Path "$dir\ngrok.zip" -DestinationPath $dir -Force
Remove-Item "$dir\ngrok.zip" -Force
& "$dir\ngrok.exe" version
```
→ 마지막 줄에서 **`ngrok version 3.20.0` 이상**이 나오면 성공. (옛날 winget 버전은 이제 무시해도 됨)

## 2. 내 ngrok 토큰 등록 (최초 1회)
```powershell
& "C:\ngrok\ngrok.exe" config add-authtoken <본인_ngrok_토큰>
```
> ⚠️ `<본인_ngrok_토큰>` 자리에 dashboard에서 복사한 **진짜 토큰**을 넣는다(그 글자 그대로 X). 토큰은 비밀이므로 이 문서·채팅·git에 적지 말 것.

## 3. 검증 (둘 다 통과해야 함)
```powershell
& "C:\ngrok\ngrok.exe" version       # 3.20.0 이상?
& "C:\ngrok\ngrok.exe" config check  # "Valid configuration file" ?
```

## 4. 터널 켜기
```powershell
& "C:\ngrok\ngrok.exe" http 8001
```
→ 이렇게 뜨면 성공:
```
Session Status   online
Forwarding       https://xxxx.ngrok-free.app -> http://localhost:8001
```
**`https://xxxx.ngrok-free.app`** 주소를 복사한다. ⚠️ **이 터미널은 켜둔 채로 둔다**(닫으면 터널 끊김).

---

## 5. GitHub 레포에 웹훅 등록
레포 → **Settings → Webhooks → Add webhook**:

| 칸 | 값 |
|---|---|
| **Payload URL** | `https://xxxx.ngrok-free.app/triggers/pr`  ← 끝에 **`/triggers/pr` 필수** |
| **Content type** | `application/json` |
| **Secret** | 루트 `.env` 의 `GITHUB_WEBHOOK_SECRET` 값과 **글자까지 동일** |
| **Which events?** | "Let me select individual events" → **Pull requests** 만 체크 |
| **Active** | ✓ |

→ **Add webhook** 클릭.

## 6. 웹사이트에서 레포 등록 + PR 발생
1. **웹사이트(http://localhost:5173)** 접속 → GitHub 로그인 → 내 레포 등록
   - ⚠️ 레포명을 **글자까지 정확히** (`owner/repo`). 다르면 ingest 404.
   - 이걸로 팀·유저·멤버십이 자동 생성됨(수동 DB 작업 불필요). PR 작성자=내 계정이라 자동 매칭.
2. 레포에서 **PR을 새로 열거나**, 기존 PR을 **Close → Reopen** → 웹훅 발사.

## 7. 결과 확인 — GitHub "Recent Deliveries"
웹훅 설정 페이지의 **Recent Deliveries** 탭에서 응답 코드 확인:
| 코드 | 의미 | 조치 |
|---|---|---|
| **200** | 성공 (m1이 잘 받음) | ✅ |
| **401** | 서명 불일치 | Secret이 m1 `.env`와 같은지 |
| **404** | 레포/작성자/멤버 매칭 실패 | 레포명·로그인 계정·팀 멤버십 확인 |
| **빨간 X / timeout** | m1까지 못 감 | ngrok 켜져 있나·주소·`/triggers/pr` 경로 확인 |
> 첫 delivery가 `ping`(200)이면 정상 — GitHub이 웹훅 등록 시 보내는 신호.

---

## 🤖 에이전트(Claude 등)에게 통째로 시키기 (복붙용)
직접 하기 싫으면 아래를 그대로 에이전트에게 주면 §1~§3을 대신 해준다:
```
docs/ngrok_로컬_웹훅_테스트_가이드.md 를 읽고 §1~§3을 그대로 실행해줘.
- 최신 ngrok을 C:\ngrok 에 설치(§1)
- 내 authtoken 등록(§2): <여기에_내_토큰>
- 검증(§3): `ngrok version`이 3.20 이상인지 + `config check`가 "Valid"인지 확인해서 보고
터널(§4 `& "C:\ngrok\ngrok.exe" http 8001`)은 내가 직접 켤게(켜두고 있어야 하니까).
설치·검증 결과만 표로 알려줘.
```

---

## 트러블슈팅 빠른표
| 증상 | 원인 | 해결 |
|---|---|---|
| `ngrok: CommandNotFoundException` | (winget 방식의) PATH 문제 | **이 문서 방식대로 전체경로 `C:\ngrok\ngrok.exe` 사용** → 안 생김 |
| `unknown version '3'. valid versions are: [1 2]` | 옛날 ngrok이 새 설정파일 못 읽음 | **최신 설치(§1)** 하면 사라짐 |
| `ERR_NGROK_121` / "agent too old" | ngrok 버전이 3.20.0 미만 | **최신 설치(§1)** |
| `ERR_NGROK_4018` / authtoken 요구 | 토큰 미등록 | §2 토큰 등록 |
| 웹훅 401 | secret 불일치 | §5 Secret = m1 `.env` 동일 |
| 웹훅 404 | 레포/유저/멤버 미등록 | §6 웹사이트에서 레포 등록 + 본인 로그인 |
| ngrok 주소가 매번 바뀜 | 무료 플랜 특성 | 터널 다시 켤 때마다 §5 Payload URL 갱신 |

> 💡 **무료 ngrok은 켤 때마다 공개주소가 바뀐다.** 다시 켜면 GitHub 웹훅 Payload URL도 새 주소로 바꿔야 한다.
> 💡 모든 명령은 `ngrok` 대신 **`& "C:\ngrok\ngrok.exe"`** 로 쓴다(PATH 무관, 절대 실패 없음).
