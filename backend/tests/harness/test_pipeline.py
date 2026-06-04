"""D1 테스트 — PipelineTask Protocol + asyncio.gather + Semaphore.

T05: MockPipelineTask가 PipelineTask 프로토콜을 만족한다 (isinstance)
T08: Semaphore(N)이 최대 N개 동시 실행을 강제한다
"""
import asyncio
import pytest

from app.usecases.interfaces.pipeline_task import PipelineTask
from app.usecases.run_pipeline import run_pipeline_batch, GEMINI_RPM_LIMIT


# ── 테스트용 구현체 ────────────────────────────────────────────────────────

class MockPipelineTask:
    """인메모리 실행 추적 — 실제 크롤/추출 없음."""

    def __init__(self, delay: float = 0.0, fail_doc_ids: set[str] | None = None):
        self.executed: list[tuple[str, str, str]] = []  # (session_id, doc_id, url)
        self._delay = delay
        self._fail = fail_doc_ids or set()

    async def execute(self, session_id: str, doc_id: str, url: str) -> None:
        if self._delay:
            await asyncio.sleep(self._delay)
        if doc_id in self._fail:
            raise ValueError(f"simulated failure: {doc_id}")
        self.executed.append((session_id, doc_id, url))


# ── T05: Protocol 준수 ────────────────────────────────────────────────────

def test_T05_mock_task_satisfies_protocol():
    """Arrange: MockPipelineTask 인스턴스.
    Act: isinstance(task, PipelineTask).
    Assert: True — 구조적 서브타이핑 통과.
    """
    task = MockPipelineTask()
    assert isinstance(task, PipelineTask), "MockPipelineTask는 PipelineTask Protocol을 충족해야 함"


def test_T05_protocol_requires_execute():
    """Arrange: execute 메서드가 없는 클래스.
    Act: isinstance 검사.
    Assert: False — Protocol 불충족.
    """
    class NoExecute:
        pass

    assert not isinstance(NoExecute(), PipelineTask)


# ── T08: Semaphore 동시성 제한 ────────────────────────────────────────────

@pytest.mark.anyio
async def test_T08_semaphore_limits_concurrency():
    """Arrange: Semaphore(2), 5개 URL.
    Act: run_pipeline_batch 실행 — 각 태스크 0.05초 sleep.
    Assert: 최대 동시 실행 수가 2를 초과하지 않는다.
    """
    limit = 2
    semaphore = asyncio.Semaphore(limit)
    active = 0
    peak = 0

    class CountingTask:
        async def execute(self, session_id: str, doc_id: str, url: str) -> None:
            nonlocal active, peak
            active += 1
            peak = max(peak, active)
            await asyncio.sleep(0.01)
            active -= 1

    pairs = [(f"https://example.com/{i}", f"EXT_url{i}_abc123{i:02d}") for i in range(5)]
    results = await run_pipeline_batch("sess-001", pairs, CountingTask(), semaphore)

    assert all(r is None for r in results), "모든 태스크가 성공해야 함"
    assert peak <= limit, f"동시 실행 피크 {peak}이 Semaphore 한도 {limit}을 초과"


@pytest.mark.anyio
async def test_T08_all_urls_executed():
    """Arrange: 5개 URL.
    Act: run_pipeline_batch.
    Assert: 모든 URL이 정확히 1회씩 실행된다.
    """
    task = MockPipelineTask()
    pairs = [(f"https://example.com/{i}", f"EXT_url{i}_ff{i:06d}") for i in range(5)]

    results = await run_pipeline_batch("sess-002", pairs, task)

    assert len(results) == 5
    assert all(r is None for r in results)
    assert len(task.executed) == 5
    executed_urls = {url for _, _, url in task.executed}
    assert executed_urls == {url for url, _ in pairs}


@pytest.mark.anyio
async def test_T08_partial_failure_returns_exceptions():
    """Arrange: doc_id 'fail-doc'은 예외 발생하도록 설정.
    Act: run_pipeline_batch(return_exceptions=True).
    Assert: 실패 항목만 Exception, 나머지는 None.
    """
    fail_id = "EXT_fail_00000001"
    task = MockPipelineTask(fail_doc_ids={fail_id})
    pairs = [
        ("https://example.com/ok",   "EXT_ok_00000001"),
        ("https://example.com/fail", fail_id),
        ("https://example.com/ok2",  "EXT_ok_00000002"),
    ]

    results = await run_pipeline_batch("sess-003", pairs, task)

    assert len(results) == 3
    ok_results   = [r for r in results if r is None]
    fail_results = [r for r in results if isinstance(r, Exception)]
    assert len(ok_results)   == 2
    assert len(fail_results) == 1


@pytest.mark.anyio
async def test_T08_default_semaphore_uses_gemini_rpm_limit():
    """Arrange: semaphore=None (기본값).
    Act: run_pipeline_batch — 내부에서 Semaphore(GEMINI_RPM_LIMIT) 생성.
    Assert: GEMINI_RPM_LIMIT개 URL이 모두 실행된다.
    """
    task = MockPipelineTask()
    pairs = [(f"https://example.com/{i}", f"EXT_url{i}_de{i:06d}") for i in range(GEMINI_RPM_LIMIT)]

    results = await run_pipeline_batch("sess-004", pairs, task)

    assert all(r is None for r in results)
    assert len(task.executed) == GEMINI_RPM_LIMIT
