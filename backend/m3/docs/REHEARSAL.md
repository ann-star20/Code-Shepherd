# REHEARSAL.md — 시연 리허설 완전 가이드

> 처음 보는 사람도 이것만 보고 따라할 수 있게 작성. 준비물 생성부터 시연까지 전부 포함.
> **PART 1 = 준비물 만들기 (1회만)** → **PART 2 = 환경 켜기** → **PART 3 = 4장면 리허설**

---

# 이 시연이 증명하려는 것 (먼저 이해)

우리 코드리뷰 에이전트가 일반 AI(Copilot 등)와 다른 점 3가지:
1. **세계 기준이 아니라 우리 회사 KMS 기준으로 본다** — requests처럼 세상에선 멀쩡한 것도 사내 규칙이면 잡는다
2. **모르면 모른다고 한다** — KMS에 없으면 지어내지 않고 "규정 없음"으로 정직 보고
3. **지침이 바뀌면 코드 수정 없이 검사가 따라간다** — corpus 문서만 고치면 판정이 바뀜

4개 장면은 각각 이 중 하나를 보여준다:
- 장면1 = 차별점 1 (위반 탐지 + 근거 인용)
- 장면2 = 차별점 1 심화 (예외조항까지 이해)
- 장면3 = 차별점 2 (지침공백 정직 보고)
- 장면4 = 차별점 3 (핫스왑) ← **주인공**

---

# PART 1 — 준비물 만들기 (시연 전 1회만)

> 4장면에 쓸 테스트 PR을 미리 다 만들어둔다. 시연 당일엔 "PR 열기" 버튼만 누르면 되게.
> 작업 위치: `-dev3-demo` repo 로컬 클론.

## 1-0. 데모 repo 클론 (이미 있으면 skip)
```powershell
cd C:\Users\user
git clone https://github.com/kskt1234-netizen/-dev3-demo.git
cd "C:\Users\user\-dev3-demo"
```

## 1-1. 장면1 준비물 — SQL injection 위반 (브랜치)
```powershell
cd "C:\Users\user\-dev3-demo"
git checkout main
git checkout -b demo/scene1-sql-injection

@"
from database import db

def get_user(user_id: str):
    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    return db.execute(query)
"@ | Out-File -FilePath "user_service.py" -Encoding utf8

git add user_service.py
git commit -m "scene1: user service"
git push origin demo/scene1-sql-injection
```
> 함수 1개만 둠 (ISSUE-1 중복 코멘트 수정 전이면 2개일 때 중복 보이니, 시연용은 1개 권장)

## 1-2. 장면2 준비물 — scripts/ 예외 (브랜치)
```powershell
git checkout main
git checkout -b demo/scene2-scripts-exception
mkdir scripts -ErrorAction SilentlyContinue

@"
import requests

def backfill_orders():
    resp = requests.get("https://legacy.internal/orders", timeout=30)
    return resp.json()
"@ | Out-File -FilePath "scripts\batch_job.py" -Encoding utf8

git add scripts/batch_job.py
git commit -m "scene2: batch job in scripts"
git push origin demo/scene2-scripts-exception
```
> async에서 requests 쓰는 패턴이지만 `scripts/` 경로 → §4 예외조항으로 미지적되어야 함

## 1-3. 장면3 준비물 — gap (브랜치)
```powershell
git checkout main
git checkout -b demo/scene3-gap-subprocess

@"
import subprocess

def run_migration(script_path: str):
    result = subprocess.run(["python", script_path], capture_output=True, check=True)
    return result.stdout
"@ | Out-File -FilePath "migration_runner.py" -Encoding utf8

git add migration_runner.py
git commit -m "scene3: migration runner"
git push origin demo/scene3-gap-subprocess
```
> subprocess는 KMS에 규정 없음 → gap 리포트 나와야 함

## 1-4. 장면4 준비물 — 핫스왑 (httpx 정상 코드 + 스왑 문서)
```powershell
git checkout main
git checkout -b demo/scene4-hotswap

@"
import httpx

async def call_external_api(url: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        return resp.json()
"@ | Out-File -FilePath "api_client.py" -Encoding utf8

git add api_client.py
git commit -m "scene4: httpx async client"
git push origin demo/scene4-hotswap
```
> 스왑 **전**: httpx는 정상(권장 라이브러리) → 위반 없음
> 스왑 **후**: corpus를 "httpx 금지 → aiohttp"로 바꾸면 → 같은 코드가 위반으로 뒤집힘

