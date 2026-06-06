"""M3 테스트 검증·성능 분석 — 실제 분석 어댑터.

엔드포인트는 test-performance-agent 의 run() 을 호출해 결과를 IssueItem 계약으로 변환한다.
분석 로직(run·탐지기)은 test-performance-agent 소유 — 여기는 "변환 어댑터"만 추가한다.
"""

import os
import sys
import time
import urllib.request
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI

from shared.contracts import IssueItem, IssueSummary, M3VerifyRequest, M3VerifyResponse
from shared.logging import TraceIDMiddleware, configure_logging

log = structlog.get_logger()

# test-performance-agent 경로 (이 파일: backend/m3/app/main.py → backend/m3/test-performance-agent)
_TP = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "test-performance-agent"
)
# 동명 모듈(contracts/main/config) 충돌 방지 — webhook-gateway/agents/dev3_adapter.py 와 동일 패턴
_DEV3_MODS = ("contracts", "main", "config", "config.settings")

# pr_diff(=diff 본문) fetch 방어 — m1은 보통 본문을 보내지만 URL(.diff)이 올 수도 있다.
_DIFF_FETCH_TIMEOUT_S = 15


def _resolve_pr_diff(pr_diff: str) -> str:
    """pr_diff 는 기본적으로 diff 본문이다.

    단, 값이 'http'로 시작하면(예: https://github.com/owner/repo/pull/4.diff)
    1회 fetch 해 본문으로 치환한다. 분석기(parse_diff)는 URL이 아니라 본문을 기대한다.
    fetch 실패 시 정직하게 빈 문자열을 반환한다(가짜 diff 를 만들지 않는다).
    """
    s = (pr_diff or "").strip()
    if not s.lower().startswith("http"):
        return pr_diff  # 이미 본문 — 그대로 사용
    try:
        req = urllib.request.Request(
            s,
            headers={"User-Agent": "code-shepherd-m3", "Accept": "application/vnd.github.v3.diff"},
        )
        with urllib.request.urlopen(req, timeout=_DIFF_FETCH_TIMEOUT_S) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except Exception as exc:  # noqa: BLE001 — 네트워크/HTTP 어떤 실패든 정직하게 빈 결과로
        log.warning("m3.diff.fetch_failed", url=s, error=str(exc))
        return ""


@asynccontextmanager
async def lifespan(_app: FastAPI):
    configure_logging()
    yield


app = FastAPI(title="code-shepherd m3-verify", version="0.1.0", lifespan=lifespan)
app.add_middleware(TraceIDMiddleware)


def _analyze_pr(payload: M3VerifyRequest):
    """clone → dev3.run 실행 후 AgentOutput 리스트 반환.

    repo(clone_url) 정보가 없으면 분석 불가 → None (가짜를 만들지 않는다).
    동명 모듈 충돌은 sys.path/sys.modules 격리 + 함수 안 지연 import 로 회피한다.
    """
    if not payload.clone_url:
        log.info(
            "m3.analyze.skip",
            reason="clone_url 없음 — 분석 불가, 빈 issues 반환",
            task_id=payload.task_id,
        )
        return None

    for m in _DEV3_MODS:
        sys.modules.pop(m, None)
    if _TP not in sys.path:
        sys.path.insert(0, _TP)
    work_dir = None
    try:
        from contracts import Dev3Input, Developer, RepoInfo

        repo = RepoInfo(clone_url=payload.clone_url, commit_sha=payload.commit_sha or "")
        dev_id = payload.developer.id if payload.developer else "junior"
        inp = Dev3Input(
            task_id=payload.task_id,
            scan_id=0,
            pr_id=payload.pr_id,
            pr_diff=_resolve_pr_diff(payload.pr_diff),
            repo=repo,
            developer=Developer(id=dev_id),
        )
        work_dir = _dev3_prepare_repo(repo)
        _dev3_measure_coverage(work_dir)  # coverage.json 생성(없으면 TEST-001/004 skip)
        return _dev3_run(inp, work_dir)
    finally:
        for m in _DEV3_MODS:
            sys.modules.pop(m, None)
        if work_dir:
            import shutil

            shutil.rmtree(work_dir, ignore_errors=True)


