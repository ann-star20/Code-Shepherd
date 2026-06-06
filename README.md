# Task-Link
신입사원 업무지원 플랫폼


  <!-- postgres:16 (5433:5432)
  neo4j:5     (7687, 7474 브라우저 UI)
  backend     (8000) ← postgres + neo4j 헬스체크 후 기동
  frontend    (3000) ← nginx이 /api/ → backend:8000 프록시 -->

  # 풀 스택 실행
  docker compose up --build

  # 백엔드 테스트 (compose 네트워크 안에서)
  docker compose run --rm backend pytest backend/tests/ -v

  # 프론트 unit 테스트 (mock, 서버 불필요)
  cd frontend && npm test
