# dev3 m3 drop-in 이미지 — 팀 compose 의 m3 서비스 자리에 들어간다 (포트 8004).
# 비밀키는 이미지에 절대 포함하지 않는다 — 런타임 env_file/-e 로만 주입.
FROM python:3.13-slim

WORKDIR /app

# build context = ./backend (팀 규약) → 경로 prefix m3/
COPY m3/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY m3/contracts/ contracts/
COPY m3/src/ src/
COPY m3/corpus/ corpus/

# 도커 내부 → 호스트 ollama (직접실행은 localhost — .env 만으로 전환)
ENV OLLAMA_BASE_URL=http://host.docker.internal:11434
ENV ENABLE_DB_WRITE=true

EXPOSE 8004

# 인덱스(.chroma)는 볼륨 마운트 권장 — 없으면 최초 1회:
#   docker exec <ctr> python -m src.ingestion
CMD ["uvicorn", "src.adapters.http_adapter:app", "--host", "0.0.0.0", "--port", "8004"]
