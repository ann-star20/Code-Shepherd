# Dev3 테스트 샌드박스 — 신입 PR 코드를 격리 실행해 커버리지 측정 (TECH_SPEC §9.2)
# 사용: docker build -t dev3-sandbox -f prepare/Dockerfile prepare/
#       (settings.SANDBOX_IMAGE = "dev3-sandbox")
FROM python:3.12-slim
RUN pip install --no-cache-dir pytest pytest-cov coverage
WORKDIR /work
