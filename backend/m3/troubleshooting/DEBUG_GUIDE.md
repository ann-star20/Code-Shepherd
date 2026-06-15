# PR 코드리뷰 디버깅 가이드

PR을 열었는데 GitHub 코멘트가 안 달릴 때, 이 순서대로 체크한다.

---

## 빠른 진단 (먼저 이것부터)

```bash
# 1. 컨테이너 전부 살아있나?
docker ps --format "table {{.Names}}\t{{.Status}}"

# 2. ngrok 살아있나?
curl http://localhost:4040/api/tunnels

# 3. m3 health
curl http://localhost:8004/health

# 4. Ollama + bge-m3
python backend/m3/_check_ollama.py
```

---

## 경우의 수 체크리스트

### CASE 1 — GitHub 웹훅 설정 문제
**증상**: PR 만들어도 m1 로그에 아무것도 안 찍힘

**체크**:
- GitHub 레포 → Settings → Webhooks → 해당 웹훅 클릭
- Payload URL이 ngrok 주소와 일치하는지 확인
  - 맞는 형식: `https://xxxx.ngrok-free.app`
  - 포트 없이 도메인만 (ngrok이 443 처리)
- Content type: `application/json`
- 이벤트: `Pull requests` 체크됐는지
- Active 체크됐는지

**해결**:
```
Payload URL = ngrok이 보여주는 Forwarding URL 그대로 붙여넣기
```

---

### CASE 2 — ngrok 꺼져있음
**증상**: GitHub Webhooks → Recent Deliveries에 `ERR_NGROK_3200` 또는 connection refused

**체크**:
```bash
# ngrok 상태
curl http://localhost:4040/api/tunnels
# 응답 없으면 ngrok 꺼진 것
```

**해결**:
```bash
ngrok http 8001
# 새 URL이 나오면 GitHub 웹훅 URL도 업데이트 해야 함
```

---

### CASE 3 — 웹훅 시크릿 불일치
**증상**: GitHub Deliveries에 `HTTP 400` 또는 `invalid signature`

**체크**:
- GitHub 웹훅 설정의 Secret 값
- `.env` 파일의 `GITHUB_WEBHOOK_SECRET` 값
- 두 개가 정확히 일치해야 함 (앞뒤 공백 없이)

**해결**:
```bash
# .env에서 확인 (값 직접 보지 말고 길이만 확인)
python -c "import os; from dotenv import load_dotenv; load_dotenv(); s=os.getenv('GITHUB_WEBHOOK_SECRET',''); print(f'길이: {len(s)}')"
```

---

### CASE 4 — Ollama 미설치 / 미실행
**증상**: m3 로그에 `connection refused` 또는 `ollama`관련 에러

**체크**:
```bash
python backend/m3/_check_ollama.py
```

**해결**:
```bash
# Ollama 설치: https://ollama.com
# 설치 후 서버 실행
ollama serve

# bge-m3 모델 다운로드 (약 1.2GB, 시간 걸림)
ollama pull bge-m3
```

---

### CASE 5 — m3 컨테이너 에러
**증상**: `curl http://localhost:8004/health` 응답 없음 또는 500

**체크**:
```bash
docker logs code-shepherd-new-m3-1 --tail 30
```

**해결**:
```bash
docker-compose restart m3
# 또는 재빌드
docker-compose up -d --build m3
```

---

### CASE 6 — m1 타임아웃 (첫 번째 PR에서 자주 발생)
**증상**: m1 로그에 `pr_trigger_dispatch_error`, error 필드가 빈 문자열

**원인**: bge-m3 cold start 시 m3 `/review`가 60초 초과

**체크**:
```bash
docker logs code-shepherd-new-m1-1 --tail 20
# pr_trigger_dispatch_error 보이면 이 케이스
```

**해결**: PR을 close 후 reopen하면 두 번째에 warm 상태라 성공함
```
GitHub PR → Close pull request → Reopen
```

---

### CASE 7 — ANTHROPIC_API_KEY 없음 / 만료
**증상**: m3 로그에 `AuthenticationError` 또는 `401`

**체크**:
```bash
docker exec code-shepherd-new-m3-1 env | grep ANTHROPIC
```

**해결**: `.env`에 유효한 키 설정 후 `docker-compose up -d m3`

---

### CASE 8 — GITHUB_TOKEN 권한 부족
**증상**: 파이프라인은 돌아가는데 GitHub 코멘트가 안 달림

**체크**:
```bash
# 토큰 권한 확인
python -c "
import os, requests
from dotenv import load_dotenv; load_dotenv()
token = os.getenv('GITHUB_TOKEN')
r = requests.get('https://api.github.com/user', headers={'Authorization': f'Bearer {token}'})
print(r.status_code, r.json().get('login'))
"
```

**해결**: GitHub → Settings → Developer settings → Personal access tokens
- `repo` 권한 필요 (pull_requests read/write)

---

### CASE 9 — 포트 충돌
**증상**: `docker-compose up` 시 `address already in use`

**체크**:
```bash
# 8001, 8004 포트 점유 확인
netstat -ano | findstr ":8001"
netstat -ano | findstr ":8004"
```

**해결**:
```bash
# 점유 프로세스 종료 (PID 확인 후)
taskkill /PID <PID번호> /F
```

---

### CASE 10 — pgVector 연결 실패
**증상**: m3 로그에 `could not connect to server` 또는 DB 관련 에러

**체크**:
```bash
docker logs code-shepherd-new-postgres-1 --tail 10
# 또는
docker ps | grep postgres
```

**해결**:
```bash
docker-compose restart postgres
docker-compose restart m3
```

---

## 로그 실시간 모니터링 (PR 트리거 시 켜놓기)

```bash
# m1 (웹훅 수신)
docker logs code-shepherd-new-m1-1 -f

# m3 (리뷰 실행 — 노드별 OK/FAIL 찍힘)
docker logs code-shepherd-new-m3-1 -f
```

---

## GitHub Webhooks Recent Deliveries 상태별 의미

| 상태 | 의미 | 해결 |
|------|------|------|
| `200` | 정상 수신 | - |
| `timeout` | 10초 내 응답 못 받음 (정상 처리 중일 수도) | Deliveries 상세에서 실제 에러 확인 |
| `ERR_NGROK_3200` | ngrok 연결 끊김 | ngrok 재시작 후 URL 업데이트 |
| `400` | 시크릿 불일치 | CASE 3 |
| `404` | 엔드포인트 없음 | m1 컨테이너 확인 |
| `500` | 서버 에러 | m1/m3 로그 확인 |
