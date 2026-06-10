"""dev2/repositories/scan_repository.py — 스캔 결과 영속화 Repository (CLAUDE.md §2)

Clean Architecture (의존성은 안쪽=추상을 향한다):

    [Use Cases]  nodes/store.py, nodes/aggregate.py
          │ depends on
          ▼
    [Interface]  ScanRepository (ABC)        ← 노드는 여기에만 의존
          ▲ implements
          │
    [Adapter]    SqlAlchemyScanRepository  →  dev2.db (SQLAlchemy + asyncpg)

CLAUDE.md §2:
    "DB 접근은 Repository 패턴으로 래핑한다. 에이전트 코드에 SQL/ORM이 직접
     노출되지 않는다." → 노드는 ScanRepository 인터페이스만 import하고,
    SQL은 구현체와 dev2.db 안에만 존재한다.

테스트 (CLAUDE.md §13):
    get_scan_repository()를 패치해 가짜 Repository를 주입하면 실제 DB 없이
    노드 로직을 검증할 수 있다.
        with patch("dev2.nodes.aggregate.get_scan_repository", return_value=fake):
            ...
"""
from __future__ import annotations

from abc import ABC, abstractmethod


class ScanRepository(ABC):
    """스캔 실행/이슈/요약 영속화 + 조회 인터페이스 (CLAUDE.md §2 Repository 패턴).

    노드(Use Case) 코드는 이 추상에만 의존한다. 구현체 교체(다른 DB, Mock)가
    노드 코드 변경 없이 가능하도록 의존성을 역전한다.
    """

    @abstractmethod
    async def insert_execution(
        self,
        task_id: str,
        pr_id: str,
        execution_ms: int,
        developer_id: str | None = None,
        trace_id: str | None = None,
    ) -> int:
        """scan_executions에 실행 기록을 INSERT하고 생성된 scan_id를 반환한다."""

    @abstractmethod
    async def insert_issues(self, scan_id: int, issues: list[dict], agent: str) -> None:
        """scan_issues에 이슈별 행을 INSERT한다."""

    @abstractmethod
    async def insert_summary(self, scan_id: int, agent: str, summary: dict) -> None:
        """scan_summaries에 집계 요약을 UPSERT한다 (재스캔 시 덮어쓰기)."""

    @abstractmethod
    async def insert_aggregated_result(
        self,
        task_id: str,
        pr_id: str,
        developer_id: str,
        issues: list[dict],
        summary: dict,
    ) -> None:
        """취합 결과를 execution + issues + summary에 한 번에 적재한다."""

    @abstractmethod
    async def fetch_results_by_task(self, task_id: str) -> list[dict]:
        """task_id로 적재된 결과를 AgentOutput 리스트로 복원한다 (DB 릴레이)."""


class SqlAlchemyScanRepository(ScanRepository):
    """ScanRepository의 SQLAlchemy/asyncpg 구현체.

    SQL은 dev2.db 모듈에 존재하며 이 클래스는 그 함수에 위임한다(현 단계는
    인터페이스 seam 도입이 목적이므로 SQL은 한곳에 유지). dev2.db는 asyncpg를
    요구하므로, 미설치 환경(테스트)에서 import 에러가 나지 않도록 각 메서드
    안에서 lazy import 한다 (CLAUDE.md §10-3).
    """

    async def insert_execution(
        self,
        task_id: str,
        pr_id: str,
        execution_ms: int,
        developer_id: str | None = None,
        trace_id: str | None = None,
    ) -> int:
        from dev2.db import insert_scan_execution  # noqa: PLC0415

        return await insert_scan_execution(
            task_id=task_id,
            pr_id=pr_id,
            execution_ms=execution_ms,
            developer_id=developer_id,
            trace_id=trace_id,
        )

    async def insert_issues(self, scan_id: int, issues: list[dict], agent: str) -> None:
        from dev2.db import insert_scan_issues  # noqa: PLC0415

        await insert_scan_issues(scan_id, issues, agent)

    async def insert_summary(self, scan_id: int, agent: str, summary: dict) -> None:
        from dev2.db import insert_scan_summary  # noqa: PLC0415

        await insert_scan_summary(scan_id, agent, summary)

    async def insert_aggregated_result(
        self,
        task_id: str,
        pr_id: str,
        developer_id: str,
        issues: list[dict],
        summary: dict,
    ) -> None:
        from dev2.db import insert_aggregated_result  # noqa: PLC0415

        await insert_aggregated_result(
            task_id=task_id,
            pr_id=pr_id,
            developer_id=developer_id,
            issues=issues,
            summary=summary,
        )

    async def fetch_results_by_task(self, task_id: str) -> list[dict]:
        from dev2.db import fetch_scan_results_by_task  # noqa: PLC0415

        return await fetch_scan_results_by_task(task_id)


# 기본 구현체 싱글턴 — 프로세스당 1개면 충분 (상태 없음, asyncpg는 lazy)
_default_repository: ScanRepository = SqlAlchemyScanRepository()


def get_scan_repository() -> ScanRepository:
    """기본 ScanRepository 구현체를 반환한다.

    노드는 이 팩토리로 Repository를 얻어 인터페이스(ScanRepository)에만 의존한다.
    테스트는 이 함수를 패치해 가짜 Repository를 주입한다.
    """
    return _default_repository
