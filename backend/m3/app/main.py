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
# test-performance-agent 의 rag(검색·포맷)를 동명 충돌 없이 import 하기 위한 격리 대상.
# _PRC(pr-comment-agent)와 '동명'인 모듈만 비운다 — 이것들만 _TP/_PRC 어디로 풀리느냐가 갈린다.
# rag.*·persist 는 _TP 에만 있어 충돌하지 않으므로 비우지 않는다(특히 rag.embedder 는 BGE-M3
# 모델을 모듈 캐시로 들고 있어, 비우면 이슈마다 수 GB 모델을 재로딩하게 된다).
_TP_MODS = ("contracts", "config", "config.settings", "main")

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
    metrics: dict | None = None
    if outputs:
        for o in outputs:
            if o.agent != agent:
                continue
            # 측정 지표(커버리지 등)는 IssueItem 엔 안 들어가므로 응답 레벨로 실어 보낸다(7D).
            if getattr(o, "metrics", None):
                metrics = o.metrics
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
        metrics=metrics,
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


@contextlib.contextmanager
def _tp_isolation():
    """test-performance-agent 의 rag 모듈(retriever·augment)을 동명 충돌 없이 import.

    _prc_isolation 의 거울상 — _TP 를 sys.path 맨 앞으로 강제하고 동명 모듈을 비워
    'from config import settings'·'import persist'·'from rag ...' 가 _PRC 가 아니라
    _TP 로 풀리게 한다. _review_aggregate(_prc_isolation)가 _PRC 를 앞에 꽂아둔 뒤라도 안전.
    POSTGRES_URL 등은 형제 .env 에서 로드(키/URL 은 코드·깃에 없음).
    """
    for m in _TP_MODS:
        sys.modules.pop(m, None)
    while _TP in sys.path:
        sys.path.remove(_TP)
    sys.path.insert(0, _TP)
    _load_env_file(os.path.join(_TP, ".env"))
    try:
        yield
    finally:
        for m in _TP_MODS:
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


def _rag_search(message: str) -> list[dict]:
    """검색 seam — test-performance-agent rag.retriever.search_convention 재사용(_TP 격리).

    7A 검색기를 그대로 호출한다(retriever 로직 중복 구현 금지). 테스트에서 monkeypatch 대상.
    검색기 자체도 DB 미설정/예외 시 [] 를 주지만, import 실패 등 어떤 오류든 여기서 정직하게
    [] 로 막는다(가짜 인용 금지). 반환: [{content, doc_title, source_url, score}, ...].
    """
    try:
        with _tp_isolation():
            from rag.retriever import search_convention

            return search_convention(message)
    except Exception as exc:  # noqa: BLE001 — import/검색 실패 → 빈 결과(가짜 인용 금지)
        log.warning("m3.review.rag_search_failed", error=f"{type(exc).__name__}: {exc}")
        return []


def _format_rag_docs(docs: list[dict]) -> str:
    """포맷 seam — test-performance-agent rag.augment.format_context 재사용(중복 구현 금지)."""
    if not docs:
        return ""
    with _tp_isolation():
        from rag.augment import format_context

        return format_context(docs)


def _review_augment_rag(combined: list[dict]) -> None:
    """코멘트 생성 직전, 각 combined 이슈의 message 로 사내규칙을 검색해 rag_context 를 채운다(제자리).

    - RAG_ENABLED 꺼짐 → 스킵. docker-compose 기본 ON; 테스트는 conftest _rag_off 로 격리.
    - 검색/포맷은 7A retriever·augment 재사용. DB 미설정·검색 예외 → 빈 인용으로 남김(가짜 금지).
    - combined 는 refine(코멘트)·persist(리뷰 페이지) 공용 → 둘 다에 📖 가 반영된다.
    - 어떤 실패든 /review 흐름을 막지 않는다(이슈 1건 실패가 전체 코멘트를 막지 않게).
    """
    if not os.getenv("RAG_ENABLED"):
        return
    for c in combined:
        try:
            docs = _rag_search(c.get("message", ""))
            c["rag_context"] = _format_rag_docs(docs)
        except Exception as exc:  # noqa: BLE001 — 한 이슈 검색/포맷 실패가 전체를 막지 않게
            log.warning("m3.review.rag_issue_skip", error=f"{type(exc).__name__}: {exc}")


def _review_metrics(payload: M3ReviewRequest) -> dict:
    """코멘트 '📊 지표 줄'용 측정값을 응답에서 추출 — 측정된 것만(가짜 숫자 금지) — 7D.

    - test_verification.metrics.coverage_line(0~1) → coverage_pct(0~100, 반올림).
    - performance.metrics.max_complexity 가 있으면(향후 산출 시) 그대로 전달.
    측정값이 없으면 빈 dict → 렌더가 지표 줄을 통째로 생략한다.
    """
    metrics: dict = {}
    tv = payload.test_verification
    if tv is not None and tv.metrics:
        cov = tv.metrics.get("coverage_line")
        if cov is not None:
            metrics["coverage_pct"] = round(cov * 100)
    perf = payload.performance
    if perf is not None and perf.metrics:
        mc = perf.metrics.get("max_complexity")
        if mc is not None:
            metrics["max_complexity"] = mc
    return metrics


def _review_refine(
    combined: list[dict], verdict: str, skill_level: str, metrics: dict | None = None
) -> str:
    """pr-comment-agent llm_refiner 재사용 → 코멘트 본문. LLM 키 없으면 휴리스틱 fallback.

    metrics(선택)가 있으면 헤더 아래 '📊 지표 줄'로 렌더된다(7D).
    """
    with _prc_isolation():
        from contracts import CombinedIssue
        from llm_refiner import _heuristic_refine, refine

        issues = [CombinedIssue(**c) for c in combined]
        try:
            return refine(issues, verdict, skill_level, metrics=metrics)
        except Exception as exc:  # noqa: BLE001 — LLM 호출 실패는 휴리스틱으로 정직하게 fallback
            log.warning("m3.review.refine_fallback", error=f"{type(exc).__name__}: {exc}")
            return _heuristic_refine(issues, verdict, metrics=metrics)


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

    # 코멘트 직전, 합쳐진 이슈에 사내규칙(rag_context)을 채운다 — RAG_ENABLED 이면 실행(기본 ON).
    _review_augment_rag(combined)

    metrics = _review_metrics(payload)  # 📊 지표 줄용 측정값(없으면 빈 dict → 줄 생략) — 7D
    skill = payload.developer.skill_level if payload.developer else "junior"
    comment_body = _review_refine(combined, verdict, skill, metrics)

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
