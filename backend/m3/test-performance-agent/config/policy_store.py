"""정책(평가 기준 숫자) 저장소 — GCP convention_policies에서 읽고, 실패 시 fallback.

Policy as Data: 커버리지 임계값·면제 규칙 같은 "기준"을 코드가 아니라 DB(jsonb)에 둔다.
규정 담당자가 사내 문서만 고치면(→ rag.load_conventions 적재) 기준이 반영된다.

원칙:
- 위험3: 숫자는 jsonb 구조화 데이터로 **코드가 정확히** 읽는다(LLM 자연어 파싱 아님).
- 안전장치: DB 못 읽으면(POSTGRES_URL 없음/표 없음/예외) 빈 dict 반환
  → 호출자(config/conventions.py 등)가 하드코딩 기본값으로 fallback.
- 캐시: 실행당 1번만 조회(탐지기가 파일마다 DB를 두드리지 않게).
- 측정·판정 로직은 호출자(coverage.py 등) 그대로. 여기는 "기준값 공급"만.
"""
from __future__ import annotations

import json

import persist

CONVENTION_POLICIES_DDL = """
CREATE TABLE IF NOT EXISTS convention_policies (
    policy_key text PRIMARY KEY,
    rule_id    text,
    params     jsonb NOT NULL,
    updated_at timestamptz DEFAULT now()
);
"""

# 실행당 캐시 — {policy_key: params(dict)}. None=아직 안 읽음.
_CACHE: dict | None = None


def ensure_table(conn) -> None:
    """convention_policies가 없으면 생성(IF NOT EXISTS, 안전)."""
    with conn.cursor() as cur:
        cur.execute(CONVENTION_POLICIES_DDL)


def _connect():
    """GCP Postgres 연결(POSTGRES_URL). 없으면 None. 테스트에서 monkeypatch 대상."""
    url = persist._pg_url()
    if not url:
        return None
    import psycopg2  # noqa: PLC0415

    return psycopg2.connect(url, connect_timeout=10)


def load_policies(force: bool = False) -> dict:
    """convention_policies 전체를 {policy_key: params} 로 읽어 캐시.

    DB 미설정/표 없음/예외 → 빈 dict(안전). 호출자가 fallback 하도록.
    """
    global _CACHE
    if _CACHE is not None and not force:
        return _CACHE

    policies: dict = {}
    conn = None
    try:
        conn = _connect()
        if conn is not None:
            with conn.cursor() as cur:
                cur.execute("SELECT policy_key, params FROM convention_policies")
                for key, params in cur.fetchall():
                    if isinstance(params, dict):  # jsonb → dict (psycopg2)
                        policies[key] = params
    except Exception:
        policies = {}  # 표 없음/연결 실패 → fallback 유도(가짜 기준 안 씀)
    finally:
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    _CACHE = policies
    return policies


def get_params(policy_key: str) -> dict | None:
    """정책 1개의 params(dict). DB에 없으면 None → 호출자 fallback."""
    return load_policies().get(policy_key)


def reset_cache() -> None:
    """캐시 비움(테스트·재적재 후 갱신용)."""
    global _CACHE
    _CACHE = None


def upsert_policy(conn, policy_key: str, rule_id: str, params: dict) -> None:
    """정책 1개 UPSERT(있으면 갱신). params는 jsonb로 저장."""
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO convention_policies (policy_key, rule_id, params, updated_at)
               VALUES (%s, %s, %s::jsonb, now())
               ON CONFLICT (policy_key) DO UPDATE SET
                 rule_id = excluded.rule_id,
                 params  = excluded.params,
                 updated_at = now()""",
            (policy_key, rule_id, json.dumps(params)),
        )
