FROM python:3.12-slim AS base

RUN pip install uv

WORKDIR /app

COPY _shared /app/_shared
COPY m1 /app/service

WORKDIR /app/service

RUN uv sync --no-dev

EXPOSE 8001

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
