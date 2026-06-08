# [Dev1/M1 담당자께] m3 연결을 위한 계약 필드 요청

> **From**: Dev3(m3, 테스트·성능) → **To**: M1(오케스트레이터) 담당
> **한 줄**: m1이 m3를 호출할 때 보내는 `M3VerifyRequest`에 **repo·diff 정보가 없어서** m3가 실제 분석(clone·pytest·AST)을 못 합니다. 아래 **선택 필드 4개만** 채워 보내주시면 연결됩니다. (하위호환 — m2/m4 영향 없음)

---

## 1. 지금 무엇이 문제인가

현재 흐름(`m1/app/routers/triggers.py` → `module_clients.call_m3_*`):
```
GitHub 웹훅 → m1 /triggers/pr → M3VerifyRequest 생성 → m3 /verify/tests · /analyze/performance
```

그런데 m1이 채우는 `M3VerifyRequest`(`_shared/shared/contracts.py`)는:
```python
class M3VerifyRequest(BaseModel):
    task_id: str
    pr_id: str
    pr_diff: str          # ← 지금 여기에 GitHub의 diff_url(URL 문자열)만 들어옴
    context: AnalysisContext = ...
    developer: DeveloperProfile | None = None
    trace_id: str | None = None
```

m3가 하는 일은 **신입 PR 코드를 실제로 clone 받아 Docker에서 pytest(커버리지)·AST 분석**입니다. 이를 위해선:
- 어떤 레포를(=clone URL), 어느 커밋을(=commit SHA) 받아야 하는지
- 실제 diff **텍스트**(어떤 파일·줄이 바뀌었는지) — `diff_url`(URL)만으론 부족, 본문이 필요

가 있어야 합니다. **현재 계약엔 이 정보가 없습니다.**

> 참고: m1 `triggers.py`에서 이미 `pull_request` dict 전체를 들고 있습니다(`html_url`, `diff_url`, `head.sha`, `base.repo.clone_url` 등). 그 안의 값을 아래 필드로 옮겨 담아 주시면 됩니다.

---

## 2. 요청 — `M3VerifyRequest`에 선택 필드 4개 추가

`_shared/shared/contracts.py`의 `M3VerifyRequest`에 **Optional 필드**로 추가 (기본값 있으니 기존 호출 안 깨짐):

```python
class M3VerifyRequest(BaseModel):
    task_id: str
    pr_id: str
    pr_diff: str
    # ── m3 연결용 신규(선택) ──
    repository: str | None = None     # "owner/repo"  (repository.full_name)
    clone_url: str | None = None      # "https://github.com/owner/repo.git" (clone용)
    commit_sha: str | None = None     # PR head 커밋 (pull_request.head.sha)
    raw_diff: str | None = None       # diff 본문 텍스트 (불가하면 m3가 diff_url로 직접 받음)
    # ────────────────────────
    context: AnalysisContext = Field(default_factory=AnalysisContext)
    developer: DeveloperProfile | None = None
    trace_id: str | None = None
```

그리고 m1 `triggers.py`의 `verify_req = M3VerifyRequest(...)` 생성부에서 GitHub payload 값으로 채워 주세요:

```python
verify_req = M3VerifyRequest(
    task_id=task_id,
    pr_id=trigger.pr_id or "",
    pr_diff=trigger.pr_diff,                       # 기존 유지
    repository=repository,                          # raw["repository"]["full_name"]
    clone_url=pull_request.get("head", {}).get("repo", {}).get("clone_url")
              or raw.get("repository", {}).get("clone_url"),
    commit_sha=pull_request.get("head", {}).get("sha"),
    raw_diff=None,                                  # 채우기 어려우면 None (m3가 처리)
    context=AnalysisContext(),
    trace_id=trigger.trace_id,
)
```

> `raw_diff`까지 주시면 가장 좋지만(네트워크 1회 절약), 어려우면 `repository`+`clone_url`+`commit_sha` 3개만이라도 충분합니다. m3가 `diff_url` 혹은 clone 후 `git diff`로 본문을 확보하겠습니다.

---

## 3. 확인 요청 — 응답 계약은 그대로

m3 응답 `M3VerifyResponse`(agent=`test_verification`/`performance`, `issues: list[IssueItem]`)는 **변경 없습니다.** m4로 가는 `M4EvaluateRequest.test_verification`·`performance` 매핑도 그대로면 됩니다. 즉 **m1↔m4 사이는 손댈 필요 없고, m3로 가는 요청에 위 4개 필드만 추가**하면 됩니다.

## 4. (별건·확인만) PR 코멘트 등록 주체

플랫폼 모드에서 m4가 `comment_body`를 만든 뒤 **GitHub PR에 실제로 코멘트를 올리는 주체**가 m1인지 m4인지 정해져 있나요? (m3 옛 독립 게이트웨이에는 poster가 있었지만, 플랫폼에선 m3 범위 밖으로 봅니다.) 이 부분 합의된 위치만 알려주시면 m3 결과가 거기에 잘 실리는지 맞춰보겠습니다.

---

**정리**: `M3VerifyRequest`에 `repository`·`clone_url`·`commit_sha`(+가능하면 `raw_diff`) 선택 필드 추가 & payload에서 채워 전달. 그러면 m3가 clone→분석→이슈 반환까지 연결됩니다. 문의: Dev3.
