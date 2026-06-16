"""11개 KMS 컨벤션 규칙 전체 pgVector 재인덱싱 스크립트

각 규칙마다 §0(개요) §1(원인/위험) §2(BAD 패턴) §3(GOOD 패턴) 4개 청크로 구성.
UUID5 결정적 ID — 반복 실행해도 중복 없이 UPSERT.

사용법:
  docker exec code-shepherd-new-m3-1 python scripts/index_all_rules.py
  python scripts/index_all_rules.py  # 로컬 직접 실행
"""
from __future__ import annotations

import os, sys, uuid
from pathlib import Path
from dotenv import load_dotenv

_HERE = Path(__file__).parent
sys.path.insert(0, str(_HERE.parent))
load_dotenv()

from src.embeddings import embed_texts  # noqa: E402

_NS = uuid.UUID("a1b2c3d4-e5f6-7890-abcd-ef1234567890")

# ── 규칙별 KMS 청크 정의 ──────────────────────────────────────────────────────

RULES: list[dict] = [

    # ── CONV-API-001 ────────────────────────────────────────────────────────────
    {
        "rule_id": "CONV-API-001", "severity": "Major",
        "storage_path": "kms_docs/api_sync.md", "category": "코딩컨벤션",
        "chunks": [
            {
                "section": "§0",
                "text": (
                    "[CONV-API-001] 동기 HTTP 호출 금지 — severity: Major\n\n"
                    "핵심 키워드: 동기 requests, blocking HTTP, 이벤트루프 블로킹, "
                    "requests.get, requests.post, httpx sync, urllib\n\n"
                    "규칙: async 함수 내부에서 동기 HTTP 라이브러리(requests, urllib)를 "
                    "호출하면 이벤트 루프 전체가 블로킹된다. "
                    "모든 외부 HTTP 호출은 httpx.AsyncClient 또는 aiohttp를 사용해야 한다."
                ),
            },
            {
                "section": "§1",
                "text": (
                    "CONV-API-001 §1 — 왜 위험한가\n\n"
                    "FastAPI, asyncio 기반 서비스에서 requests.get()을 호출하면 "
                    "해당 스레드가 응답 올 때까지 완전히 멈춘다. "
                    "단일 이벤트 루프를 공유하는 모든 coroutine이 대기 상태가 되어 "
                    "처리량(TPS)이 급격히 감소한다.\n\n"
                    "영향: 평균 응답시간 3~10배 증가, 동시 요청 처리 불가, "
                    "timeout cascade(연쇄 타임아웃) 발생 위험."
                ),
            },
            {
                "section": "§2",
                "text": (
                    "CONV-API-001 §2 — BAD 패턴\n\n"
                    "# BAD - async 함수 안에서 동기 requests 사용\n"
                    "import requests\n\n"
                    "async def get_user_data(user_id: str) -> dict:\n"
                    "    response = requests.get(f'https://api.example.com/users/{user_id}')\n"
                    "    return response.json()  # 이벤트루프 블로킹!\n\n"
                    "# BAD - urllib 사용\n"
                    "import urllib.request\n\n"
                    "async def fetch(url: str) -> bytes:\n"
                    "    return urllib.request.urlopen(url).read()  # 동기 블로킹"
                ),
            },
            {
                "section": "§3",
                "text": (
                    "CONV-API-001 §3 — GOOD 패턴\n\n"
                    "# GOOD - httpx.AsyncClient 사용\n"
                    "import httpx\n\n"
                    "async def get_user_data(user_id: str) -> dict:\n"
                    "    async with httpx.AsyncClient() as client:\n"
                    "        response = await client.get(f'https://api.example.com/users/{user_id}')\n"
                    "        return response.json()\n\n"
                    "# GOOD - aiohttp 사용\n"
                    "import aiohttp\n\n"
                    "async def fetch(url: str) -> dict:\n"
                    "    async with aiohttp.ClientSession() as session:\n"
                    "        async with session.get(url) as resp:\n"
                    "            return await resp.json()"
                ),
            },
        ],
    },

    # ── CONV-TIME-002 ───────────────────────────────────────────────────────────
    {
        "rule_id": "CONV-TIME-002", "severity": "Major",
        "storage_path": "kms_docs/time_complexity.md", "category": "코드성능검증",
        "chunks": [
            {
                "section": "§0",
                "text": (
                    "[CONV-TIME-002] 시간복잡도 위반 — severity: Major\n\n"
                    "핵심 키워드: O(n²), 중첩 루프, 이중 for문, nested loop, "
                    "시간복잡도, 알고리즘 복잡도, 성능 저하\n\n"
                    "규칙: 리스트 탐색이 중첩되어 O(n²) 이상의 복잡도가 발생하는 "
                    "코드는 허용하지 않는다. "
                    "dict/set 조회(O(1))나 정렬 후 이진탐색(O(n log n))으로 개선해야 한다."
                ),
            },
            {
                "section": "§1",
                "text": (
                    "CONV-TIME-002 §1 — 왜 위험한가\n\n"
                    "데이터 100건: O(n²) = 10,000번 연산 → 무시 가능\n"
                    "데이터 10,000건: O(n²) = 100,000,000번 연산 → 수십 초 지연\n"
                    "데이터 100,000건: O(n²) = 10^10번 연산 → 사실상 무한 대기\n\n"
                    "프로덕션에서 데이터가 늘어날수록 기하급수적으로 느려져 "
                    "서비스 다운 또는 타임아웃을 유발한다."
                ),
            },
            {
                "section": "§2",
                "text": (
                    "CONV-TIME-002 §2 — BAD 패턴\n\n"
                    "# BAD - O(n²) 중첩 루프\n"
                    "def find_duplicates(items: list) -> list:\n"
                    "    duplicates = []\n"
                    "    for i in range(len(items)):\n"
                    "        for j in range(i + 1, len(items)):\n"
                    "            if items[i] == items[j]:  # O(n²)\n"
                    "                duplicates.append(items[i])\n"
                    "    return duplicates\n\n"
                    "# BAD - list in 연산 (O(n)) * 루프 (O(n)) = O(n²)\n"
                    "def filter_valid(orders: list, valid_ids: list) -> list:\n"
                    "    return [o for o in orders if o['id'] in valid_ids]  # O(n²)"
                ),
            },
            {
                "section": "§3",
                "text": (
                    "CONV-TIME-002 §3 — GOOD 패턴\n\n"
                    "# GOOD - set 사용으로 O(n)\n"
                    "def find_duplicates(items: list) -> list:\n"
                    "    seen = set()\n"
                    "    return [x for x in items if x in seen or seen.add(x)]  # O(n)\n\n"
                    "# GOOD - set 변환 후 조회 O(n)\n"
                    "def filter_valid(orders: list, valid_ids: list) -> list:\n"
                    "    valid_set = set(valid_ids)  # O(n) 변환\n"
                    "    return [o for o in orders if o['id'] in valid_set]  # O(1) 조회"
                ),
            },
        ],
    },

    # ── CONV-LOG-003 ───────────────────────────────────────────────────────────
    {
        "rule_id": "CONV-LOG-003", "severity": "Minor",
        "storage_path": "kms_docs/logging.md", "category": "코딩컨벤션",
        "chunks": [
            {
                "section": "§0",
                "text": (
                    "[CONV-LOG-003] 로깅 규칙 위반 — severity: Minor\n\n"
                    "핵심 키워드: print문 프로덕션, logging 미사용, print() 디버깅, "
                    "로그 레벨, logger, logging.info\n\n"
                    "규칙: 프로덕션 코드에서 print()를 사용하지 않는다. "
                    "반드시 Python logging 모듈을 사용하고 적절한 레벨(DEBUG/INFO/WARNING/ERROR)을 지정한다."
                ),
            },
            {
                "section": "§1",
                "text": (
                    "CONV-LOG-003 §1 — 왜 위험한가\n\n"
                    "print()는 stdout에만 출력되어 중앙 로그 수집 시스템(ELK, CloudWatch)에서 수집이 어렵다.\n"
                    "로그 레벨 필터링 불가 → 디버그 메시지와 에러 메시지를 구분할 수 없다.\n"
                    "민감한 정보(토큰, 패스워드)가 print로 노출될 위험이 있다.\n"
                    "컨테이너 환경에서 stdout 버퍼링으로 실시간 확인이 어렵다."
                ),
            },
            {
                "section": "§2",
                "text": (
                    "CONV-LOG-003 §2 — BAD 패턴\n\n"
                    "# BAD - print 사용\n"
                    "def process_order(order_id: str) -> dict:\n"
                    "    print(f'Processing order {order_id}')  # CONV-LOG-003 위반\n"
                    "    result = db.get_order(order_id)\n"
                    "    print(f'Order result: {result}')  # 민감정보 노출 위험\n"
                    "    return result\n\n"
                    "# BAD - 에러를 print로만 출력\n"
                    "try:\n"
                    "    risky_operation()\n"
                    "except Exception as e:\n"
                    "    print(f'Error: {e}')  # 에러 추적 불가"
                ),
            },
            {
                "section": "§3",
                "text": (
                    "CONV-LOG-003 §3 — GOOD 패턴\n\n"
                    "import logging\n\n"
                    "logger = logging.getLogger(__name__)\n\n"
                    "# GOOD - logging 모듈 사용\n"
                    "def process_order(order_id: str) -> dict:\n"
                    "    logger.info('Processing order %s', order_id)\n"
                    "    result = db.get_order(order_id)\n"
                    "    logger.debug('Order fetched successfully')\n"
                    "    return result\n\n"
                    "# GOOD - 에러 로깅\n"
                    "try:\n"
                    "    risky_operation()\n"
                    "except Exception as e:\n"
                    "    logger.error('Operation failed: %s', e, exc_info=True)"
                ),
            },
        ],
    },

    # ── CONV-DB-004 ────────────────────────────────────────────────────────────
    {
        "rule_id": "CONV-DB-004", "severity": "Critical",
        "storage_path": "kms_docs/db_connection.md", "category": "코딩컨벤션",
        "chunks": [
            {
                "section": "§0",
                "text": (
                    "[CONV-DB-004] DB 연결 풀 미사용 — severity: Critical\n\n"
                    "핵심 키워드: DB 연결 풀, connection pool, 직접 연결, "
                    "psycopg2.connect 매번, SQLAlchemy pool, DB 연결 누수\n\n"
                    "규칙: DB 연결을 요청마다 새로 생성하지 않는다. "
                    "반드시 Connection Pool(SQLAlchemy, psycopg2 pool 등)을 사용한다. "
                    "연결 후 반드시 close() 또는 context manager로 반환한다."
                ),
            },
            {
                "section": "§1",
                "text": (
                    "CONV-DB-004 §1 — 왜 위험한가\n\n"
                    "DB 연결 생성 비용: 일반적으로 100~300ms (TCP 핸드셰이크 + 인증)\n"
                    "요청마다 새 연결: 1,000 TPS 서비스에서 초당 1,000개 연결 시도 → DB 과부하\n"
                    "연결 누수: close() 없이 종료 → DB max_connections 도달 → 새 연결 불가\n"
                    "PostgreSQL 기본 max_connections = 100 → 100개 초과 시 전체 서비스 장애"
                ),
            },
            {
                "section": "§2",
                "text": (
                    "CONV-DB-004 §2 — BAD 패턴\n\n"
                    "import psycopg2\n\n"
                    "# BAD - 요청마다 새 연결 생성\n"
                    "def get_user(user_id: str) -> dict:\n"
                    "    conn = psycopg2.connect(host='db', dbname='app')  # 매번 새 연결\n"
                    "    cur = conn.cursor()\n"
                    "    cur.execute('SELECT * FROM users WHERE id = %s', (user_id,))\n"
                    "    result = cur.fetchone()\n"
                    "    # close() 없음 → 연결 누수!\n"
                    "    return result"
                ),
            },
            {
                "section": "§3",
                "text": (
                    "CONV-DB-004 §3 — GOOD 패턴\n\n"
                    "from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession\n"
                    "from sqlalchemy.orm import sessionmaker\n\n"
                    "# GOOD - 앱 시작 시 풀 1회 생성\n"
                    "engine = create_async_engine(\n"
                    "    DATABASE_URL,\n"
                    "    pool_size=10,\n"
                    "    max_overflow=20,\n"
                    ")\n"
                    "AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession)\n\n"
                    "# GOOD - context manager로 세션 사용\n"
                    "async def get_user(user_id: str) -> dict:\n"
                    "    async with AsyncSessionLocal() as session:\n"
                    "        result = await session.execute(...)\n"
                    "        return result.fetchone()"
                ),
            },
        ],
    },

    # ── CONV-DEP-005 ───────────────────────────────────────────────────────────
    {
        "rule_id": "CONV-DEP-005", "severity": "Major",
        "storage_path": "kms_docs/dependency.md", "category": "코딩컨벤션",
        "chunks": [
            {
                "section": "§0",
                "text": (
                    "[CONV-DEP-005] 의존성 버전 미고정 — severity: Major\n\n"
                    "핵심 키워드: requirements.txt 버전 미고정, 의존성 버전, "
                    "pip install without version, unpinned dependency, 패키지 버전\n\n"
                    "규칙: requirements.txt 또는 pyproject.toml에서 의존성 버전을 "
                    "반드시 고정(==)하거나 범위(>=x,<y)로 명시한다. "
                    "버전 없이 패키지명만 작성하는 것은 금지한다."
                ),
            },
            {
                "section": "§1",
                "text": (
                    "CONV-DEP-005 §1 — 왜 위험한가\n\n"
                    "버전 미고정 시 `pip install` 때마다 최신 버전 설치 → "
                    "어제 빌드와 오늘 빌드가 다른 코드 실행\n\n"
                    "실제 사례:\n"
                    "- requests 2.x → 3.x 메이저 업그레이드 시 API 변경으로 런타임 에러\n"
                    "- pydantic 1.x → 2.x 마이그레이션으로 전체 모델 재작성 필요\n"
                    "- 보안 취약점이 있는 구버전이 의도치 않게 설치될 수 있음"
                ),
            },
            {
                "section": "§2",
                "text": (
                    "CONV-DEP-005 §2 — BAD 패턴\n\n"
                    "# BAD - requirements.txt 버전 미고정\n"
                    "requests\n"
                    "fastapi\n"
                    "sqlalchemy\n"
                    "pydantic\n\n"
                    "# BAD - 너무 넓은 버전 범위\n"
                    "requests>=2.0\n"
                    "fastapi>=0.1\n\n"
                    "# BAD - pyproject.toml에서 버전 없이 추가\n"
                    "dependencies = ['requests', 'httpx', 'aiohttp']"
                ),
            },
            {
                "section": "§3",
                "text": (
                    "CONV-DEP-005 §3 — GOOD 패턴\n\n"
                    "# GOOD - requirements.txt 버전 고정\n"
                    "requests==2.31.0\n"
                    "fastapi==0.104.1\n"
                    "sqlalchemy==2.0.23\n"
                    "pydantic==2.5.0\n\n"
                    "# GOOD - pyproject.toml 범위 지정\n"
                    "[project]\n"
                    "dependencies = [\n"
                    "    'requests>=2.31.0,<3.0.0',\n"
                    "    'fastapi>=0.100.0,<1.0.0',\n"
                    "]"
                ),
            },
        ],
    },

    # ── CONV-ERR-006 ───────────────────────────────────────────────────────────
    {
        "rule_id": "CONV-ERR-006", "severity": "Major",
        "storage_path": "kms_docs/error_handling.md", "category": "코딩컨벤션",
        "chunks": [
            {
                "section": "§0",
                "text": (
                    "[CONV-ERR-006] 에러 처리 누락 — severity: Major\n\n"
                    "핵심 키워드: bare except, except pass, 에러 무시, "
                    "Exception 미처리, 광범위한 예외처리, try except pass\n\n"
                    "규칙: bare except(except:), except Exception: pass 패턴은 "
                    "금지한다. 모든 예외는 구체적인 타입으로 잡고 로깅 또는 "
                    "재발생(raise)시켜야 한다."
                ),
            },
            {
                "section": "§1",
                "text": (
                    "CONV-ERR-006 §1 — 왜 위험한가\n\n"
                    "except pass: 에러가 발생해도 조용히 무시 → 데이터 손실, "
                    "서비스 불일치 상태 유지, 디버깅 불가\n\n"
                    "bare except: KeyboardInterrupt, SystemExit까지 잡아 "
                    "프로세스 종료가 안 되는 좀비 프로세스 생성 위험\n\n"
                    "except Exception as e: pass: 에러 원인을 알 수 없어 "
                    "장애 대응 시간이 기하급수적으로 늘어남"
                ),
            },
            {
                "section": "§2",
                "text": (
                    "CONV-ERR-006 §2 — BAD 패턴\n\n"
                    "# BAD - bare except\n"
                    "try:\n"
                    "    result = risky_call()\n"
                    "except:  # 모든 예외 무시 (CONV-ERR-006 위반)\n"
                    "    pass\n\n"
                    "# BAD - Exception pass\n"
                    "try:\n"
                    "    data = json.loads(raw)\n"
                    "except Exception:  # 에러 삼킴\n"
                    "    pass\n\n"
                    "# BAD - 광범위한 예외처리\n"
                    "try:\n"
                    "    process()\n"
                    "except Exception as e:\n"
                    "    print(e)  # 로그만 찍고 처리 안 함"
                ),
            },
            {
                "section": "§3",
                "text": (
                    "CONV-ERR-006 §3 — GOOD 패턴\n\n"
                    "import logging\n"
                    "logger = logging.getLogger(__name__)\n\n"
                    "# GOOD - 구체적 예외 타입 + 로깅\n"
                    "try:\n"
                    "    data = json.loads(raw)\n"
                    "except json.JSONDecodeError as e:\n"
                    "    logger.error('Invalid JSON: %s', e)\n"
                    "    raise ValueError(f'Failed to parse response: {e}') from e\n\n"
                    "# GOOD - 여러 예외 처리\n"
                    "try:\n"
                    "    result = await http_call()\n"
                    "except httpx.TimeoutException:\n"
                    "    logger.warning('Request timed out, retrying...')\n"
                    "    raise\n"
                    "except httpx.HTTPStatusError as e:\n"
                    "    logger.error('HTTP error %s', e.response.status_code)\n"
                    "    raise"
                ),
            },
        ],
    },

    # ── CONV-CFG-007 ───────────────────────────────────────────────────────────
    {
        "rule_id": "CONV-CFG-007", "severity": "Critical",
        "storage_path": "kms_docs/config.md", "category": "보안",
        "chunks": [
            {
                "section": "§0",
                "text": (
                    "[CONV-CFG-007] 하드코딩 설정값 금지 — severity: Critical\n\n"
                    "핵심 키워드: 하드코딩, API_KEY, PASSWORD, SECRET, TOKEN, "
                    "하드코딩된 비밀번호, 소스코드 자격증명, credentials in code\n\n"
                    "규칙: API 키, 패스워드, 시크릿, 토큰, DB 연결 문자열 등 "
                    "민감한 설정값을 소스코드에 직접 작성하는 것을 절대 금지한다. "
                    "모든 민감 정보는 환경변수 또는 시크릿 관리 서비스에서 로드해야 한다."
                ),
            },
            {
                "section": "§1",
                "text": (
                    "CONV-CFG-007 §1 — 왜 위험한가\n\n"
                    "Git 히스토리에 한 번 커밋되면 삭제해도 영구적으로 남음\n"
                    "GitHub 퍼블릭 레포라면 즉시 크롤러에 의해 수집\n"
                    "실제 사례: AWS 키 노출 → 24시간 내 마이닝 봇이 수백만원 청구\n\n"
                    "OWASP Top 10 A02:2021 - Cryptographic Failures 해당\n"
                    "GDPR, PCI-DSS 위반으로 법적 제재 가능"
                ),
            },
            {
                "section": "§2",
                "text": (
                    "CONV-CFG-007 §2 — BAD 패턴\n\n"
                    "# BAD - 소스코드에 하드코딩\n"
                    "API_KEY = 'sk-ant-api03-xxxxxxxxxxxxx'  # 절대 금지!\n"
                    "DB_PASSWORD = 'admin1234'  # 절대 금지!\n"
                    "GITHUB_TOKEN = 'ghp_xxxxxxxxxxxxxxxx'  # 절대 금지!\n\n"
                    "# BAD - 설정 딕셔너리에 직접 작성\n"
                    "config = {\n"
                    "    'database': {'password': 'secret123'},\n"
                    "    'redis': {'auth': 'redispass'},\n"
                    "}"
                ),
            },
            {
                "section": "§3",
                "text": (
                    "CONV-CFG-007 §3 — GOOD 패턴\n\n"
                    "import os\n"
                    "from dotenv import load_dotenv\n\n"
                    "load_dotenv()  # .env 파일 로드 (.gitignore에 포함)\n\n"
                    "# GOOD - 환경변수에서 로드\n"
                    "API_KEY = os.getenv('API_KEY')\n"
                    "DB_PASSWORD = os.getenv('DB_PASSWORD')\n\n"
                    "# GOOD - pydantic Settings 사용\n"
                    "from pydantic_settings import BaseSettings\n\n"
                    "class Settings(BaseSettings):\n"
                    "    api_key: str\n"
                    "    db_password: str\n\n"
                    "    class Config:\n"
                    "        env_file = '.env'"
                ),
            },
        ],
    },

    # ── CONV-SQL-008 ───────────────────────────────────────────────────────────
    {
        "rule_id": "CONV-SQL-008", "severity": "Critical",
        "storage_path": "kms_docs/sql_injection.md", "category": "보안",
        "chunks": [
            {
                "section": "§0",
                "text": (
                    "[CONV-SQL-008] f-string SQL 조합 금지 — severity: Critical\n\n"
                    "핵심 키워드: SQL 인젝션, f-string SQL, SQL injection, "
                    "파라미터 바인딩, 동적 SQL, format SQL, % SQL\n\n"
                    "규칙: SQL 쿼리를 f-string, str.format(), % 연산자로 동적 조합하는 것을 "
                    "절대 금지한다. 반드시 파라미터 바인딩(%s, :param)을 사용한다."
                ),
            },
            {
                "section": "§1",
                "text": (
                    "CONV-SQL-008 §1 — 왜 위험한가\n\n"
                    "SQL 인젝션은 OWASP Top 10 A03:2021 — Injection의 핵심이다.\n\n"
                    "공격 예시:\n"
                    "user_id = \"1 OR 1=1; DROP TABLE users; --\"\n"
                    "query = f\"SELECT * FROM users WHERE id = {user_id}\"\n"
                    "→ 전체 테이블 삭제 가능\n\n"
                    "user_id = \"1 UNION SELECT username, password FROM admin\"\n"
                    "→ 관리자 계정 탈취 가능\n\n"
                    "파라미터 바인딩은 입력값을 SQL 문법이 아닌 데이터로 처리하여 "
                    "인젝션을 근본적으로 차단한다."
                ),
            },
            {
                "section": "§2",
                "text": (
                    "CONV-SQL-008 §2 — BAD 패턴\n\n"
                    "# BAD - f-string SQL (CONV-SQL-008 위반)\n"
                    "def get_user(user_id: str):\n"
                    "    query = f'SELECT * FROM users WHERE id = {user_id}'\n"
                    "    return db.execute(query)\n\n"
                    "# BAD - % 포맷팅\n"
                    "def search(keyword: str):\n"
                    "    sql = 'SELECT * FROM products WHERE name LIKE \\'%%%s%%\\'' % keyword\n"
                    "    return db.execute(sql)\n\n"
                    "# BAD - str.format()\n"
                    "def delete_record(table: str, id: int):\n"
                    "    db.execute('DELETE FROM {} WHERE id = {}'.format(table, id))"
                ),
            },
            {
                "section": "§3",
                "text": (
                    "CONV-SQL-008 §3 — GOOD 패턴\n\n"
                    "# GOOD - psycopg2 파라미터 바인딩\n"
                    "def get_user(user_id: str):\n"
                    "    cur.execute('SELECT * FROM users WHERE id = %s', (user_id,))\n"
                    "    return cur.fetchone()\n\n"
                    "# GOOD - SQLAlchemy text() 파라미터\n"
                    "from sqlalchemy import text\n\n"
                    "def search(keyword: str):\n"
                    "    result = session.execute(\n"
                    "        text('SELECT * FROM products WHERE name LIKE :kw'),\n"
                    "        {'kw': f'%{keyword}%'}\n"
                    "    )\n"
                    "    return result.fetchall()\n\n"
                    "# GOOD - ORM 사용 (가장 안전)\n"
                    "def get_user_orm(user_id: str):\n"
                    "    return session.query(User).filter(User.id == user_id).first()"
                ),
            },
        ],
    },

    # ── CONV-PERF-009 ──────────────────────────────────────────────────────────
    {
        "rule_id": "CONV-PERF-009", "severity": "Major",
        "storage_path": "kms_docs/performance.md", "category": "코드성능검증",
        "chunks": [
            {
                "section": "§0",
                "text": (
                    "[CONV-PERF-009] 성능 안티패턴 — severity: Major\n\n"
                    "핵심 키워드: N+1 쿼리, 루프 내 DB 호출, 반복 API 호출, "
                    "배치 처리 미사용, 루프 안 쿼리, 성능 저하\n\n"
                    "규칙: 루프 내부에서 DB 쿼리나 외부 API 호출을 반복하는 N+1 패턴을 "
                    "금지한다. 배치 처리, JOIN, IN절, bulk 연산으로 대체해야 한다."
                ),
            },
            {
                "section": "§1",
                "text": (
                    "CONV-PERF-009 §1 — 왜 위험한가\n\n"
                    "N+1 쿼리 문제: 리스트 100개 조회 시 1(목록) + 100(각 상세) = 101번 DB 쿼리\n"
                    "vs JOIN 사용 시: 1번 쿼리로 동일한 결과\n\n"
                    "실 서비스 영향:\n"
                    "- DB 커넥션 과부하\n"
                    "- 응답시간: 10ms × 100 = 1,000ms (1초) 지연\n"
                    "- 동시 사용자 증가 시 기하급수적 악화"
                ),
            },
            {
                "section": "§2",
                "text": (
                    "CONV-PERF-009 §2 — BAD 패턴\n\n"
                    "# BAD - N+1 쿼리\n"
                    "def get_orders_with_users(order_ids: list) -> list:\n"
                    "    orders = db.query('SELECT * FROM orders WHERE id IN (%s)', order_ids)\n"
                    "    for order in orders:\n"
                    "        # 루프마다 DB 쿼리 → N+1!\n"
                    "        order['user'] = db.query(\n"
                    "            'SELECT * FROM users WHERE id = %s', order['user_id']\n"
                    "        )\n"
                    "    return orders\n\n"
                    "# BAD - 루프 내 API 호출\n"
                    "for product_id in product_ids:\n"
                    "    price = requests.get(f'/api/price/{product_id}').json()"
                ),
            },
            {
                "section": "§3",
                "text": (
                    "CONV-PERF-009 §3 — GOOD 패턴\n\n"
                    "# GOOD - JOIN으로 한 번에\n"
                    "def get_orders_with_users(order_ids: list) -> list:\n"
                    "    return db.query(\n"
                    "        'SELECT o.*, u.name, u.email '\n"
                    "        'FROM orders o JOIN users u ON o.user_id = u.id '\n"
                    "        'WHERE o.id = ANY(%s)',\n"
                    "        (order_ids,)\n"
                    "    )\n\n"
                    "# GOOD - 배치 API 호출\n"
                    "prices = requests.post('/api/prices/batch',\n"
                    "    json={'product_ids': product_ids}).json()"
                ),
            },
        ],
    },

    # ── CONV-SEC-010 ───────────────────────────────────────────────────────────
    {
        "rule_id": "CONV-SEC-010", "severity": "Major",
        "storage_path": "kms_docs/security.md", "category": "보안",
        "chunks": [
            {
                "section": "§0",
                "text": (
                    "[CONV-SEC-010] 보안 헤더 누락 — severity: Major\n\n"
                    "핵심 키워드: 클릭재킹, X-Frame-Options, CSP, 보안 헤더, "
                    "clickjacking, Content-Security-Policy, CORS 설정\n\n"
                    "규칙: 웹 응답에 보안 헤더(X-Frame-Options, Content-Security-Policy, "
                    "X-Content-Type-Options 등)를 반드시 포함해야 한다. "
                    "클릭재킹, XSS, MIME 스니핑 공격을 방어한다."
                ),
            },
            {
                "section": "§1",
                "text": (
                    "CONV-SEC-010 §1 — 왜 위험한가\n\n"
                    "클릭재킹(Clickjacking): 공격자가 iframe에 피해 사이트를 숨기고 "
                    "사용자 클릭을 가로채 결제/동의 버튼 대신 악성 버튼 클릭 유도\n\n"
                    "X-Frame-Options 미설정 → iframe 삽입 허용 → 클릭재킹 가능\n"
                    "CSP 미설정 → XSS 스크립트 삽입 허용\n"
                    "X-Content-Type-Options 미설정 → MIME 타입 혼동 공격 가능\n\n"
                    "OWASP Top 10 A05:2021 - Security Misconfiguration 해당"
                ),
            },
            {
                "section": "§2",
                "text": (
                    "CONV-SEC-010 §2 — BAD 패턴\n\n"
                    "# BAD - 보안 헤더 없는 FastAPI 응답\n"
                    "from fastapi import FastAPI\n"
                    "from fastapi.responses import JSONResponse\n\n"
                    "app = FastAPI()\n\n"
                    "@app.get('/api/data')\n"
                    "def get_data():\n"
                    "    return {'data': 'sensitive'}  # 보안 헤더 없음\n\n"
                    "# BAD - CORS 전체 허용\n"
                    "app.add_middleware(CORSMiddleware, allow_origins=['*'])"
                ),
            },
            {
                "section": "§3",
                "text": (
                    "CONV-SEC-010 §3 — GOOD 패턴\n\n"
                    "from fastapi import FastAPI\n"
                    "from fastapi.middleware.httpsredirect import HTTPSRedirectMiddleware\n"
                    "from starlette.middleware.base import BaseHTTPMiddleware\n\n"
                    "class SecurityHeadersMiddleware(BaseHTTPMiddleware):\n"
                    "    async def dispatch(self, request, call_next):\n"
                    "        response = await call_next(request)\n"
                    "        response.headers['X-Frame-Options'] = 'DENY'\n"
                    "        response.headers['X-Content-Type-Options'] = 'nosniff'\n"
                    "        response.headers['Content-Security-Policy'] = \"default-src 'self'\"\n"
                    "        return response\n\n"
                    "app.add_middleware(SecurityHeadersMiddleware)"
                ),
            },
        ],
    },

    # ── CONV-MEM-011 ───────────────────────────────────────────────────────────
    {
        "rule_id": "CONV-MEM-011", "severity": "Major",
        "storage_path": "kms_docs/memory_leak.md", "category": "코딩컨벤션",
        "chunks": [
            {
                "section": "§0",
                "text": (
                    "[CONV-MEM-011] 메모리 누수: Unbounded Collection Growth — severity: Major\n\n"
                    "핵심 키워드: Memory Leak, 메모리 누수, Unbounded Collection, "
                    "무한히 커지는 자료구조, 캐시 무한 증가, maxsize 없음, TTL 없음, "
                    "dict append list 무제한, CONV-MEM-011\n\n"
                    "규칙: dict/list/cache/queue에 maxsize, TTL, eviction policy 없이 "
                    "무한히 데이터를 추가하는 패턴을 금지한다."
                ),
            },
            {
                "section": "§1",
                "text": (
                    "CONV-MEM-011 §1 — 원인과 위험\n\n"
                    "Python GC는 참조가 남아있는 한 메모리를 회수하지 않는다.\n"
                    "전역 dict/list에 계속 추가하면 프로세스 메모리가 무한히 증가.\n\n"
                    "증상:\n"
                    "- 컨테이너 메모리 OOM → 강제 재시작\n"
                    "- 응답속도 점진적 저하 (GC 부담 증가)\n"
                    "- 서비스 장시간 운영 시 장애 발생 (메모리 누수 패턴)"
                ),
            },
            {
                "section": "§2",
                "text": (
                    "CONV-MEM-011 §2 — BAD 패턴\n\n"
                    "# BAD - maxsize 없는 캐시\n"
                    "cache = {}  # TTL/eviction 없음\n"
                    "def get_data(key):\n"
                    "    if key not in cache:\n"
                    "        cache[key] = fetch_from_db(key)  # 무한 증가\n"
                    "    return cache[key]\n\n"
                    "# BAD - 무한 히스토리\n"
                    "history = defaultdict(list)\n"
                    "def record(user_id, item):\n"
                    "    history[user_id].append(item)  # maxlen 없음\n\n"
                    "# BAD - 로그 버퍼 무제한\n"
                    "logs = []\n"
                    "def log_event(event):\n"
                    "    logs.append(event)  # flush 없음"
                ),
            },
            {
                "section": "§3",
                "text": (
                    "CONV-MEM-011 §3 — GOOD 패턴\n\n"
                    "from functools import lru_cache\n"
                    "from collections import deque\n"
                    "from cachetools import TTLCache\n\n"
                    "# GOOD - LRU cache with maxsize\n"
                    "@lru_cache(maxsize=1000)\n"
                    "def get_data(key): return fetch_from_db(key)\n\n"
                    "# GOOD - bounded deque\n"
                    "history = defaultdict(lambda: deque(maxlen=100))\n"
                    "def record(user_id, item):\n"
                    "    history[user_id].append(item)  # 100개 초과 시 자동 삭제\n\n"
                    "# GOOD - TTL 캐시\n"
                    "cache = TTLCache(maxsize=500, ttl=300)  # 5분 만료"
                ),
            },
        ],
    },
]


