# m3 마이그레이션 검증 프롬프트

아래 내용을 새 Claude Code 세션에 그대로 붙여넣어서 실행하세요.

---

## Claude Code에게 전달할 프롬프트

```
나는 Task-Link-clean의 세 에이전트 폴더를 Code-Shepherd/backend/m3 안으로 방금 옮겼어.
아래 체크리스트를 순서대로 전부 실행하고, 각 항목에 OK / FAIL / 수정완료 로 표시해줘.
FAIL이 나오면 바로 그 자리에서 고쳐줘.

작업 디렉토리: C:\Users\user\Desktop\Code-Shepherd\backend\m3

────────────────────────────────────────
## STEP 1. 폴더 구조 확인
────────────────────────────────────────
m3 루트에 아래 항목이 모두 있는지 확인해줘:

폴더:
- test-performance-agent/
- pr-comment-agent/
- webhook-gateway/
- app/
- alembic/
- tests/

파일:
- pyproject.toml
- Dockerfile
- README.md

────────────────────────────────────────
## STEP 2. 각 에이전트 폴더 내부 핵심 파일 확인
────────────────────────────────────────

### test-performance-agent/ 안에 있어야 할 것:
- 폴더: assemble, config, conventions, docs, enrich, filter, performance, prepare, rag, test_verification, validation, tests
- 파일: contracts.py, harness.py, main.py, persist.py, tracing.py, .env.example
- tests/ 안에: test_task1_contracts.py ~ test_task16_harness.py 포함 여부, fixtures/ 폴더

### pr-comment-agent/ 안에 있어야 할 것:
- 파일: aggregator.py, contracts.py, github_poster.py, llm_refiner.py, main.py
- 폴더: config/, tests/, validation/

### webhook-gateway/ 안에 있어야 할 것:
- 파일: gateway.py, registry.py, server.py
- 폴더: agents/, tests/

────────────────────────────────────────
## STEP 3. m3/tests/ 확인 (오염 여부)
────────────────────────────────────────
m3/tests/ 안에는 아래 두 파일만 있어야 해:
- test_contract.py
- __init__.py

그 외 다른 파일이 있으면 FAIL — 해당 파일을 test-performance-agent/tests/ 로 이동해줘.

────────────────────────────────────────
## STEP 4. pyproject.toml 확인
────────────────────────────────────────
C:\Users\user\Desktop\Code-Shepherd\backend\m3\pyproject.toml 을 읽어서:

dependencies에 아래가 모두 있는지 확인:
- fastapi
- uvicorn
- pydantic
- psycopg2-binary
- google-generativeai
- sentence-transformers
- pyyaml
- langsmith

[tool.pytest.ini_options] 에 아래가 있는지 확인:
- pythonpath = ["."]
- addopts = "-v --ignore=tests/fixtures"

없으면 추가해줘.

────────────────────────────────────────
## STEP 5. import 경로 오류 확인
────────────────────────────────────────
아래 파일들을 읽어서 import 문이 m3/test-performance-agent/ 기준으로
상대경로 없이 동작 가능한지 확인해줘:

- test-performance-agent/main.py
- test-performance-agent/persist.py
- test-performance-agent/harness.py
- test-performance-agent/assemble/output.py
- test-performance-agent/rag/augment.py

확인 기준:
- "from contracts import" → test-performance-agent/ 루트에 contracts.py 있으면 OK
- "from config import" → test-performance-agent/config/ 있으면 OK
- "from shared.contracts import" → 이건 m3/app/ 전용이므로 test-performance-agent 파일엔 없어야 정상
- 만약 "from shared." 로 시작하는 import가 test-performance-agent 파일에 있으면 FAIL로 표시

────────────────────────────────────────
## STEP 6. 불필요 파일 확인
────────────────────────────────────────
아래 파일/폴더가 m3 루트나 에이전트 폴더 안에 있으면 삭제해줘:
- __pycache__/ (어디든)
- .pytest_cache/ (어디든)
- *.pyc 파일
- .coverage 파일
- demo_output.json
- showcase_issues.json

────────────────────────────────────────
## STEP 7. 최종 트리 출력
────────────────────────────────────────
모든 체크가 끝나면 m3 폴더의 구조를 아래 형식으로 출력해줘:

m3/
├── test-performance-agent/
│   ├── assemble/
│   ├── config/
│   └── ... (하위 폴더만, 파일은 생략)
├── pr-comment-agent/
│   └── ...
├── webhook-gateway/
│   └── ...
├── app/
├── alembic/
├── tests/
│   ├── test_contract.py
│   └── __init__.py
├── pyproject.toml
├── Dockerfile
└── README.md

각 STEP 결과를 OK / FAIL / 수정완료 로 요약해서 마지막에 표로 정리해줘.
```