**스왑용 corpus 문서 확인** — `backend/m3/fixtures/demo/hotswap_external_api.md`가 있는지 확인.
없으면 만들기 (httpx 대신 aiohttp 강제 내용으로):
```powershell
# 원본 corpus/external_api.md 를 복사해서 httpx→aiohttp 로 바꾼 버전
# CC에게 "hotswap_external_api.md를 aiohttp 강제 버전으로 만들어줘" 요청하면 됨
```

## 1-5. PR 4개 생성 (GitHub 웹에서)
각 브랜치로 PR을 만들어두되 **아직 분석은 안 돌게** — 시연 때 열거나, 미리 열어두고 시연 때 reopen.
- `demo/scene1-sql-injection` → main : 제목 `[Demo] SQL injection`
- `demo/scene2-scripts-exception` → main : 제목 `[Demo] scripts batch`
- `demo/scene3-gap-subprocess` → main : 제목 `[Demo] subprocess`
- `demo/scene4-hotswap` → main : 제목 `[Demo] httpx async`

> 팁: 시연 직전 PR을 열면 그 자리에서 분석이 도니까 "실시간 분석" 느낌이 난다. 단 m1 60초 타임아웃 대비 캐시 워밍은 미리 1회.

---

# PART 2 — 환경 켜기 (시연/리허설 시작 30분 전)

## 2-1. Docker Desktop 실행
시작 메뉴 → Docker Desktop → 고래 아이콘 초록불 대기

## 2-2. Ollama 확인
```powershell
ollama list
```
`bge-m3:latest` 있으면 OK. 없으면 `ollama pull bge-m3`

## 2-3. 전체 스택 기동
```powershell
cd C:\Users\user\Code-Shepherd-new
docker compose up -d
```
1분 대기 후 확인:
```powershell
docker ps --format "table {{.Names}}\t{{.Status}}" | Select-String "m1|m3|frontend"
```
m1·m3·frontend 전부 `Up`

## 2-4. ngrok 기동 (새 터미널)
```powershell
ngrok http --domain=phonics-underwent-scrounger.ngrok-free.app 8001
```
`Forwarding ... -> http://localhost:8001` 보이면 OK

## 2-5. GitHub 웹훅 확인
`-dev3-demo` → Settings → Webhooks:
- Payload URL이 위 ngrok 주소와 일치
- Secret이 `.env`의 `GITHUB_WEBHOOK_SECRET`과 일치
- Events: **Pull requests** 만 체크 (opened 위주)

## 2-6. 캐시 워밍 (첫 분석 느림 방지)
```powershell
docker exec code-shepherd-new-m3-1 python -m src.ingestion
```
`40청크` 메시지 = 완료

## 2-7. 브라우저 탭 미리 열기
- 탭 1: `http://localhost:5173` (프론트)
- 탭 2: `https://github.com/kskt1234-netizen/-dev3-demo/pulls`

## 2-8. 안전장치
- `grep ENABLE_DB_WRITE "C:\Users\user\Code-Shepherd-new\.env"` → false 확인 (DB 보여줄 거면 그 장면만 true)
- 화면 녹화 시작 (라이브 실패 시 폴백)

---

# PART 3 — 4장면 리허설

## 장면 1 — 위반 탐지 (3분)
**증명: "세계 기준이 아니라 우리 회사 KMS 기준으로 본다"**

1. GitHub 탭 → `[Demo] SQL injection` PR 열기 (또는 reopen)
2. 멘트: "PR이 올라오면 자동 분석이 시작됩니다."
3. 30초~1분 대기 (캐시 워밍 했으면 빠름)
4. **GitHub PR 새로고침** → 코멘트 확인
   - CONV-SQL-008 인용, 위반 코드, 사내 `db.safe_query()` 교정 지시
5. 멘트: "일반 AI는 SQL을 잡아도 '파라미터 바인딩 쓰세요'라는 일반론만 말합니다. 우리는 사내 `db.safe_query()`를 쓰라고, 출처까지 달아서 말합니다."
6. **프론트 탭** → /review → 이 PR 선택 → `RAG 파이프라인 실행 흐름` 토글 펼치기
   - ⓪입력수집 → ①개념추출 → ②KMS검색 → ③충분성 → ④판정 → ⑤코멘트, 각 단계 소요시간
7. 멘트: "어떤 근거로 판단했는지 단계별로 추적됩니다."

