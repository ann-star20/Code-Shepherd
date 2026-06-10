# Code Shepherd Docker 가이드

Docker는 각 모듈을 독립된 컨테이너로 실행하는 도구이고, Docker Compose는 api-core, m0~m5, frontend 같은 여러 서비스를 한 번에 결합해서 운영할 수 있게 해준다.

---

## 1. 프로젝트 구조 확인

우리 프로젝트는 이런 구조다.

```
Code-Shepherd/
├── backend/
│   ├── _shared/           ← 공통 패키지 (각 모듈이 공유)
│   ├── api-core/          ← API 게이트웨이 (포트 8000)
│   │   ├── app/
│   │   ├── pyproject.toml
│   │   └── Dockerfile
│   ├── m0/                ← 포트 8002
│   ├── m1/                ← 포트 8001
│   ├── m2/                ← 포트 8003
│   ├── m3/                ← 포트 8004
│   ├── m4/                ← 포트 8005
│   └── m5/                ← 포트 8006 (Neo4j 연동)
├── frontend/              ← Vite + React (포트 5173)
└── docker-compose.yml     ← 전체를 하나로 묶는 파일
```

---

## 2. 각 모듈의 Dockerfile 구조

모든 모듈은 같은 패턴이다. uv로 의존성을 관리하고, _shared 패키지를 함께 복사한다.

### 예시: backend/m1/Dockerfile

```dockerfile
FROM python:3.12-slim

RUN pip install uv

WORKDIR /app

COPY _shared /app/_shared
COPY m1 /app/service

WORKDIR /app/service

RUN uv sync --no-dev

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
```

**주의:** build context를 ./backend로 설정해야 _shared와 각 모듈을 함께 복사할 수 있다.

---

## 3. docker-compose.yml (루트에 위치)

docker-compose.yml은 루트에 있으며 모든 서비스를 하나의 네트워크(code-shepherd)로 묶는다.

서비스별 포트 정리:
- api-core: 8000
- m0: 8002
- m1: 8001
- m2: 8003
- m3: 8004
- m4: 8005
- m5: 8006 (Neo4j depends_on)
- neo4j: 7474 / 7687
- frontend: 5173

---

## 4. 서비스 간 통신

Docker Compose 안에서는 localhost가 아니라 **서비스 이름**으로 호출한다.

```python
# 잘못된 예
M2_URL = "http://localhost:8003"

# 올바른 예
M2_URL = "http://m2:8003"
```

예를 들어 api-core에서 각 모듈 호출:

```python
import os
import httpx

M1_URL = os.getenv("M1_URL", "http://m1:8001")
M2_URL = os.getenv("M2_URL", "http://m2:8003")
M3_URL = os.getenv("M3_URL", "http://m3:8004")

async def call_m2(payload: dict):
    async with httpx.AsyncClient() as client:
        response = await client.post(f"{M2_URL}/analyze/static", json=payload)
        response.raise_for_status()
        return response.json()
```

---

## 5. 실행 방법

### 전체 실행

```bash
# 프로젝트 루트에서
docker compose up --build
```

### 백그라운드 실행

```bash
docker compose up -d --build
```

### 특정 모듈만 실행

```bash
docker compose up --build m2 api-core frontend
```

### 확인

```
http://localhost:8000/docs  ← api-core
http://localhost:8001/docs  ← m1
http://localhost:8002/docs  ← m0
http://localhost:8003/docs  ← m2
http://localhost:8004/docs  ← m3
http://localhost:8005/docs  ← m4
http://localhost:8006/docs  ← m5
http://localhost:5173        ← frontend
http://localhost:7474        ← Neo4j 브라우저
```

---

## 6. 자주 쓰는 Docker 명령어

```bash
# 중지
docker compose down

# 로그 전체
docker compose logs -f

# 특정 모듈 로그만
docker compose logs -f m2

# 캐시 없이 다시 빌드
docker compose build --no-cache

# 실행 중인 컨테이너 확인
docker ps
```

---

## 7. 주의사항

### uvicorn host는 반드시 0.0.0.0

```dockerfile
# 잘못된 예 — 컨테이너 외부에서 접근 불가
CMD ["uvicorn", "app.main:app", "--host", "127.0.0.1"]

# 올바른 예
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0"]
```

### _shared 패키지

build context는 반드시 ./backend여야 _shared를 같이 복사할 수 있다.

```yaml
build:
  context: ./backend      ← 이게 없으면 _shared 복사 안 됨
  dockerfile: m1/Dockerfile
```

### 포트 매핑

```yaml
ports:
  - "8001:8001"   # 호스트포트:컨테이너포트
```

왼쪽이 내 컴퓨터 포트, 오른쪽이 컨테이너 안 포트다.

---

## 8. 권장 실행 순서

1. 먼저 m2만 단독으로 테스트

```bash
docker compose up m2 --build
# → http://localhost:8003/docs
```

2. api-core 추가

```bash
docker compose up api-core m2 --build
# → http://localhost:8000/docs
```

3. 전체 실행

```bash
docker compose up --build
```
