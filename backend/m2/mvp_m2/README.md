# M2 MVP - 정적 분석 · 보안 스캔

## 포함 파일

### 백엔드
- backend/m2/app/main.py — FastAPI 엔드포인트 (/analyze/static, /analyze/security)
- backend/m2/app/analyzer.py — Pylint · Radon · Bandit 분석 도구 실행
- backend/m2/Dockerfile — 컨테이너 빌드
- backend/m2/pyproject.toml — 의존성 정의

### 프론트엔드
- frontend/src/pages/security/SecurityPage.tsx — 정적 분석 · 보안 스캔 페이지
- frontend/src/components/M2PipelineFlow.tsx — 파이프라인 시각화 컴포넌트
- frontend/src/layouts/AppLayout.tsx — 사이드바 레이아웃
- frontend/src/App.tsx — /security 라우트 등록

## 실행 방법
docker compose up -d api-core frontend m2
접속: http://localhost:5173/security

## API
POST http://localhost:8003/analyze/static
POST http://localhost:8003/analyze/security
