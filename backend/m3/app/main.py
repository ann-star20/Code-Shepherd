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

from shared.contracts import (
    IssueItem,
    IssueSummary,
    M3ReviewRequest,
    M3ReviewResponse,
    M3VerifyRequest,
    M3VerifyResponse,
)
from shared.logging import TraceIDMiddleware, configure_logging

log = structlog.get_logger()

# 형제 에이전트 경로 (이 파일: backend/m3/app/main.py)
_M3_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TP = os.path.join(_M3_ROOT, "test-performance-agent")
_PRC = os.path.join(_M3_ROOT, "pr-comment-agent")
# 동명 모듈(contracts/main/config) 충돌 방지 — webhook-gateway/agents/dev3_adapter.py 와 동일 패턴
_DEV3_MODS = ("contracts", "main", "config", "config.settings")
# pr-comment-agent 도 contracts/config 를 가짐 → 같은 격리로 import 한다.
_PRC_MODS = ("contracts", "config", "config.settings", "main",
             "aggregator", "llm_refiner", "github_poster")

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
    # _TP 를 sys.path 맨 앞으로 강제 — pr-comment-agent(_PRC)도 동명 contracts 를 가지므로
    # 순서에 따라 'from contracts import Dev3Input'가 엉뚱한 패키지로 풀리는 걸 막는다.
    while _TP in sys.path:
        sys.path.remove(_TP)
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


# ════════════════════════════════════════════════════════════════════
# /review — 4개 결과 집계 → 판정 → 코멘트 → 게시 → 저장.
# 분석/코멘트 로직은 형제 에이전트(pr-comment-agent·test-performance-agent) 소유.
# 여기는 "조립 + 엔드포인트"만. 외부 의존(LLM·GitHub·DB)은 seam 으로 분리해
# 테스트에서 monkeypatch 하고, 키/토큰 없으면 정직하게 fallback/skip 한다.
# ════════════════════════════════════════════════════════════════════

import contextlib  # noqa: E402


def _load_env_file(path: str) -> None:
    """형제 .env(GITHUB_TOKEN·GOOGLE_API_KEY)를 setdefault 로 로드. 값은 코드/깃에 없음."""
    if not os.path.exists(path):
        return
    try:
        for line in open(path, encoding="utf-8"):
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip())
    except OSError:
        pass


@contextlib.contextmanager
def _prc_isolation():
    """pr-comment-agent 모듈을 동명 충돌 없이 import 하기 위한 sys.path/sys.modules 격리.

    _PRC 를 sys.path 맨 앞으로 강제한다 — test-performance-agent(_TP)도 동명 contracts/config 를
    가지므로, persist/get 등이 _TP 를 앞에 꽂아둔 상태면 'from contracts import CombinedIssue'가
    엉뚱한 패키지로 풀려 ImportError 가 난다. 호출 순서와 무관하게 _PRC 가 우선되게 한다.
    """
    for m in _PRC_MODS:
        sys.modules.pop(m, None)
    while _PRC in sys.path:
        sys.path.remove(_PRC)
    sys.path.insert(0, _PRC)
    _load_env_file(os.path.join(_PRC, ".env"))
    try:
        yield
    finally:
        for m in _PRC_MODS:
            sys.modules.pop(m, None)


def _collect_outputs(payload: M3ReviewRequest) -> list[dict]:
    """4개 모듈 결과(M2/M3 Response)를 {agent, issues[]} 평면 dict 목록으로 변환."""
    outputs: list[dict] = []
    for result in (
        payload.static_analysis,
        payload.security_scan,
        payload.test_verification,
        payload.performance,
    ):
        if result is None:
            continue
        outputs.append(
            {
                "agent": result.agent,
                "issues": [
                    {
                        "severity": i.severity,
                        "file": i.file or "",
                        "line": i.line,
                        "message": i.message,
                        "rule_id": i.rule_id or "",
                        "suggestion": i.suggestion or "",
                    }
                    for i in result.issues
                ],
            }
        )
    return outputs


def _review_aggregate(outputs: list[dict]) -> tuple[str, list[dict]]:
    """pr-comment-agent aggregator 재사용 → (verdict, combined_issues[dict])."""
    with _prc_isolation():
        from aggregator import aggregate
        from contracts import AgentOutput, Issue

        agent_outputs = [
            AgentOutput(
                task_id="review",
                scan_id=0,
                pr_id="",
                agent=o["agent"],
                issues=[Issue(**i) for i in o["issues"]],
            )
            for o in outputs
        ]
        combined, verdict, _summary = aggregate(agent_outputs)
        combined_dicts = [
            {
                "severity": c.severity,
                "file": c.file,
                "line": c.line,
                "message": c.message,
                "rule_id": c.rule_id,
                "suggestion": c.suggestion,
                "source_agent": c.source_agent,
                "rag_context": c.rag_context,
            }
            for c in combined
        ]
        return verdict, combined_dicts


