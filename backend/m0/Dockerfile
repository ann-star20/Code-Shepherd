FROM python:3.12-slim

RUN pip install uv

WORKDIR /app

COPY _shared /app/_shared
COPY m0 /app/service

WORKDIR /app/service

RUN uv sync --no-dev

EXPOSE 8002

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
