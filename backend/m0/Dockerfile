FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    fonts-noto-cjk \
    fonts-nanum \
    fontconfig \
    && fc-cache -fv \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

WORKDIR /app

COPY _shared /app/_shared
COPY m0 /app/service

WORKDIR /app/service

# venv를 /app/.venv 에 생성 — 볼륨 마운트(/app/service) 밖에 위치시켜
# Docker Desktop 9P 파일시스템 경유 import 행 방지
ENV UV_PROJECT_ENVIRONMENT=/app/.venv
RUN uv sync --no-dev

EXPOSE 8002

CMD ["/app/.venv/bin/python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