def _dev3_prepare_repo(repo):
    """clone seam — test-performance-agent/prepare/repo.py 의 prepare_repo 호출.

    별도 함수로 분리해 테스트에서 monkeypatch(실 clone 없이 RepoInfo 캡처)할 수 있게 한다.
    호출 시점에 _TP 가 sys.path 에 있어야 한다(_analyze_pr 가 보장).
    """
    from prepare.repo import prepare_repo

    return prepare_repo(repo)


def _dev3_run(dev3_input, work_dir):
    """run seam — test-performance-agent/main.py 의 run 호출.

    별도 함수로 분리해 테스트에서 monkeypatch(Dev3Input 캡처 + 가짜 AgentOutput 주입)할 수 있게 한다.
    """
    import main as dev3_main

    return dev3_main.run(dev3_input, work_dir)


def _dev3_measure_coverage(work_dir: str) -> None:
    """coverage seam — Docker 샌드박스로 pytest --cov 실측 → work_dir/coverage.json 기록.

    test_verification(coverage TEST-001 · missing_funcs TEST-004)은 coverage.json 이 있어야
    동작한다. run() 은 그 파일을 '읽기만' 하므로, clone 직후 여기서 만들어 둔다.
    webhook-gateway/agents/dev3_adapter.py 와 동일한 방식: 컨테이너(root)가 만든 파일은
    호스트가 못 읽을 수 있어, run_sandbox 가 stdout 마커로 회수한 coverage dict 를
    호스트가 직접 기록한다. Docker 미가용 등 '어떤' 실패든 try/except 로 삼켜
    커버리지만 정직하게 skip 한다(가짜 coverage 를 만들지 않는다).
    """
    try:
        import json as _json
        from prepare.sandbox import run_sandbox

        res = run_sandbox(work_dir)
        cov = res.get("coverage")
        if not cov:
            log.info("m3.coverage.skip", reason="coverage 회수 실패 — TEST-001/004 누락 가능")
            return
        cov_path = os.path.join(work_dir, "coverage.json")
        try:
            if os.path.exists(cov_path):
                os.remove(cov_path)  # 컨테이너 잔여물 제거(권한 충돌 회피)
        except OSError:
            pass
        with open(cov_path, "w", encoding="utf-8") as f:
            _json.dump(cov, f)
        log.info(
            "m3.coverage.measured",
            percent=cov.get("totals", {}).get("percent_covered", 0),
        )
    except Exception as exc:  # noqa: BLE001 — Docker 미가용 등 어떤 실패든 커버리지만 skip
        log.warning("m3.coverage.skip", error=f"{type(exc).__name__}: {exc}")


_SEV_KEY = {"Critical": "critical", "Major": "major", "Minor": "minor"}


def _build_response(payload: M3VerifyRequest, agent: str) -> M3VerifyResponse:
    """선택 agent 의 이슈만 골라 IssueItem 으로 변환 + severity 카운트 summary."""
    t0 = time.time()
    outputs = _analyze_pr(payload)

    issues: list[IssueItem] = []
    if outputs:
        for o in outputs:
            if o.agent != agent:
                continue
            for i in o.issues:
                # IssueItem 계약 필드만 매핑 — keyword/code_context/rag_context 등은 버린다.
                issues.append(
                    IssueItem(
                        severity=i.severity,
                        line=i.line,
                        file=i.file,
                        message=i.message,
                        rule_id=i.rule_id,
                        suggestion=i.suggestion,
                    )
                )

    counts = {"critical": 0, "major": 0, "minor": 0}
    for it in issues:
        counts[_SEV_KEY[it.severity]] += 1

    return M3VerifyResponse(
        task_id=payload.task_id,
        agent=agent,
        issues=issues,
        summary=IssueSummary(**counts),
        execution_ms=int((time.time() - t0) * 1000),
    )


@app.get("/health")
async def health():
    return {"status": "ok", "service": "m3-verify"}


@app.post("/verify/tests", response_model=M3VerifyResponse)
async def verify_tests(payload: M3VerifyRequest) -> M3VerifyResponse:
    """run() 결과 중 agent=='test_verification' 이슈를 반환."""
    return _build_response(payload, "test_verification")


@app.post("/analyze/performance", response_model=M3VerifyResponse)
async def analyze_performance(payload: M3VerifyRequest) -> M3VerifyResponse:
    """run() 결과 중 agent=='performance' 이슈를 반환."""
    return _build_response(payload, "performance")
