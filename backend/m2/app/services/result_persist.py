"""m2 분석 결과 → m4 소유 `review_issue` 테이블 영속화.

m4가 제공한 INSERT(파라미터 바인딩, FK는 github_id 서브쿼리로 해결)를 사용한다.
review_issue·pull_requests·users는 **타 모듈(m4) 소유** 테이블이므로:

  - 기본 **비활성**(opt-in). `M2_PERSIST_ENABLED`가 truthy일 때만 실제로 INSERT 한다.
    (개발/테스트·CI에서 공유 클라우드 DB를 건드리지 않게 하는 안전장치.)
  - 실패해도 분석 자체를 중단시키지 않는다(graceful — 0 반환).

⚠️ severity 매핑·keyword 규칙은 m4 통계 키와 정렬되어야 한다(아래 매핑은 잠정값 —
   통합 시 m4와 문서로 확정 필요).
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, async_sessionmaker, create_async_engine

from app.contract import AgentResult
from shared.contracts import IssueItem

# m2 3단계(Critical/Major/Minor) → review_issue CHECK(critical/high/medium/low) 잠정 매핑.
# ⚠️ m4 합의 전 임시값. (low는 현재 미사용)
_SEVERITY_MAP = {
    "Critical": "critical",
    "Major": "high",
    "Minor": "medium",
}

# rule_id 접두사 → keyword(도메인). review_issue.keyword는 NOT NULL.
_KEYWORD_BY_PREFIX = {
    "SEC-": "security",
    "OWASP-": "security",
    "SA-": "static",
    "JS-": "static",
}

# 파일 확장자 → programming_language (nullable, 있으면 채움)
_LANG_BY_EXT = {
    ".py": "python",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
}

_INSERT_SQL = text(
    """
    INSERT INTO review_issue (
        id, pull_request_id, user_id, github_id, agent,
        severity, keyword, sub_category, code_context,
        code_snippet, suggestion, programming_language,
        framework, framework_version, name_of_function
    )
    VALUES (
        :id,
        (SELECT pr.id FROM pull_requests pr
         JOIN users u ON u.user_id = pr.user_id
         WHERE u.github_id = :github_id ORDER BY pr.submitted_at DESC LIMIT 1),
        (SELECT user_id FROM users WHERE github_id = :github_id),
        :github_id, :agent, :severity, :keyword, :sub_category, :code_context,
        :code_snippet, :suggestion, :programming_language,
        :framework, :framework_version, :name_of_function
    )
    """
)

_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker | None = None


def is_enabled() -> bool:
    """영속화가 켜져 있고 DB URL이 있는지."""
    flag = (os.getenv("M2_PERSIST_ENABLED") or "").strip().lower()
    return flag in ("1", "true", "yes", "on") and bool(_database_url())


def _database_url() -> str | None:
    url = os.getenv("DATABASE_URL")
    return url if url else None


def _get_factory() -> async_sessionmaker | None:
    """async 세션 팩토리(lazy). DB URL 없으면 None."""
    global _engine, _session_factory
    if _session_factory is not None:
        return _session_factory
    url = _database_url()
    if not url:
        return None
    _engine = create_async_engine(url, echo=False, pool_pre_ping=True)
    _session_factory = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_factory


def _keyword_for(issue: IssueItem, agent: str) -> str:
    rid = issue.rule_id or ""
    for prefix, kw in _KEYWORD_BY_PREFIX.items():
        if rid.startswith(prefix):
            return kw
    # fallback — agent 도메인
    return "security" if agent == "security_scan" else "static"


def _language_for(issue: IssueItem) -> str | None:
    if not issue.file:
        return None
    return _LANG_BY_EXT.get(Path(issue.file).suffix.lower())


def _issue_params(issue: IssueItem, agent: str, github_id: str) -> dict:
    """IssueItem → INSERT 바인드 파라미터(m2가 못 만드는 컬럼은 None)."""
    return {
        "id": str(uuid.uuid4()),
        "github_id": github_id,
        "agent": agent,
        "severity": _SEVERITY_MAP.get(issue.severity, "medium"),
        "keyword": _keyword_for(issue, agent),
        "sub_category": issue.rule_id,
        "code_context": None,
        "code_snippet": None,
        "suggestion": issue.suggestion,
        "programming_language": _language_for(issue),
        "framework": None,
        "framework_version": None,
        "name_of_function": None,
    }


async def persist_issues(
    result: AgentResult | None,
    github_id: str | None,
    factory: async_sessionmaker | None = None,
) -> int:
    """AgentResult의 이슈들을 review_issue에 INSERT. 삽입한 행 수 반환.

    비활성·github_id 없음·이슈 없음·DB 오류 시 0(graceful, 비중단).
    `factory`를 주입하면 그것을 사용한다(테스트용).
    """
    if result is None or not result.issues:
        return 0
    if not github_id:
        return 0
    if factory is None:
        if not is_enabled():
            return 0
        factory = _get_factory()
    if factory is None:
        return 0

    params = [_issue_params(i, result.agent, github_id) for i in result.issues]
    try:
        async with factory() as session:
            for p in params:
                await session.execute(_INSERT_SQL, p)
            await session.commit()
        return len(params)
    except Exception:  # noqa: BLE001 — DB 실패가 분석을 막지 않는다
        return 0
