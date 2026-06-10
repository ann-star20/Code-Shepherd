FROM python:3.12-slim

# git: prepare_repo()가 PR 분석 전 레포를 clone 한다(subprocess git clone).
# slim 베이스엔 git이 없어 /verify/tests 가 FileNotFoundError → 500 이 됐다.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

RUN pip install uv

WORKDIR /app

COPY _shared /app/_shared
COPY m3 /app/service

WORKDIR /app/service

RUN uv sync --no-dev

EXPOSE 8004

CMD ["uv", "run", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8004"]
