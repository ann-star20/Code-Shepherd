"""Streamlit 데모 UI (세션 B 소유) - make demo

시연 4장면 지원:
  장면1/4: PR 선택 or diff 붙여넣기 -> 리뷰 실행 -> comment_md 렌더
  장면2  : findings 테이블 (rule_id, verdict, severity, 근거 줄, 환각 배지, 출처 링크)
  장면3  : gap 경로 - 지침공백 리포트 + 신규 지침 제안
  장면4  : 핫스왑 - corpus 수정 -> make reindex -> 동일 PR 재실행 버튼
           원복 버튼 - git checkout corpus/ && make reindex

파이프라인 호출: src.adapters.streamlit_adapter.review() 만 사용 (src 내부 구조 비의존).
파이프라인 미구현(D2 전) 시 안내 배너를 표시하고 앱은 정상 유지.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import streamlit as st

REPO_ROOT = Path(__file__).resolve().parent.parent
DEMO_DIR = REPO_ROOT / "fixtures" / "demo"

_DEMO_SCENES = {
    "장면1 — 위반 탐지 (async requests)": "scene1_violation.txt",
    "장면2 — 오탐 회피 (scripts/ 예외)": "scene2_exception.txt",
    "장면3 — 지침공백 (subprocess 규정 없음)": "scene3_gap.txt",
    "장면4 — 핫스왑 전 (httpx 정상)": "scene4_hotswap.txt",
}

# ── 코퍼스 인덱스 로드 (환각 배지 + 출처 링크용) ─────────────────────────────

@st.cache_resource(show_spinner=False)
def _corpus_idx():
    try:
        from eval.harness import build_corpus_index, _default_corpus_dir
        return build_corpus_index(_default_corpus_dir())
    except Exception:
        return {}


# ── 골든 PR 목록 로드 ────────────────────────────────────────────────────

@st.cache_resource(show_spinner=False)
def _golden_cases():
    try:
        from eval.harness import load_golden_cases
        return {c.pr_id: c for c in load_golden_cases(REPO_ROOT / "golden")}
    except Exception:
        return {}


def _reload_resources():
    _corpus_idx.clear()
    _golden_cases.clear()


# ── 헬퍼 ────────────────────────────────────────────────────────────────

def _halluc_badge(finding_dict: dict, diff: str) -> str:
    idx = _corpus_idx()
    if not idx:
        return ""
    try:
        from contracts import Finding
        from eval.harness import verify_finding
        f = Finding(**finding_dict)
        r = verify_finding(f, diff, idx)
        return "OK" if r["ok"] else "HALLUC"
    except Exception:
        return "?"


def _source_link(rule_id: str) -> str:
    """rule_id → corpus 파일 상대 경로 (없으면 빈 문자열)."""
    idx = _corpus_idx()
    doc = idx.get(rule_id)
    if not doc:
        return ""
    try:
        return str(Path(doc.source_path).relative_to(REPO_ROOT))
    except ValueError:
        return doc.source_path


def _run_review(diff: str, file_paths: list[str], files: dict[str, str]) -> tuple:
    """(ReviewOutput | None, trace, error_msg | None)"""
    try:
        from src.adapters.streamlit_adapter import review_traced
        output, trace = review_traced(diff, file_paths, repo_meta={"source": "streamlit", "files": files})
        return output, trace, None
    except NotImplementedError as e:
        return None, [], f"파이프라인 미구현 (D2 통합 전): {e}"
    except Exception as e:
        return None, [], f"{type(e).__name__}: {e}"


def _render_timeline(trace: list[dict]) -> None:
    """⓪→⑤ 노드 실행 타임라인 — run_review_traced 기록 그대로 (추가 LLM 호출 없음)."""
    if not trace:
        return
    st.subheader("파이프라인 실행 흐름")
    total_ms = sum(r["ms"] for r in trace)
    cols = st.columns(len(trace))
    for col, rec in zip(cols, trace):
        icon = "✅" if rec["ok"] else "❌"
        col.metric(label=f"{icon} {rec['label']}", value=f"{rec['ms']}ms")
    with st.expander(f"단계별 상세 (총 {total_ms}ms)", expanded=False):
        for rec in trace:
            icon = "✅" if rec["ok"] else "❌"
            st.markdown(f"{icon} **{rec['label']}** — {rec['summary']} `({rec['ms']}ms)`")


def _run_reindex() -> tuple[bool, str]:
    py = sys.executable
    res = subprocess.run(
        [py, "-m", "src.ingestion"],
        capture_output=True, text=True, cwd=str(REPO_ROOT), encoding="utf-8", errors="replace",
    )
    return res.returncode == 0, res.stderr[:1000] if res.returncode != 0 else ""


# ── 결과 렌더링 ──────────────────────────────────────────────────────────

def _render_output(output, diff: str) -> None:
    if output.gap_report:
        st.subheader("지침공백 리포트 (장면3)")
        gap = output.gap_report
        st.warning(f"**패턴 요약**: {gap.pattern_summary}")
        with st.expander("시도한 검색 질의", expanded=False):
            for q in gap.queries_tried:
                st.code(q, language=None)
        if gap.nearest_rule_ids:
            st.info("근접 규칙: " + ", ".join(gap.nearest_rule_ids))
        with st.expander("신규 지침 제안 초안", expanded=True):
            st.markdown(gap.proposed_rule_md)

    if output.findings:
        st.subheader("Findings")
        rows = []
        for f in output.findings:
            fd = f.model_dump()
            badge = _halluc_badge(fd, diff)
            src = _source_link(f.rule_id)
            rows.append({
                "rule_id": f.rule_id,
                "verdict": f.verdict,
                "severity": f.severity,
                "file": f.file or "-",
                "근거 (첫 줄)": (f.evidence_lines[0][:80] if f.evidence_lines else "-"),
                "인용 검증": badge,
                "출처": src,
            })
        import pandas as pd
        df = pd.DataFrame(rows)

        def _style(val):
            if val == "violation":
                return "color: #d62728; font-weight: bold"
            if val == "no_violation":
                return "color: #2ca02c"
            if val == "HALLUC":
                return "background: #ffe0e0; color: #d62728; font-weight: bold"
            if val == "OK":
                return "color: #2ca02c"
            return ""

        st.dataframe(df.style.applymap(_style, subset=["verdict", "인용 검증"]), use_container_width=True)

        halluc_count = sum(1 for f in output.findings if _halluc_badge(f.model_dump(), diff) == "HALLUC")
        if halluc_count:
            st.error(f"환각 의심 {halluc_count}건 - rule_quote 또는 evidence_lines 가 코퍼스/diff 와 불일치합니다.")
        elif _corpus_idx():
            st.success("모든 인용 검증 통과 - rule_id 실존, rule_quote/evidence string-match OK")

        with st.expander("finding 상세 (reasoning + fp_note + 출처)", expanded=False):
            for f in output.findings:
                src = _source_link(f.rule_id)
                link_md = f" ([출처]({src}))" if src else ""
                st.markdown(f"**{f.rule_id}** `{f.verdict}`{link_md}")
                st.text(f.reasoning or "-")
                if f.rule_quote:
                    st.caption(f"> {f.rule_quote}")
                if f.fp_note:
                    st.info(f"오탐 점검: {f.fp_note}")
    elif not output.gap_report:
        st.success("지적 없음 (no_violation / 정상 PR)")

    st.subheader("생성된 코멘트 (comment_md)")
    st.markdown(output.comment_md)
    with st.expander("마크다운 원문", expanded=False):
        st.code(output.comment_md, language="markdown")


# ── 메인 UI ──────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="Dev3 코드리뷰 에이전트",
        page_icon=":mag:",
        layout="wide",
    )
    st.title(":mag: Dev3 코드리뷰 에이전트 - 데모")
    st.caption("사내 KMS 컨벤션에 근거해서만 리뷰 코멘트를 답니다.")

    idx = _corpus_idx()
    golden = _golden_cases()

    if not idx:
        st.warning(
            "코퍼스 인덱스 없음 - `make reindex` 를 먼저 실행하거나 "
            "세션 C 통합 전이면 환각 배지는 '?' 로 표시됩니다."
        )
    else:
        st.sidebar.success(f"코퍼스 규칙 {len(idx)}개 로드")

    # ── 사이드바: 입력 소스 선택 ─────────────────────────────────────────
    st.sidebar.header("입력 방법")
    input_mode = st.sidebar.radio(
        "diff 소스",
        ["시연 장면 선택", "golden/ PR 선택", "직접 붙여넣기"],
        horizontal=False,
    )

    diff = ""
    file_paths: list[str] = []
    files: dict[str, str] = {}
    label_info = ""

    if input_mode == "시연 장면 선택":
        scene_label = st.sidebar.selectbox("장면", list(_DEMO_SCENES.keys()))
        fname = _DEMO_SCENES[scene_label]
        fpath = DEMO_DIR / fname
        if fpath.exists():
            diff = fpath.read_text(encoding="utf-8")
            st.sidebar.caption(f"`fixtures/demo/{fname}` 로드됨")
            if "scene4" in fname:
                st.sidebar.info(
                    "장면4 핫스왑: corpus/conv_api_001.md 에서 `httpx` → `aiohttp` 로 수정 후 "
                    "**make reindex** 실행 → 같은 diff 재실행하면 판정 변경."
                )
        else:
            st.sidebar.error(f"fixtures/demo/{fname} 없음")

    elif input_mode == "golden/ PR 선택":
        if not golden:
            st.sidebar.info("golden/ 에 PR 없음 - 세션 C 통합 후 사용 가능")
        else:
            pr_id = st.sidebar.selectbox("PR 선택", sorted(golden.keys()))
            if pr_id:
                case = golden[pr_id]
                diff = case.diff
                file_paths = case.file_paths
                files = case.files
                label_info = (
                    f"기대 라벨: `{case.label.expected}` "
                    f"| 분류: **{case.category}**"
                )
    else:
        diff = st.text_area(
            "unified diff 붙여넣기",
            height=300,
            placeholder="--- a/app/api.py\n+++ b/app/api.py\n@@ ...",
        )
        if diff:
            from eval.harness import _parse_file_paths
            file_paths = _parse_file_paths(diff)

    # ── 버튼 행 ────────────────────────────────────────────────────────
    col1, col2, col3, col4 = st.columns([2, 2, 2, 2])
    run_btn = col1.button(":arrow_forward: 리뷰 실행", type="primary", disabled=not diff)
    reindex_btn = col2.button(":recycle: make reindex (핫스왑)")
    rollback_btn = col3.button(":arrows_counterclockwise: 핫스왑 원복")
    if col4.button(":refresh: 리소스 새로 고침"):
        _reload_resources()
        st.rerun()

    if reindex_btn:
        with st.spinner("make reindex 실행 중..."):
            ok, err = _run_reindex()
        if ok:
            _reload_resources()
            st.success("reindex 완료 - corpus 변경 사항이 적용됐습니다. 같은 PR 을 다시 실행하세요.")
        else:
            st.error(f"reindex 실패\n```\n{err}\n```")

    if rollback_btn:
        with st.spinner("핫스왑 원복 중 (git checkout corpus/ && make reindex)..."):
            git_res = subprocess.run(
                ["git", "checkout", "corpus/"],
                capture_output=True, text=True, cwd=str(REPO_ROOT), encoding="utf-8", errors="replace",
            )
            if git_res.returncode != 0:
                st.error(f"git checkout corpus/ 실패: {git_res.stderr[:500]}")
            else:
                ok, err = _run_reindex()
                if ok:
                    _reload_resources()
                    st.success("핫스왑 원복 완료 — corpus 원상복구 + reindex 완료. eval 수치 정상.")
                else:
                    st.error(f"reindex 실패 (corpus는 복구됨)\n```\n{err}\n```")

    if label_info:
        st.info(label_info)

    if not run_btn:
        return

    if not diff.strip():
        st.warning("diff 를 입력하세요.")
        return

    with st.spinner("리뷰 에이전트 실행 중..."):
        output, trace, err = _run_review(diff, file_paths, files)

    if err:
        st.error(err)
        if "미구현" in err:
            st.info(
                "파이프라인은 D2 메인 세션에서 구현됩니다. "
                "현재는 하네스·UI 껍데기가 준비된 상태입니다."
            )
        return

    _render_timeline(trace)
    _render_output(output, diff)


main()
