# PRD v2.0 — 사내 지식 관리 + 신입 개발자 온보딩 플랫폼 (모듈 기반)

**버전**: v2.0 (M5·M6 현행 구현 보정) | **기준**: Module 0~6 | **이전 버전**: PRD v1.1 (Dev1~Dev5 기반)
**최초 작성일**: 2026-06-04 | **상태**: 초기 기획 + M5·M6 실행 코드 보정

> M5·M6는 각 독립 모듈로 정정했습니다. M0~M4의 역할 상세·공통 Agent 계약·주차별 계획은 초기 설계이며 모두 현재 실행 상태를 뜻하지 않습니다.

---

## 1. 제품 한 줄 정의

> 사내 지식을 AI가 자동 구조화하고, 신입 개발자의 코드 리뷰·학습 경로를 자동화하는 MAS 기반 플랫폼.

**두 가지 핵심 목표:**

- **KMS (Knowledge Management System)**: 사내 문서 → Markdown 정규화 → 구조화 저장 → 자연어 검색
- **온보딩 자동화**: KMS 지식 활용 → PR 코드 리뷰 → 맞춤 학습 추천 → 성장 추적

---

## 2. 시스템 아키텍처 — 모듈 연결 맵

```mermaid
flowchart LR
    GH["GitHub PR"] --> M1["M1 감지·라우팅"]
    M1 --> M2["M2 정적·보안 분석"]
    M1 --> M3["M3 테스트·성능·리뷰 집계"]
    U["사용자"] --> M0["M0 KMS"]
    U --> M4["M4 학습 생성"]
    M4 --> M0
    U --> M6["Module 6: 온톨로지 지식 그래프 관리"]
    M6 --> P["PostgreSQL / pgvector"]
    M6 -->|승인 후 쓰기| N["neo4j_m6"]
    U --> M5["Module 5: YouTube 추천"]
    M5 -->|읽기| N
    M5 --> Y["YouTube Data API"]
```

M5와 M6는 별도 HTTP 서비스다. M6가 지식 그래프를 구축·관리하고 M5가 조회·추천에 사용한다. 최초 PRD에서 M5 하나로 묶었던 외부 문서 추출·그래프 저장·영상 추천 책임을 현재 코드에 맞게 나누었다. M1 호출은 순차 await이며 다이어그램의 가지는 병렬 실행을 뜻하지 않는다.

---

## 3. 모듈별 역할 정의

### Module 0. KMS 사내 지식 파이프라인

**MAS 패턴**: Sequential Pipeline (각 Stage가 이전 Stage 출력에 의존)

**역할**: 사내 문서를 AI가 검색 가능한 지식으로 변환·저장하는 전체 서비스의 지식 저장소.

**처리 흐름:**
```
문서 업로드 (PDF/DOCX/PPTX/TXT)
    → Stage 1: DocumentParser (Upstage/Gemini Multimodal)
    → Stage 2: MarkdownValidate (품질 검증 + retry + HITL)
    → Stage 3: Chunking (결정론적 분할, 512토큰/overlap 128)
    → Stage 4: ChunkValidate (규칙 기반 검증)
    → Stage 5: MetadataExtract (카테고리/태그/엔티티)
    → Stage 6: StoreRoute (pgVector + PostgreSQL + GraphDB)
```

**입력:**
```json
{
  "file": "multipart/form-data",
  "source": "upload | notion | confluence | slack",
  "uploaded_by": "user_id"
}
```

**출력:**
```json
{
  "doc_id": "uuid",
  "status": "stored | hitl_pending | failed",
  "quality_score": 0.85,
  "chunk_count": 12,
  "trace_id": "trc_0001_{doc_id_8hex}"
}
```

**KMS 사용 여부**: 자체가 KMS — 다른 모듈의 KMS 소스  
**HITL 조건**: quality_score < 0.8, 표/이미지 구조 손실, Parent-Child 연결 실패

---

### Module 1. 오케스트레이터

**MAS 패턴**: Supervisor (LangGraph StateGraph, conditional_edges)

**역할**: 사용자/Webhook 요청 수신 → 의도 분류 → 모듈 라우팅 → 결과 취합 → 최종 응답.

**입력:**
```json
{
  "request_type": "pr_review | kms_query | onboarding | architecture",
  "payload": {
    "pr_id": "github-pr-number",
    "pr_diff": "unified diff string",
    "user_id": "string"
  }
}
```

**출력:**
```json
{
  "task_id": "uuid",
  "verdict": "lgtm | rework | escalate",
  "comment_body": "마크다운 형식 GitHub 코멘트",
  "learning_resources": [{"title": "...", "url": "..."}],
  "escalation": {"required": false, "slack_channel": null}
}
```

**KMS 사용 여부**: Yes — pgVector 코사인 유사도 검색으로 관련 컨텍스트 조회  
**GitHub Webhook**: HMAC-SHA256 서명 검증 필수 (X-Hub-Signature-256 없으면 403)

---

