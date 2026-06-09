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



# db지우기
윈도우(PowerShell) 예시: Remove-Item -Recurse -Force ${env:USERPROFILE}/neo4j/*
rm -rf ~/neo4j/* && rm -rf ~/postgres/*

# 볼륨 연동 해제 후 삭제, 그리고 다시 클린 빌드 구동
rm -rf ~/neo4j/* ~/postgres/*
docker compose down -v && docker compose up
<!-- docker compose down -v && rm -rf ~/neo4j/* ~/postgres/* && docker compose up -->

# 초기화용 JSON 데이터로 기존 데이터를 덮어쓰기
docker compose exec backend python scripts/seed_postgres.py && docker compose exec backend python scripts/seed_neo4j.py


# DB 리셋 (원하는 경우)
docker compose exec postgres psql -U postgres -c "UPDATE documents SET state='PENDING' WHERE doc_id='EXT_https---docs-nestjs-com-security-csrf_4a05f756'"
<!-- docker compose exec postgres psql -U postgres -c "UPDATE documents SET state='PENDING' WHERE doc_id='EXT_https---docs-djangoproject-com-en-6-0-topics-security_32450f22'" -->
https://docs.nestjs.com/security/csrf


# 1. Neo4j 볼륨 내 오염된 데이터 및 인덱스 잔재 영구 격리 삭제 후 재가동
docker compose down -v
docker compose up -d --build

# 2. 인프라가 안정화될 때까지 5초 대기 후 마이그레이션 스크립트 재실행
sleep 5
docker compose exec backend python scripts/seed_postgres.py && docker compose exec backend python scripts/seed_neo4j.py

 docker-compose logs -f -t