FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    libreoffice \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

WORKDIR /app

COPY _shared /app/_shared
COPY m0 /app/service

WORKDIR /app/service

RUN uv sync --no-dev

EXPOSE 8002

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002"]