### Module 2. 정적 분석 + 보안 분석

**MAS 패턴**: Parallel Independent Agent (asyncio.gather, 타임아웃 30초)

**역할**: PR diff 분석 → 정적 분석(ESLint/Pylint/순환복잡도) + 보안 탐지(SQL Injection/XSS/CSRF/CVE).

**입력 (Module 1이 채움):**
```json
{
  "task_id": "uuid",
  "pr_diff": "string",
  "context": {
    "architecture_docs": ["chunk_id_1"],
    "coding_conventions": "string",
    "previous_pr_issues": ["N+1 쿼리"]
  }
}
```

**출력 (Output Contract — 섹션 6 참고):**
```json
{
  "task_id": "uuid",
  "agent": "static_analysis | security_scan",
  "module_id": "module_2",
  "issues": [...],
  "summary": {"critical": 0, "major": 2, "minor": 5},
  "execution_ms": 1200
}
```

**KMS 사용 여부**: Yes — 코딩 컨벤션, 보안 가이드 chunk 조회  
**타임아웃**: 30초 (초과 시 빈 결과로 대체, agent_traces에 fail 기록)

---

### Module 3. 테스트 검증 + 성능 분석

**MAS 패턴**: Parallel Independent Agent (asyncio.gather, 타임아웃 30초)

**역할**: 커버리지 측정(80% 미달 시 Major) + N+1 쿼리 감지 + 시간복잡도 추정.

**입력**: Module 2와 동일 구조  
**출력**: Module 2와 동일 Output Contract (`agent: "test_verification | performance"`)  
**KMS 사용 여부**: Yes — 테스트 가이드, 성능 최적화 패턴 chunk 조회

---

### Module 4. 커리큘럼 에이전트

**MAS 패턴**: Cyclical Feedback Loop (LangGraph cyclical graph + HITL)

**역할**: Module 2/3 이슈 취합 → 3-Way 판정 → 개인화 피드백 → GitHub 코멘트 + Slack 알림 → 커리큘럼 생성.

**3-Way 판정 로직:**
```
Critical >= 1  → escalate  (Slack 즉시 알림)
Major >= 3     → rework    (힌트 포함, 최대 3회 리트라이)
나머지          → lgtm      (시니어 최종 승인 요청)
```

**입력**: Module 1 State + Module 2/3 Output Contract 목록  
**출력 (→ FE / GitHub / Slack):**
```json
{
  "task_id": "uuid",
  "verdict": "lgtm | rework | escalate",
  "comment_body": "마크다운",
  "learning_resources": [...],
  "onboarding_update": {"issue_pattern": "N+1 쿼리", "occurrence_count": 3}
}
```

**KMS 사용 여부**: Yes — 학습 자료 chunk 조회 + 이전 PR 이력 조회  
**자동 머지 금지**: 시니어 최종 승인은 항상 사람이 한다

---

### Module 5. 기술 맥락 기반 YouTube 추천

**소유 기능:** neo4j_m6 읽기, 개념·대응 기법·코드 메타데이터 조회, 검색어·우선순위 구성, YouTube 검색. FastAPI :8006의 독립 요청·응답 서비스다. 문서 업로드·추출·그래프 쓰기를 포함하지 않는다.

**입력:** POST /youtube/ranked의 concept_name과 선택 mechanism_name, code_id, code_lang, code_framework. code_id는 현재 로직에서 사용하지 않는다.

**출력:** concept_name, videos 배열. 영상별 rank·추천 유형·검색어·제목·URL·썸네일·채널을 제공한다. 검색 실패·빈 결과는 생략하므로 항상 5개를 보장하지 않는다. POST /extract는 호환용 스텁이다.

[Module 5 전용 설명](MODULE_5_GRAPH_YOUTUBE_RULE.md) · [서비스 README](../backend/m5/README.md)

### Module 6. 온톨로지 기반 지식 그래프 관리

**소유 기능:** 외부 URL 수집·청킹·개념 추출·해소·HITL·그래프 저장. FastAPI :8007과 Celery worker, Redis, PostgreSQL/pgvector, Neo4j/APOC를 사용한다. YouTube 검색은 M5의 책임이다.

**입력:** POST /pipeline/trigger의 doc_id 필드에 문서 URL을 전달한다. 이후 session_id 기반 메타데이터 재개·검수·commit API를 사용한다.

**출력:** session_id, SSE 이벤트, staging 후보와 해소 결과, 상태별 집계, topology 노드·관계. 최초 Celery chain은 Prescan→Crawl→Extract이며 Resolver는 Extract 내부, GraphWriter는 승인 후 별도 실행이다.

**지식 모델:** Domain → Concept → Mechanism/RootCause/Component → CodeExample의 4계층. 완료 문서 중복 검사·문서 upsert·행 잠금·Neo4j MERGE·코드 해시 키를 사용하지만 전체 멱등성·DB 간 원자성은 보장하지 않는다.

