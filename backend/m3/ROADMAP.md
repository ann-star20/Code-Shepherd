# dev3 m3 — 로드맵

## v1 (현재 — 통합 완료)

- LangGraph 6노드 파이프라인 (assemble→extract→retrieve→sufficiency→judge→compose)
- bge-m3(1024d) + ChromaDB RAG, KMS 규칙 8종
- `/review` POST (집계·판정·코멘트 게시·DB 저장)
- `/verify/tests`, `/analyze/performance` 팀 계약 호환 스텁
- 팀 m1 오케스트레이터 파이프라인 완전 통합

---

## v2 — 레포 풀 소스 분석

> **전제 (팀 협의 필요)**: m1이 PR 웹훅 수신 시 레포를 clone하고 `files_root` 경로를 m3에 전달해야 한다.  
> 현재 m1은 diff 텍스트만 전달하므로 아래 세 기능이 모두 비활성/스텁 상태다.

### 2-1. AST 연관 함수 컨텍스트 추출 (코드 존재, files_root 대기)

**현재 상태**: 코드가 `src/nodes/assemble_input.py`에 구현되어 있으나 **비활성**.

```python
# assemble_input.py
files_root = inp.repo_meta.get("files_root", "")
if files_root:          # ← files_root가 비어있어서 한 번도 실행되지 않음
    contexts = _function_contexts(inp.diff, files_root)
```

**활성화 조건**: m1(또는 직접 호출자)이 `M3ReviewRequest.repo_meta["files_root"]`에 체크아웃된 소스 경로를 전달.

**활성화 후 효과**: PR diff의 변경 줄을 포함하는 **함수 전문**(AST 추출)이 `pr_context`에 추가되어 LLM judge가 함수 단위 전체 컨텍스트를 보고 판정 → 오탐 감소 기대.

**필요 작업**:
- m1: PR 수신 시 `git clone` + `files_root` 경로를 `M3ReviewRequest`에 추가 (m1 담당, 팀 협의)
- m3: 없음 (이미 구현됨)

---

### 2-2. 테스트 커버리지 실측 (`/verify/tests` 실구현)

**현재 상태**: `/verify/tests`는 **빈 pass 스텁**. 실제 테스트 커버리지 분석 없음.

```python
@app.post("/verify/tests")
async def verify_tests(payload: _TeamVerifyRequest) -> _TeamVerifyResponse:
    return _TeamVerifyResponse(task_id=payload.task_id, agent="test_verification")
    # issues=[], summary(critical/major/minor)=0 — 분석 없음
```

**구현 계획**:
- `clone_url` + `commit_sha`로 레포 체크아웃 (m1이 넘겨주는 경우 활용 가능)
- `pytest --cov` 실행 후 커버리지 보고서 파싱
- 변경 함수 기준 미커버 라인 → `IssueItem` 생성
- 현재 `/verify/tests`에 넘어오는 `M3VerifyRequest.clone_url`, `commit_sha`는 m1이 이미 포함해서 보냄 — 파싱 코드만 추가하면 됨

**전제**: 안전한 샌드박스 실행 환경(컨테이너 격리), 실행 타임아웃 관리.

---

### 2-3. 성능 분석 실측 (`/analyze/performance` 실구현)

**현재 상태**: `/analyze/performance`는 **빈 pass 스텁**. 실제 성능 분석 없음.

```python
@app.post("/analyze/performance")
async def analyze_performance(payload: _TeamVerifyRequest) -> _TeamVerifyResponse:
    return _TeamVerifyResponse(task_id=payload.task_id, agent="performance")
    # issues=[], 분석 없음
```

**구현 계획 (옵션 A — 정적)**:
- diff에서 성능 안티패턴 시그니처 탐지 (현재 judge가 하는 CONV-DB-004 N+1 등)
- LLM 호출 없이 regex/AST 기반 → 저비용

**구현 계획 (옵션 B — 동적)**:
- 레포 clone + `py-spy` / `cProfile` 실행 후 핫스팟 보고
- 실행 환경 요건 높음

**전제**: files_root 또는 clone_url 필요 (m1 협의 동일).

---

## 전제 정리 (팀 협의 항목)

| 항목 | 현재 | v2 목표 | 담당 |
|------|------|---------|------|
| m1 → m3 전달 데이터 | diff 텍스트만 | diff + `files_root`(체크아웃 경로) | **m1 팀** |
| `M3ReviewRequest` 스키마 | 변경 없음 | `repo_meta["files_root"]` 추가 | 팀 공통 |
| `/verify/tests` | 스텁 (빈 pass) | pytest 커버리지 실측 | m3 (dev3) |
| `/analyze/performance` | 스텁 (빈 pass) | 정적/동적 성능 분석 | m3 (dev3) |
| AST 함수 컨텍스트 | 코드 있음, 비활성 | files_root 전달되면 자동 활성 | m3 (dev3), 대기 중 |
