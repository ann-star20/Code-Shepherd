FROM python:3.12-slim

RUN pip install uv

WORKDIR /app

COPY _shared /app/_shared
COPY m2 /app/service

WORKDIR /app/service

RUN pip install pylint radon bandit && \
    uv sync --no-dev --extra analysis

EXPOSE 8003

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