**✅ 통과 기준:** 코멘트 달림 + rule_id 인용 + 프론트 trace 보임

---

## 장면 2 — 오탐 회피 (1분)
**증명: "예외조항까지 이해한다"**

1. GitHub 탭 → `[Demo] scripts batch` PR 열기
2. 대기 후 확인 → **Major 위반 코멘트 없음** (또는 Info만)
3. 멘트: "같은 requests 패턴인데 여기선 지적하지 않습니다. `scripts/` 폴더는 §4 예외조항이 있거든요. 규칙의 예외까지 KMS에서 읽습니다."

**✅ 통과 기준:** Major violation 없음

---

## 장면 3 — 지침공백 정직 보고 (1분)
**증명: "모르면 모른다고 한다"**

1. GitHub 탭 → `[Demo] subprocess` PR 열기
2. 대기 후 확인 → **gap 리포트** ("subprocess 관련 사내 규정 없음")
3. 멘트: "일반 AI는 모르는 영역도 뭔가 지어내서 지적합니다. 우리는 KMS에 없으면 '규정 없음'이라고 정직하게 보고합니다. 환각이 0%인 이유입니다."

**✅ 통과 기준:** 지어낸 위반 없음 + gap 리포트 있음

---

## 장면 4 — 핫스왑 (3분) ← 주인공
**증명: "지침이 바뀌면 코드 수정 없이 검사가 따라간다"**

### 4-1. 스왑 전 (정상 확인)
1. GitHub 탭 → `[Demo] httpx async` PR 열기
2. 확인 → **위반 없음** (httpx는 현재 권장 라이브러리)
3. 멘트: "이 코드는 httpx를 씁니다. 지금 우리 규칙은 httpx를 권장하니 통과입니다."

### 4-2. 지침 변경 (corpus 수정)
```powershell
copy "C:\Users\user\Code-Shepherd-new\backend\m3\fixtures\demo\hotswap_external_api.md" "C:\Users\user\Code-Shepherd-new\backend\m3\corpus\external_api.md"
```
멘트: "방금 지침 문서를 바꿨습니다. httpx 대신 aiohttp를 쓰라고요. **코드는 한 줄도 안 건드렸습니다.**"

### 4-3. 재인덱싱
```powershell
docker exec code-shepherd-new-m3-1 python -m src.ingestion
```
멘트: "지침만 재인덱싱했습니다."

### 4-4. 같은 PR 재실행
- `[Demo] httpx async` PR을 **reopen** (close 후 reopen, 또는 새 커밋 push)
- 대기 후 확인 → **이번엔 httpx가 위반으로 뒤집힘**
- 멘트: "같은 코드인데 판정이 바뀌었습니다. 코드가 아니라 지침을 따라갑니다. 이게 규칙 기반 시스템의 힘입니다."

### 4-5. 원복 (반드시)
```powershell
cd C:\Users\user\Code-Shepherd-new
git checkout backend/m3/corpus/
docker exec code-shepherd-new-m3-1 python -m src.ingestion
```
> ⚠️ **스왑 상태에서 `make eval` 절대 금지** — 골든셋 지표가 깨진 것처럼 보임

**✅ 통과 기준:** 스왑 후 판정 뒤집힘 → 원복 → eval 12/12 정상

---

# 리허설 완료 기준

| 장면 | 통과 |
|---|---|
| 1 | 코멘트 + 인용 + trace |
| 2 | Major 없음 |
| 3 | gap 리포트 |
| 4 | 뒤집힘 → 원복 |

**4개 × 2회 통과 = v1 완료**

---

# 폴백 플랜

| 상황 | 대응 |
|---|---|
| ngrok 끊김 | 재기동 (고정 도메인이라 URL 유지) |
| 프론트 안 뜸 | `cd backend/m3 && make demo` (Streamlit) |
| API 한도 | 캐시 히트 재실행 (같은 diff면 0원) |
| 라이브 사고 | 녹화본 재생 |
| PR 분석 안 옴 | `docker logs code-shepherd-new-m1-1 --tail 20` 로 웹훅 수신 확인 → ngrok·secret 점검 |

---

# 외울 멘트 3개
1. "세계 기준이 아니라 우리 회사 KMS 기준으로 봅니다"
2. "모르면 모른다고 합니다 — 지어내지 않습니다"
3. "지침이 바뀌면 코드 수정 없이 검사가 따라갑니다"