def _review_refine(combined: list[dict], verdict: str, skill_level: str) -> str:
    """pr-comment-agent llm_refiner 재사용 → 코멘트 본문. LLM 키 없으면 휴리스틱 fallback."""
    with _prc_isolation():
        from contracts import CombinedIssue
        from llm_refiner import _heuristic_refine, refine

        issues = [CombinedIssue(**c) for c in combined]
        try:
            return refine(issues, verdict, skill_level)
        except Exception as exc:  # noqa: BLE001 — LLM 호출 실패는 휴리스틱으로 정직하게 fallback
            log.warning("m3.review.refine_fallback", error=f"{type(exc).__name__}: {exc}")
            return _heuristic_refine(issues, verdict)


def _gh_post(owner: str, repo: str, pr_number: int, body: str) -> dict:
    """pr-comment-agent github_poster 재사용 — 실제 게시 시도(또는 토큰 없으면 dry_run)."""
    with _prc_isolation():
        from github_poster import post_comment

        return post_comment("", body, owner=owner, repo=repo, pr_num=pr_number)


def _review_post_comment(owner: str, repo: str, pr_number: int, body: str) -> dict:
    """코멘트를 GitHub 에 게시. 토큰 없음/실패 시 정직하게 skip(가짜 게시 금지).

    Returns: {"posted": bool, "url": str|None, "reason": str}
    - mode=='github' 일 때만 실제 게시 → posted True + issuecomment URL.
    - dry_run/skipped/예외 → posted False + 사유(예외 안 터뜨림).
    """
    if not body.strip():
        return {"posted": False, "url": None, "reason": "empty comment"}
    try:
        res = _gh_post(owner, repo, pr_number, body)
    except Exception as exc:  # noqa: BLE001 — 인증 실패 등 어떤 게시 오류든 정직하게 skip
        log.warning("m3.review.post_failed", error=f"{type(exc).__name__}: {exc}")
        return {"posted": False, "url": None, "reason": str(exc)}

    if res.get("mode") == "github":
        cid = res.get("comment_id")
        url = f"https://github.com/{owner}/{repo}/pull/{pr_number}#issuecomment-{cid}"
        return {"posted": True, "url": url, "reason": "github"}

    reason = res.get("reason") or res.get("mode") or "skipped"
    log.info("m3.review.post_skipped", reason=reason)
    return {"posted": False, "url": None, "reason": reason}


def _review_persist(owner, repo, pr_number, verdict, comment, issues) -> bool:
    """test-performance-agent persist 재사용 → review_results 저장. 실패해도 예외 안 터뜨림."""
    if _TP not in sys.path:
        sys.path.insert(0, _TP)
    try:
        import persist as dev3_persist

        dev3_persist.save_review(owner, repo, pr_number, verdict, comment, issues)
        return True
    except Exception as exc:  # noqa: BLE001 — DB 미가용 등 어떤 실패든 저장만 정직하게 skip
        log.warning("m3.review.persist_failed", error=f"{type(exc).__name__}: {exc}")
        return False
    finally:
        sys.modules.pop("persist", None)


def _get_stored_review(owner: str, repo: str, pr_number: int):
    """저장된 리뷰 결과 dict 반환(없으면 None). 조회 실패해도 예외 안 터뜨림."""
    if _TP not in sys.path:
        sys.path.insert(0, _TP)
    try:
        import persist as dev3_persist

        return dev3_persist.get_review(owner, repo, pr_number)
    except Exception as exc:  # noqa: BLE001
        log.warning("m3.review.get_failed", error=f"{type(exc).__name__}: {exc}")
        return None
    finally:
        sys.modules.pop("persist", None)


@app.post("/review", response_model=M3ReviewResponse)
async def review(payload: M3ReviewRequest) -> M3ReviewResponse:
    """4개 결과 → 판정 → 코멘트 → GitHub 게시 → DB 저장 → M3ReviewResponse."""
    owner, _, repo = payload.repository.partition("/")

    outputs = _collect_outputs(payload)
    verdict, combined = _review_aggregate(outputs)

    skill = payload.developer.skill_level if payload.developer else "junior"
    comment_body = _review_refine(combined, verdict, skill)

    post = _review_post_comment(owner, repo, payload.pr_number, comment_body)
    persisted = _review_persist(
        owner, repo, payload.pr_number, verdict, comment_body, combined
    )

    log.info(
        "m3.review.done",
        task_id=payload.task_id,
        repository=payload.repository,
        pr_number=payload.pr_number,
        verdict=verdict,
        comment_posted=post["posted"],
        persisted=persisted,
    )
    return M3ReviewResponse(
        task_id=payload.task_id,
        pr_id=payload.pr_id,
        verdict=verdict,
        comment_posted=post["posted"],
        comment_url=post["url"],
        persisted=persisted,
    )


@app.get("/review/{owner}/{repo}/{pr_number}")
async def get_review(owner: str, repo: str, pr_number: int):
    """저장된 {verdict, comment, issues} 반환. 없으면 found=False 빈 결과(200)."""
    stored = _get_stored_review(owner, repo, pr_number)
    base = {"owner": owner, "repo": repo, "pr_number": pr_number}
    if not stored:
        return {**base, "found": False, "verdict": None, "comment": "", "issues": []}
    return {**base, "found": True, **stored}
