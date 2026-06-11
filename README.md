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


  cd frontend && npm run build

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
docker compose exec postgres psql -U postgres -c "UPDATE documents SET state='PENDING' WHERE doc_id='EXT_https---docs-djangoproject-com-en-6-0-topics-security_32450f22'"
docker compose exec postgres psql -U postgres -c "UPDATE documents SET state='PENDING' WHERE doc_id='EXT_https---docs-nestjs-com-security-csrf_4a05f756'"
docker compose exec postgres psql -U postgres -c "UPDATE documents SET state='PENDING' WHERE doc_id='EXT_https---react-dev-reference-react-dom-preload_5c6ba4d2'"
docker compose exec postgres psql -U postgres -c "UPDATE documents SET state='PENDING' WHERE doc_id='EXT_https---react-dev-reference-react-dom-preloadModule_228f692f'"
https://docs.nestjs.com/security/csrf
# 1. Neo4j 볼륨 내 오염된 데이터 및 인덱스 잔재 영구 격리 삭제 후 재가동
docker compose down -v
docker compose up --build

# 2. 인프라가 안정화될 때까지 5초 대기 후 마이그레이션 스크립트 재실행
sleep 5
docker compose exec backend python scripts/seed_postgres.py && docker compose exec backend python scripts/seed_neo4j.py

 docker-compose logs -f -t


 docker compose down -v frontend && docker compose --no-cache build frontend
 docker compose down -v frontend && docker compose --no-cache build frontend
 docker compose up

 # 1. 실행 중인 컨테이너 정지 및 볼륨(구버전 캐시) 삭제
docker compose down -v

# 2. 캐시를 완전히 무시하고 처음부터 이미지 새로 빌드 및 실행
docker compose up --build --force-recreate

docker compose down -v frontend & docker compose build --no-cache frontend;
docker compose up
https://docs.nestjs.com/security/csrf


# 1. 실행 중인 celery 워커 컨테이너의 ID 또는 이름을 확인합니다.
docker ps

# 2. Celery 컨테이너 내부 쉘로 진입합니다.
docker exec -it <celery_container_name> sh
docker exec -it c98fd6897901 sh
# 3. 컨테이너 내부에서 API 키 환경변수를 출력해봅니다.
echo $GEMINI_API_KEY
$GEMINI_API_KEY=v

docker compose down backend celery_worker-1
docker compose up -d --build --force-recreate backend celery_worker-1

# 1. backend와 celery_worker 컨테이너만 지정해서 완전히 중지 및 삭제
docker compose stop backend celery_worker
docker compose rm -f backend celery_worker

# 2. 새 .env 설정을 반영하여 두 컨테이너만 강제로 다시 만들어 백그라운드로 실행
docker compose up -d --force-recreate backend celery_worker


# 기본 빌드
docker compose up --build frontend && docker compose restart celery_worker
docker compose up frontend