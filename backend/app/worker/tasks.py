"""Celery 태스크 골격 — 파이프라인 5단계.

각 태스크는 독립 실행 가능하며 상태 전이를 pipeline_logs에 기록.
실제 LLM/크롤러 로직은 Phase 2에서 채워진다.
"""

import logging
import os

import psycopg2

from app.worker.celery_app import celery_app

logger = logging.getLogger(__name__)


def _pg_conn():
    return psycopg2.connect(
        host=os.getenv("DB_HOST", "localhost"),
        port=int(os.getenv("DB_PORT", "5433")),
        user=os.getenv("DB_USER", "postgres"),
        password=os.getenv("DB_PASSWORD", "postgres"),
        dbname=os.getenv("DB_NAME", "postgres"),
    )


def _log(conn, doc_id: str, session_id: str, agent: str, level: str, message: str):
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO pipeline_logs (doc_id, session_id, agent, level, message) "
            "VALUES (%s, %s, %s, %s, %s)",
            (doc_id, session_id, agent, level, message),
        )
    conn.commit()


def _set_state(conn, doc_id: str, state: str):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE documents SET state=%s, updated_at=now() WHERE doc_id=%s",
            (state, doc_id),
        )
    conn.commit()


# ── 1단계: Crawler ────────────────────────────────────────────────────────

@celery_app.task(name="pipeline.crawler", bind=True, max_retries=3)
def crawl_task(self, session_id: str, doc_id: str):
    """웹 크롤링 및 텍스트 정제 (Phase 2에서 실제 구현)."""
    conn = _pg_conn()
    try:
        _log(conn, doc_id, session_id, "Crawler", "INFO", "크롤링 시작")
        _set_state(conn, doc_id, "CRAWLING")

        # TODO(Phase2): HTTP 크롤러 실제 구현
        # raw_html = http_crawler.fetch(url)
        # cleaned_text = text_cleaner.clean(raw_html)

        _log(conn, doc_id, session_id, "Crawler", "INFO", "크롤링 완료 (stub)")
        # 다음 단계로 체이닝
        extract_task.delay(session_id=session_id, doc_id=doc_id, text="[stub text]")
    except Exception as exc:
        _log(conn, doc_id, session_id, "Crawler", "ERROR", str(exc))
        _set_state(conn, doc_id, "FAILED")
        raise self.retry(exc=exc, countdown=30)
    finally:
        conn.close()


# ── 2단계: Extractor ──────────────────────────────────────────────────────

@celery_app.task(name="pipeline.extractor", bind=True, max_retries=3)
def extract_task(self, session_id: str, doc_id: str, text: str):
    """LLM 기반 컨셉 추출 → staging_concepts DRAFT 적재 (Phase 2)."""
    conn = _pg_conn()
    try:
        _log(conn, doc_id, session_id, "Extractor", "INFO", "LLM 추출 시작")
        _set_state(conn, doc_id, "EXTRACTED")

        # TODO(Phase2): Gemini-2.5-flash 프롬프트 호출 및 JSON 파싱
        # concepts = extractor_agent.extract(text)
        # write_staging_draft(conn, session_id, doc_id, concepts)

        _log(conn, doc_id, session_id, "Extractor", "INFO", "추출 완료 (stub) — DRAFT 대기")
    except Exception as exc:
        _log(conn, doc_id, session_id, "Extractor", "ERROR", str(exc))
        _set_state(conn, doc_id, "FAILED")
        raise self.retry(exc=exc, countdown=60)
    finally:
        conn.close()


# ── 3단계: Graph Writer ───────────────────────────────────────────────────

@celery_app.task(name="pipeline.graph_writer", bind=True, max_retries=3)
def write_graph_task(self, session_id: str, doc_id: str):
    """APPROVED 항목 → Neo4j MERGE + APOC addLabels (Phase 2)."""
    conn = _pg_conn()
    try:
        _log(conn, doc_id, session_id, "Writer", "INFO", "그래프 적재 시작")

        # TODO(Phase2): graph_writer.commit_approved(session_id)

        _log(conn, doc_id, session_id, "Writer", "INFO", "그래프 적재 완료 (stub)")
        resolve_links_task.delay(session_id=session_id, doc_id=doc_id)
    except Exception as exc:
        _log(conn, doc_id, session_id, "Writer", "ERROR", str(exc))
        _set_state(conn, doc_id, "FAILED")
        raise self.retry(exc=exc, countdown=60)
    finally:
        conn.close()


# ── 4단계: Link Resolver ─────────────────────────────────────────────────

@celery_app.task(name="pipeline.link_resolver", bind=True, max_retries=3)
def resolve_links_task(self, session_id: str, doc_id: str):
    """SAME_AS / RELATED_TO 관계 탐색 및 노드 병합 (Phase 2)."""
    conn = _pg_conn()
    try:
        _log(conn, doc_id, session_id, "Resolver", "INFO", "링크 리졸버 시작")

        # TODO(Phase2): link_resolver.resolve(session_id)

        _set_state(conn, doc_id, "COMMITTED")
        _log(conn, doc_id, session_id, "Resolver", "INFO", "파이프라인 완료 — COMMITTED")
    except Exception as exc:
        _log(conn, doc_id, session_id, "Resolver", "ERROR", str(exc))
        raise self.retry(exc=exc, countdown=120)
    finally:
        conn.close()


# ── 통합 엔트리포인트 ─────────────────────────────────────────────────────

@celery_app.task(name="pipeline.run", bind=True)
def run_pipeline_task(self, session_id: str, doc_id: str):
    """파이프라인 전체 체인 시작점."""
    crawl_task.delay(session_id=session_id, doc_id=doc_id)