[Module 6 전용 설명](MODULE_6_ONTOLOGY_KNOWLEDGE_GRAPH.md) · [서비스 README](../backend/m6/README.md)

---

## 4. 초기 Agent Output Contract (M5·M6 HTTP API에는 적용하지 않음)

모듈 간 통신은 이 계약을 정확히 따른다. 필드 추가는 가능하지만 삭제 불가.

```json
{
  "task_id": "uuid",
  "trace_id": "string",
  "agent_name": "string",
  "module_id": "module_0 | module_1 | ... | module_5",
  "status": "success | fail | hitl_pending | escalated",
  "issues": [
    {
      "severity": "Critical | Major | Minor",
      "line": 42,
      "file": "src/auth.py",
      "message": "string",
      "rule_id": "string",
      "suggestion": "string"
    }
  ],
  "summary": {"critical": 0, "major": 2, "minor": 5},
  "validation_result": "pass | fail | skip",
  "execution_ms": 1200,
  "next_agent": "module_4 | null"
}
```

---

## 5. Clean Architecture 레이어

```
[Frameworks & Drivers]   FastAPI, LangGraph, PostgreSQL, pgVector, Neo4j, GitHub API, Slack
        ↑ depends on
[Interface Adapters]     API 계약 JSON, Repository 구현체, Webhook 핸들러
        ↑ depends on
[Use Cases / Application] 각 모듈 Agent 로직 (Module 0~5)
        ↑ depends on
[Entities / Domain]      Document, Chunk, PRReview, MistakePattern, AgentTrace, GraphNode
```

**의존성 방향**: 항상 안쪽(도메인)을 향한다. 상위 레이어는 인터페이스를 통해서만 하위 레이어를 참조.

---

## 6. LangSmith / Harness 적용 기준

초기 공통 설계의 Harness 적용 기준이다. M5·M6의 실제 진입점은 각 FastAPI와 Celery 코드이며, 이 문구만으로 전 경로 Harness·LangSmith 적용을 보장하지 않는다.

```python
# 환경변수 (개인별 GitHub ID 포함 필수)
LANGCHAIN_TRACING_V2=true
LANGCHAIN_PROJECT=module1-yourGitHubId  # 모듈별 + GitHub ID
```

**Trace ID 체계:**
```
문서 파이프라인:  trc_000{stage}_{doc_id_8hex}
PR 리뷰:        pr_{12자리 hex}
서브 trace:     {parent_trace_id}_{agent_name}_{4자리 hex}
```

---

## 7. DB 스키마 핵심

| 저장소 | 용도 | 주요 테이블/컬렉션 |
|--------|------|-------------------|
| PostgreSQL | 메타데이터, PR 이력, trace 로그 | users, documents, chunks, pr_reviews, agent_traces, categories |
| pgVector | 임베딩 벡터 검색 | chunk_embeddings (vector(1024), Ollama bge-m3) |
| Neo4j | 지식 관계 | M0용 neo4j / M6 관리·M5 조회용 neo4j_m6 분리 |
| PostgreSQL / pgvector | M6 문서·검수·매칭 기준 | knowledge_documents, staging_concepts, concepts, framework_metadata, domain_registry |
| Redis | M6 작업·진행 이벤트 | Celery m6_graph / 세션 PubSub |
| GCS/MinIO | 원본 파일 저장 | PDF, DOCX, 이미지 원본 |

**테이블명 주의**: `developers` ❌ → `users` ✅ / `dev_id` ❌ → `user_id` ✅

---

## 8. 초기 마일스톤 계획 (실제 완료 이력 아님)

| 주차 | 목표 | 담당 모듈 | 완료 기준 |
|------|------|-----------|-----------|
| Week 1 | DB 스키마 + API 계약 + Mock 서버 | 전체 | 계약 문서 완성, seed 데이터 INSERT |
| Week 2~3 | 각 모듈 P0 구현 (Mock 기반) | Module 0~5 독립 개발 | 독립 실행 + 단위 테스트 통과 |
| Week 4 | Module 0 문서 파이프라인 5단계 완성 | Module 0 중심 | 실제 문서 → pgVector 저장 확인 |
| Week 5 | Mock → 실제 모듈 연결 (Module 1이 Module 2/3 호출) | Module 1~4 통합 | PR 제출 → 코멘트 E2E 확인 |
| Week 6 | P1 기능 + 버그 수정 + Module 5 연동 준비 | 전체 | 전체 데모 시나리오 동작 |

---

## 9. HITL 위험 방지 규칙

| 상황 | 임계값 | 처리 |
|------|--------|------|
| Markdown 품질 점수 | < 0.8 | HITL 큐 등록, 자동 진행 중단 |
| 표/이미지 구조 손실 | 발생 시 | HITL 큐 등록 |
| Critical 보안 이슈 | >= 1건 | 즉시 Slack 에스컬레이션 |
| 재작업 요청 횟수 | > 3회 | 시니어 직접 개입 요청 |

> **자동 머지 없음.** 시니어의 최종 승인은 항상 사람이 한다.