def _make_ids(rule_id: str, section: str) -> tuple[str, str, str]:
    doc_id = str(uuid.uuid5(_NS, rule_id))
    chunk_id = str(uuid.uuid5(_NS, f"{rule_id}_{section}"))
    emb_id = str(uuid.uuid5(_NS, f"{rule_id}_{section}_emb"))
    return doc_id, chunk_id, emb_id


def run(dry_run: bool = False) -> None:
    import psycopg2
    from pgvector.psycopg2 import register_vector

    url = os.getenv("POSTGRES_URL") or os.getenv("DATABASE_URL")
    if not url:
        host = os.getenv("DB_HOST", "localhost")
        port = os.getenv("DB_PORT", "5432")
        db   = os.getenv("DB_NAME", "codeshepherd")
        user = os.getenv("DB_USER", "postgres")
        pw   = os.getenv("DB_PASSWORD", "postgres")
        url  = f"postgresql://{user}:{pw}@{host}:{port}/{db}"

    print(f"DB: {url.split('@')[-1]}")

    total_chunks = sum(len(r["chunks"]) for r in RULES)
    print(f"규칙 {len(RULES)}개 / 청크 {total_chunks}개 인덱싱 시작\n")

    if dry_run:
        for rule in RULES:
            for c in rule["chunks"]:
                print(f"[DRY] {rule['rule_id']} {c['section']} — {len(c['text'])}자")
        return

    conn = psycopg2.connect(url, connect_timeout=10)
    register_vector(conn)
    cur = conn.cursor()

    texts = [c["text"] for r in RULES for c in r["chunks"]]
    print(f"임베딩 생성 중... ({len(texts)}개)")
    vectors = embed_texts(texts)
    print("임베딩 완료\n")

    idx = 0
    for rule in RULES:
        rule_id   = rule["rule_id"]
        severity  = rule["severity"]
        path      = rule["storage_path"]
        category  = rule["category"]
        doc_id    = str(uuid.uuid5(_NS, rule_id))

        # documents upsert
        cur.execute("""
            INSERT INTO documents (doc_id, title, source, category, upload_status, file_type)
            VALUES (%s, %s, 'upload', %s, 'stored', 'md')
            ON CONFLICT (doc_id) DO UPDATE
              SET title         = EXCLUDED.title,
                  category      = EXCLUDED.category,
                  upload_status = EXCLUDED.upload_status
        """, (doc_id, f"{rule_id} 가이드", category))

        for i, c in enumerate(rule["chunks"]):
            _, chunk_id, _ = _make_ids(rule_id, c["section"])
            meta = {
                "rule_id": rule_id,
                "severity": severity,
                "section_header": c["section"],
                "storage_path": path,
                "category": category,
            }

            # chunks upsert
            cur.execute("""
                INSERT INTO chunks
                    (chunk_id, doc_id, content, section_header, storage_path,
                     chunk_type, chunk_index)
                VALUES (%s, %s, %s, %s, %s, 'child', %s)
                ON CONFLICT (chunk_id) DO UPDATE
                  SET content        = EXCLUDED.content,
                      section_header = EXCLUDED.section_header,
                      storage_path   = EXCLUDED.storage_path
            """, (chunk_id, doc_id, c["text"], c["section"], path, i))

            # chunk_embeddings upsert
            cur.execute("""
                INSERT INTO chunk_embeddings
                    (chunk_id, embedding, model_name, content, metadata)
                VALUES (%s, %s, 'bge-m3', %s, %s)
                ON CONFLICT (chunk_id) DO UPDATE
                  SET embedding  = EXCLUDED.embedding,
                      model_name = EXCLUDED.model_name,
                      content    = EXCLUDED.content,
                      metadata   = EXCLUDED.metadata
            """, (chunk_id, vectors[idx], c["text"], psycopg2.extras.Json(meta)))

            print(f"  [OK] {rule_id} {c['section']}")
            idx += 1

        conn.commit()
        print(f"[DONE] {rule_id} ({len(rule['chunks'])}청크 커밋)\n")

    cur.close()
    conn.close()
    print(f"전체 완료: {len(RULES)}개 규칙 / {total_chunks}개 청크 인덱싱")


if __name__ == "__main__":
    import psycopg2.extras  # noqa: F401
    dry = "--dry-run" in sys.argv
    run(dry_run=dry)
