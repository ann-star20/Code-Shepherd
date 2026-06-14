docker compose down -v
docker compose up -d redis neo4j_m6 cloud-sql-proxy api-core frontend m6 celery_worker_m6
docker compose up -d frontend
docker compose restart celery_worker_m6
docker compose logs -f --tail 100
docker compose up neo4j_m6_seed
docker compose up -d redis neo4j_m6 cloud-sql-proxy api-core frontend m6 celery_worker_m6 && docker compose logs -f --tail 100
docker compose up -d --force-recreate celery_worker_m6
docker compose restart celery_worker_m6 && docker compose logs -f --tail 100

docker compose up neo4j_m6_seed

cd backend\m6
.\.venv-win\Scripts\python.exe  script\seed_neo4j.py

cd backend\m6
.\.venv-win\Scripts\python.exe script\seed_neo4j.py

cd C:\Users\user\Documents\ai-work\Code-Sheperd-Team\backend\m6
Remove-Item -Recurse -Force .venv-win
C:\Users\user\AppData\Local\Programs\Python\Python314\python.exe -m venv .venv-win
.\.venv-win\Scripts\python.exe -m pip install -r requirements.txt
.\.venv-win\Scripts\python.exe script\seed_neo4j.py