FROM python:3.12-slim AS base

RUN pip install uv

WORKDIR /app

# _shared 패키지 복사
COPY _shared /app/_shared

# 서비스 코드 복사
COPY api-core /app/service

WORKDIR /app/service

# 의존성 설치 (_shared를 로컬 패키지로 설치)
RUN uv sync --no-dev

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
