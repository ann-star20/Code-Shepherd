"""전체 파이프라인 실측 쇼케이스 (1~6·8단계). 각 단계: ①뭐 ②어디서 ③실제값.

7단계(Gemini 코멘트)는 pr-comment-agent 패키지라 demo_comment.py로 분리.
8단계는 삽입→SELECT→롤백(공유 DB 변경 0). 실행 후 삭제 예정.
"""
import json
import os
import shutil
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def _load_google_key():
    env = HERE / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            if line.startswith("GOOGLE_API_KEY="):
                v = line.split("=", 1)[1].strip().strip('"').strip("'")
                if v:
                    os.environ["GOOGLE_API_KEY"] = v
                    return True
    return False


def banner(n, title):
    print("\n" + "=" * 64)
    print(f"[{n}단계] {title}")
    print("=" * 64)


def main():
    has_key = _load_google_key()
    os.environ["RAG_ENABLED"] = "1"
    os.environ.setdefault("HF_HUB_OFFLINE", "1")  # 캐시 모델 사용(다운로드 stall 방지)

    from contracts import Developer, Dev3Input, RepoInfo
    import main as dev3_main
    from prepare.sandbox import run_sandbox
    import persist
    import psycopg2

    # ── 1단계: 클론 (내 PC) ───────────────────────────────────────────────
    banner(1, "코드 클론")
    print("① 분석할 신입 PR 코드를 작업폴더로 가져옴")
    print("② 어디서: 내 PC (운영은 GitHub git clone, 데모는 번들 샘플을 복사)")
    src_fixture = HERE / "tests" / "fixtures" / "sample_repo"
    work = Path(tempfile.mkdtemp(prefix="showcase_"))
    shutil.copytree(src_fixture, work / "repo")
    work_dir = str(work / "repo")
    py_files = [str(p.relative_to(work_dir)) for p in Path(work_dir).rglob("*.py")]
    print(f"③ 실제: {work_dir}")
    print(f"   받은 .py 파일: {py_files}")

    # ── 2단계: Docker pytest 커버리지 ────────────────────────────────────
    banner(2, "Docker 컨테이너에서 pytest + 커버리지 실측")
    print("① 신입 코드를 격리된 Docker 안에서 실제로 테스트 실행 → 커버리지 측정")
    print("② 어디서: Docker 컨테이너 (이미지 dev3-sandbox)")
    sb = run_sandbox(work_dir)
    cov = sb.get("coverage") or {}
    pct = cov.get("totals", {}).get("percent_covered")
    print(f"③ 실제: returncode={sb['returncode']} (Docker 종료코드)")
    if pct is not None:
        print(f"   ★ 라인 커버리지 = {pct:.1f}%  ← Docker 컨테이너가 실측한 진짜 숫자")
        print(f"   측정 파일: {list(cov.get('files', {}).keys())}")
    else:
        print("   coverage 회수 실패")

    # ── 3~6단계: Dev3 분석 (main.run 한 번에) ────────────────────────────
    diff = (HERE / "tests" / "fixtures" / "sample_pr.diff").read_text(encoding="utf-8")
    inp = Dev3Input(task_id="showcase", scan_id=999, pr_id="PR-showcase",
                    pr_diff=diff, repo=RepoInfo(clone_url="", commit_sha=""),
                    developer=Developer(id="junior_dev_01"))
    print("\n(main.run 실행 — 탐지기 6개 + code_context(Gemini) + RAG(pgvector)…)")
    outputs = dev3_main.run(inp, work_dir)
    issues = [i for o in outputs for i in o.issues]

    banner(3, "탐지기 6개 — 결함 탐지 (AST=사실)")
    print("① 신입 코드에서 N+1·복잡도·커버리지·테스트누락 등 탐지")
    print("② 어디서: 내 PC (Python AST 분석)")
    print(f"③ 실제: {len(issues)}건 탐지")
    for i in issues:
        loc = f"{i.file}:{i.line}" if i.line else i.file
        print(f"   - [{i.rule_id}] {loc}  {i.message[:48]}")

    banner(4, "5컬럼 정규화 (Dev4 통계용)")
    print("① 각 이슈를 통계내기 좋게 keyword·sub_category 등으로 분류")
    print("② 어디서: 내 PC (고정 매핑, LLM 아님)")
    print("③ 실제:")
    for i in issues:
        print(f"   - {i.rule_id}: keyword='{i.keyword}' / sub_category='{i.sub_category}'")

    banner(5, "code_context — 함수 한 줄 설명 (LLM)")
    print(f"① 이슈가 가리키는 함수를 LLM이 한 줄로 설명  (GOOGLE_API_KEY 로드={has_key})")
    print("② 어디서: Gemini (구글) — 무료 키")
    print("③ 실제:")
    for i in issues:
        if i.code_context:
            print(f"   - {i.file}:{i.line} → \"{i.code_context}\"")
    if not any(i.code_context for i in issues):
        print("   (code_context 빈값 — 키 없거나 함수 못 찾음)")

    banner(6, "⭐ RAG — 사내 컨벤션 검색 (pgvector)")
    print("① 이슈 메시지로 사내 가이드를 의미검색해 rag_context에 채움")
    print("② 어디서: GCP pgvector (BGE-M3 임베딩은 내 PC에서)")
    print("③ 실제:")
    for i in issues:
        if i.rag_context:
            print(f"   - [{i.rule_id}] {i.file}:{i.line}")
            print(f"       매칭된 사내가이드: {i.rag_context[:90].replace(chr(10),' ')}…")
    if not any(i.rag_context for i in issues):
        print("   (rag_context 빈값 — RAG_ENABLED 꺼졌거나 검색 결과 없음)")

    # 코멘트(7단계)용으로 이슈 저장
    payload = [{
        "severity": i.severity, "file": i.file, "line": i.line,
        "message": i.message, "rule_id": i.rule_id, "suggestion": i.suggestion,
        "_agent": o.agent, "keyword": i.keyword,
        "sub_category": i.sub_category,
        "code_context": i.code_context, "rag_context": i.rag_context,
    } for o in outputs for i in o.issues]
    (HERE / "showcase_issues.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n(7단계용 이슈 {len(payload)}건 → showcase_issues.json 저장)")

    # ── 8단계: GCP 적재 → SELECT → 롤백 ──────────────────────────────────
    banner(8, "GCP 적재 (삽입 → SELECT 확인 → 롤백)")
    print("① 분석 결과를 공유 DB scan_issues에 적재 (Dev4가 scan_id로 읽음)")
    print("② 어디서: GCP PostgreSQL")
    conn = psycopg2.connect(persist._pg_url(), connect_timeout=15)
    try:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO scan_executions (task_id, pr_id, user_id) "
                        "SELECT %s,%s,user_id FROM users LIMIT 1 RETURNING id",
                        ("showcase-task", "PR-showcase"))
            scan_id = cur.fetchone()[0]
            for i in issues:
                ag = "performance" if i.rule_id.startswith("PERF") else "test_verification"
                # rag_context는 코멘트(7단계)용 — DB 통계 컬럼 아님 → 5컬럼만 적재
                cur.execute(
                    "INSERT INTO scan_issues (scan_id,agent,severity,rule_id,file,line,"
                    "message,suggestion,keyword,sub_category,"
                    "code_context) VALUES "
                    "(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                    (scan_id, ag, i.severity, i.rule_id, i.file, i.line, i.message,
                     i.suggestion, i.keyword,
                     i.sub_category, i.code_context))
            cur.execute("SELECT rule_id, keyword, sub_category, left(code_context,28) "
                        "FROM scan_issues WHERE scan_id=%s ORDER BY id", (scan_id,))
            rows = cur.fetchall()
        print(f"③ 실제: scan_id={scan_id} 에 {len(rows)}행 적재 (SELECT로 되읽음):")
        print("   (rag_context는 코멘트용이라 DB엔 안 넣음 — 5컬럼만 적재)")
        for r in rows:
            print(f"   - {r[0]} | keyword={r[1]} | sub_category={r[2]} | "
                  f"code_context~'{r[3]}…'")
        conn.rollback()
        print("   → 롤백 완료 (공유 DB에 실제로는 안 남김, 흔적 0)")
    finally:
        conn.close()

    # 작업폴더 정리
    shutil.rmtree(work, ignore_errors=True)
    print("\n[1~6·8단계 완료] 7단계 코멘트는: py demo_comment.py (pr-comment-agent)")


if __name__ == "__main__":
    main()
