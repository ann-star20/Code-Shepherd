# api-core

**담당 범위**: GitHub OAuth 로그인, 사용자/팀 관리, JWT 인증/세션, 헬스체크.

## 실행법

```bash
# Docker Compose (권장)
docker compose up api-core

# 직접 실행 (개발)
cd backend/api-core
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

## 테스트

```bash
uv run pytest tests/ --cov=app --cov-report=term-missing
```

커버리지 게이트: **≥ 80%**

## DB 마이그레이션

```bash
uv run alembic upgrade head      # 최신 스키마 적용
uv run alembic downgrade base    # 롤백
uv run alembic revision --autogenerate -m "desc"  # 새 마이그레이션 생성
```

## 엔드포인트 요약

| 메서드 | 경로 | 설명 |
|--------|------|------|
| GET | /health | 헬스체크 (DB 연결 확인) |
| GET | /auth/authorize | GitHub OAuth 시작 |
| GET | /auth/callback | OAuth 콜백 → JWT 발급 |
| GET | /auth/me | 내 정보 |
| POST | /auth/logout | 세션 무효화 |
| POST | /auth/refresh | access 토큰 갱신 |
| GET | /users?search= | 사용자 검색 |
| GET | /teams | 내 팀 목록 |
| POST | /teams | 팀 생성 |
| PATCH | /teams/{id} | 팀 수정 (lead만) |
| DELETE | /teams/{id} | 팀 삭제 (lead만) |
| GET | /teams/{id}/members | 멤버 목록 |
| POST | /teams/{id}/members | 멤버 추가 (lead만) |
| DELETE | /teams/{id}/members/{uid} | 멤버 제거 (lead만) |
| PATCH | /teams/{id}/members/{uid} | 역할 변경 (lead만) |
| GET | /teams/{id}/prs | PR 현황 (스텁) |
| POST | /prs/{id}/approve | PR 승인 (스텁) |

## 권한 정책

- 비인증 → 401
- 팀 비소속자 팀 리소스 접근 → 403
- member의 팀 관리(수정/삭제/멤버변경) → 403
- 마지막 lead 제거/강등 → 409

## 확장 지점

- `app/services/auth_service.py`: OAuth 범위 추가, 소셜 로그인 확장
- `app/models/`: 도메인 모델 확장 (PR, Review 등)
- `app/routers/`: 새 도메인 라우터 추가
- `alembic/versions/`: 스키마 마이그레이션 추가 (api-core 소유)
