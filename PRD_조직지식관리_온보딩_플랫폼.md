# PRD: 조직 지식 관리 + 개발자 온보딩 멀티 에이전트 플랫폼

**문서 버전**: v2.0 (Module 0~5 기준 재편)
**작성일**: 2026-05-22 | **최종 수정**: 2026-06-04
**팀 구성**: 6명 (프론트엔드 1 + 서비스 구현 5)
**MVP 범위**: 개발자 직군 신입사원 온보딩
**기술 핵심**: MAS (Multi-Agent System) + HITL + Harness (LangSmith)

> **v1.1 → v2.0 변경 사항**: 개발 단위를 Dev1~Dev5 기준에서 Module 0~5 기준으로 재편.
> KMS 파이프라인(§5)·페르소나(§2)·사용자 스토리(§3) 등 제품 내용은 변경 없음.

---

## 1. 제품 개요

### 한 줄 정의
> "사내 지식을 AI가 자동으로 구조화하고, 신입 개발자의 코드 리뷰·학습 경로를 자동화하는 멀티 에이전트 플랫폼"

### 두 가지 목표

| 목표 | 설명 |
|------|------|
| **Goal 1: KMS** | PDF·DOCX·PPTX·TXT 등 사내 문서를 Markdown으로 정규화 후 구조화 저장. 누구나 자연어로 검색·질의. |
| **Goal 2: 온보딩** | KMS 지식을 활용해 신입 개발자 PR 자동 코드 리뷰, 맞춤형 교육자료 추천, 성장 진도 추적. |

---

## 2. 사용자 페르소나

### Persona A: 팀장 / 시니어 개발자
- **주요 고통**: 신입 PR 리뷰에 하루 1~2시간 소비. 같은 실수 반복 피드백에 지침. 사내 문서 어디 있는지 물어보는 질문 반복.
- **원하는 것**: "Critical 이슈만 나한테 오고, 나머지는 자동으로 처리됐으면. 문서 갱신 알림도 버튼 하나로."
- **사용 맥락**: Slack 알림 → PR 링크 클릭 → 승인/거절

### Persona B: 신입 개발자 (MVP 대상)
- **주요 고통**: 질문할 타이밍 못 잡음. 사내 문서 어디 있는지 모름. PR 리뷰 기다리는 시간 길다. 지금 뭘 공부해야 하는지 모름.
- **원하는 것**: "PR 올리면 즉시 피드백. 학습 로드맵 자동으로 받고 싶다."
- **사용 맥락**: GitHub PR 제출 → 자동 코멘트 수신 → 추천 학습자료 클릭

---

## 3. 사용자 스토리

### 팀장/시니어
```
US-01  Critical 보안 이슈 발생 시 즉시 Slack 알림 수신 (SQL 인젝션 등)
US-02  신입 반복 실수 패턴 → 사내 코딩 가이드 업데이트 제안 자동 수신
US-03  신입 팀원 주간 성장 지표 확인 (커버리지 변화, Critical 감소율)
US-04  사내 지식 자연어 검색 ("우리 팀 인증 방식이 뭐였지?")
US-05  6개월 이상 미업데이트 문서 알림 수신 후 승인 한 번으로 KMS 갱신
```

### 신입 개발자
```
US-06  PR 제출 → 60초 이내 자동 코드 리뷰 코멘트 수신
US-07  피드백에 내 수준 맞는 설명 + 관련 사내 문서 링크
US-08  입사 첫날 기술스택 기반 주차별 학습 로드맵 자동 생성
US-09  자연어 질문으로 사내 지식 검색 ("배포 프로세스가 어떻게 돼요?")
US-10  PR 리뷰 히스토리 + 성장 그래프 확인
```

---

## 4. 공유 저장소 레이어 (전원 공동 구축 — 선행 필수)

### DB 아키텍처

```
입력 문서 (PDF / DOCX / PPTX / TXT)
         │
    [Markdown 변환]
    UnStructured.io + Gemini Multimodal
         │
    ┌────┴──────────────────────────────┐
    │                                   │
    ▼                                   ▼
Storage (S3 / MinIO)            PostgreSQL (라우터 DB)
- 이미지 원본                    - chunk 메타데이터
- 페이지 이미지 원본              - 권한 정보
- Markdown 원본                  - 업로드 상태
- Docx 원본                      - trace 로그
                                 - 검증 결과
                                 - relation 일부
         │                              │
    공통 Key 값 (Agent가 인식 쉽게 — 모든 DB 연결 키)
         │                              │
    ▼                                   ▼
pgVector (벡터 검색)              GraphDB (관계 저장)
- 청크 단위 임베딩 저장            - 데이터 간 관계 관리
- Parent 청킹 임베딩              - 문서-엔티티 관계
- Child 청킹 임베딩               - 코드 의존성 맵
```

### 청킹 전략 (RAG 성능 최적화)

문서 종류마다 청킹 기준이 달라지는 문제를 **Markdown 중간 변환**으로 통일.

| 전략 | 구성 | LLM | 사용 상황 |
|------|------|-----|-----------|
| 1단계 | 단순 청크 300~500 (텍스트) | 일반 LLM | 빠른 검색 |
| 2단계 | 단순 청크 + 이미지 | 멀티모달 LLM | 다이어그램 포함 문서 |
| 3단계 | Parent(800~1500) + Child(300~500) | 이미지 멀티모달 | 긴 기술 문서 |
| **4단계 (목표)** | **태깅+분류+메타데이터 + Parent/Child** | **이미지 멀티모달** | **MVP 목표 수준** |

> **MVP 목표**: 4단계 전략으로 RAG 정확도 최대화.
> 속도 우선이면 1단계부터 구현 후 점진적으로 4단계로 업그레이드.

### 공통 Key 구조 예시

```json
{
  "doc_id": "uuid-v4",
  "chunk_id": "uuid-v4",
  "parent_chunk_id": "uuid-v4 | null",
  "trace_id": "trc_XXXX",
  "source": "notion | confluence | slack | upload",
  "created_at": "ISO8601",
  "status": "processing | validated | stored | failed"
}
```

---

## 5. 문서 처리 파이프라인 (KMS Ingestion) — 전원 공동

**MAS 구조**: Supervisor 패턴 + HITL (Human-in-the-Loop)
**Harness**: LangSmith (모든 에이전트 호출 추적)

### 5단계 파이프라인

```
입력 문서
    │
[1단계] Markdown 변환 Agent (trace_id: trc_0001)
    주요 역할: 문서 파싱, 이미지/표 추출, Markdown 변환
    출력: Markdown 원본
    │
[2단계] Markdown 검증 Agent (trace_id: trc_0002)
    주요 역할: 구조 품질 검증, 누락/손실 검증, 표/이미지 검증
    출력: 검증 리포트
    │
    ├─ 검증 점수 ≥ 임계치? ──Yes──▶ [3단계]로 진행
    └─ No (예외 상황) ──────────▶ Human Review (수정 후 재검증)

[3단계] 청킹 Agent (trace_id: trc_0003)
    주요 역할: Header 기반 분할, Parent/Child 생성, Overlap 설정
    출력: Chunks + Metadata
    │
[4단계] Chunk 검증 Agent (trace_id: trc_0004)
    주요 역할: chunk 크기 검증, Parent/Child 연결 검증, 맥락 유지 검증
    출력: 검증 리포트
    │
    ├─ 검증 점수 ≥ 임계치? ──Yes──▶ [5단계]로 진행
    └─ No (예외 상황) ──────────▶ Human Review (수정 후 재검증)

[5단계] 메타데이터 추출 Agent (trace_id: trc_0005)
    주요 역할: 엔티티 추출, 카테고리 분류, 관계 후보 추출
    출력: Metadata + Entities
    │
[6단계] 저장 & 라우팅 (trace_id: trc_0006)
    PostgreSQL 라우터가 Storage / pgVector / GraphDB로 분산 저장
```

### HITL (Human-in-the-Loop) 개입 기준

| 단계 | 예외 발생 기준 | Human이 할 일 |
|------|---------------|---------------|
| Markdown 검증 (2차) | 품질 점수 < 0.8 | Markdown 내용 수정, 누락 보완, 승인 |
| | 표/이미지 구조 손실 감지 | |
| | OCR 누락/페이지 손실 감지 | |
| | 필수 섹션 누락 | |
| Chunk 검증 (4차) | chunk 길이 기준 초과/미달 | Chunk 조정/분할, Parent-Child 재연결, 승인 |
| | Parent-Child 연결 실패 | |
| | Context 맥락 검증 실패 | |
| | Overlap 부족 | |
| 기타 (선택) | Metadata 추출 신뢰도 낮음 | 엔티티/관계 보완, 분류/카테고리 불명확 시 수정 |

> Human이 수정/승인하면 시스템이 자동으로 해당 단계부터 재검증 시작.

---

## 6. 기능 요구사항 — 모듈별

---

### Module 1: 오케스트레이터 + KMS 검색 에이전트

**MAS 패턴**: Supervisor
**하네스**: LangGraph StateGraph + LangSmith 추적

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| F-ORC-01 | GitHub Webhook 수신 및 HMAC-SHA256 서명 검증 | P0 |
| F-ORC-02 | 요청 의도 분류 (PR 리뷰 / KMS 질의 / 온보딩 / 아키텍처 질문) | P0 |
| F-ORC-03 | 에이전트 라우팅 및 결과 취합 후 응답 생성 | P0 |
| F-ORC-04 | 각 에이전트 호출에 trace_id 부여 및 LangSmith 로깅 | P0 |
| F-KMS-01 | 변경 모듈 관련 아키텍처 문서 조회 (pgVector 검색) | P0 |
| F-KMS-02 | 팀 코딩 컨벤션 문서 조회 | P0 |
| F-KMS-03 | 이전 PR 이력 조회 (PostgreSQL) | P1 |
| **검증** | 라우팅 정확도 검증 에이전트 (의도 분류 오류율 추적) | P1 |
| **검증** | 컨텍스트 품질 평가 에이전트 (검색된 문서 관련성 점수) | P1 |

---

### Module 2: 정적 분석 + 보안 스캔 에이전트

**MAS 패턴**: Parallel Independent Agents
**하네스**: asyncio.gather (동시 실행)

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| F-SA-01 | ESLint / Pylint 실행 및 결과 파싱 | P0 |
| F-SA-02 | 순환복잡도 측정 (임계값: 10 이상 시 Major) | P1 |
| F-SA-03 | 중복 코드 감지 | P1 |
| F-SA-04 | 코드 스멜 감지 (너무 긴 함수, 과도한 파라미터) | P2 |
| F-SEC-01 | SQL 인젝션 패턴 탐지 | P0 |
| F-SEC-02 | XSS / CSRF 취약점 탐지 | P0 |
| F-SEC-03 | 의존성 CVE 스캔 | P0 |
| F-SEC-04 | OWASP Top 10 체크리스트 검사 | P1 |
| F-SA-05 | 결과를 표준 출력 계약 형식으로 반환 | P0 |
| **검증** | 오탐(false positive)률 추적 에이전트 | P1 |
| **검증** | 보안 룰셋 최신화 확인 에이전트 | P1 |

**출력 계약**
```json
{
  "agent": "static_analysis | security_scan",
  "task_id": "uuid",
  "issues": [
    {
      "severity": "Critical | Major | Minor",
      "line": 42,
      "file": "src/auth.py",
      "message": "SQL 인젝션 가능성: 사용자 입력이 직접 쿼리에 삽입됨",
      "rule_id": "SEC-001",
      "suggestion": "파라미터화된 쿼리 사용 권장"
    }
  ],
  "summary": { "critical": 1, "major": 3, "minor": 7 },
  "execution_ms": 1200
}
```

---

### Module 3: 테스트 검증 + 성능 분석 에이전트

**MAS 패턴**: Parallel Independent Agents
**하네스**: asyncio.gather (동시 실행)

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| F-TEST-01 | 테스트 커버리지 측정 (라인/브랜치/함수) | P0 |
| F-TEST-02 | 커버리지 80% 미달 시 Major 이슈 분류 | P1 |
| F-TEST-03 | 엣지케이스 누락 탐지 (null, 빈 배열, 음수 등) | P1 |
| F-TEST-04 | 단위 테스트 누락 함수 목록 제안 | P1 |
| F-PERF-01 | 시간복잡도 추정 (O(n²) 이상 경고) | P1 |
| F-PERF-02 | N+1 쿼리 패턴 감지 | P0 |
| F-PERF-03 | 메모리 누수 가능 패턴 감지 | P1 |
| F-PERF-04 | 병목 지점 탐지 및 최적화 제안 | P2 |
| **검증** | 커버리지 측정 정확도 검증 에이전트 | P1 |
| **검증** | 성능 분석 false alarm 추적 에이전트 | P1 |

---

### Module 4: 커리큘럼 에이전트 (Evaluator + Feedback Loop)

**MAS 패턴**: Aggregator + Conditional Router
**하네스**: LangGraph conditional_edges

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| F-EVAL-01 | Module 2, Module 3 4개 에이전트 결과 취합 | P0 |
| F-EVAL-02 | LGTM 판정 기준: Critical 0 + Major ≤ 2 | P0 |
| F-EVAL-03 | 재작업 요청: Major ≥ 3 또는 Minor 다수 | P0 |
| F-EVAL-04 | 즉시 에스컬레이션: Critical ≥ 1 | P0 |
| F-EVAL-05 | 재작업 시 힌트 제공 (최대 3회 리트라이) | P1 |
| F-EVAL-06 | 시니어 최종 승인 요청 메시지 생성 | P0 |
| F-PERS-01 | 개인별 실력 수준 프로파일 유지 (초급/중급/고급) | P1 |
| F-PERS-02 | 수준별 피드백 코멘트 생성 (초급: 상세, 고급: 간결) | P0 |
| F-PERS-03 | KMS 관련 학습 자료 링크 삽입 (Module 1 KMS 검색 API 호출) | P1 |
| F-PERS-04 | GitHub PR 코멘트 자동 작성 | P0 |
| F-PERS-05 | 성장 커브 시각화 데이터 생성 | P2 |
| **검증** | 판정 일관성 검증 에이전트 (동일 코드 → 동일 판정) | P1 |
| **검증** | 개인화 품질 평가 에이전트 (수준 분류 정확도) | P1 |

**3-Way 판정 로직**
```
Critical ≥ 1  →  즉시 에스컬레이션
               Slack #team-{팀이름} 알림 + PR 링크
               시니어가 직접 검토 후 머지 결정

Major ≥ 3    →  재작업 요청
               구체적 피드백 + 힌트 (≤3회)
               재제출 시 동일 파이프라인 재실행

나머지       →  LGTM
               시니어에게 최종 머지 승인 요청
               (자동 머지 없음 — 항상 사람이 최종 결정)
```

---

### Module 4 (계속): 온보딩 이력 + 피드백 루프

**MAS 패턴**: Cyclical Feedback Loop + Human-in-the-Loop
**하네스**: LangGraph cyclical graph

| ID | 요구사항 | 우선순위 |
|----|----------|----------|
| F-CURR-01 | 기술스택 기반 주차별 학습 로드맵 자동 생성 | P0 |
| F-CURR-02 | 역할별 커리큘럼 분기 (백엔드/프론트엔드/DevOps) | P1 |
| F-CURR-03 | PR 통과율·커버리지 기준 커리큘럼 자동 진급 | P1 |
| F-HIST-01 | PR 결과 이력 저장 (판정, 이슈 목록, 소요 시간) | P0 |
| F-HIST-02 | 반복 실수 패턴 탐지 및 PostgreSQL 기록 | P0 |
| F-HIST-03 | 주간 성장 지표 계산 API | P1 |
| F-FEED-01 | 반복 PR 패턴 → 코딩 가이드 업데이트 제안 생성 | P1 |
| F-FEED-02 | Slack으로 담당자에게 승인 요청 발송 | P1 |
| F-FEED-03 | 승인 시 문서 파이프라인 재실행 트리거 (KMS 갱신) | P1 |
| F-FEED-04 | 문서 노후화 감지 (6개월 미업데이트) | P2 |
| **검증** | 커리큘럼 적절성 검증 에이전트 (난이도 순서 적절성) | P1 |
| **검증** | 피드백 루프 완결성 추적 에이전트 (루프 E2E 확인) | P1 |

**피드백 루프 흐름**
```
Module 4 PR 리뷰 결과 수신
    │
패턴 감지: "N+1 쿼리 지적 이번 달 8회"
    │
코딩 가이드 업데이트 제안 생성
    │
Slack 알림 → 시니어 승인 (Human-in-the-Loop)
    │
문서 파이프라인 재실행 (Module 0, Stage 1~6)
    │
KMS 업데이트 완료 → 다음 PR부터 반영
    │
Module 4 커리큘럼 에이전트 자동 반영 ← 루프 완결
```

---

### 프론트엔드 (1명)

| ID | 화면 | API 출처 | 우선순위 |
|----|------|----------|----------|
| F-FE-01 | KMS 자연어 검색 & 질의 | Module 1 오케스트레이터 | P0 |
| F-FE-02 | 신입 온보딩 대시보드 (주차별 로드맵) | Module 4 커리큘럼 API | P0 |
| F-FE-03 | PR 리뷰 결과 뷰어 (이슈 목록 + 피드백) | Module 4 평가 API | P0 |
| F-FE-04 | 성장 진도 & 추천 문서 화면 | Module 4 개인화 API | P1 |
| F-FE-05 | 지식 현황 / 문서 갱신 요청 관리 (팀장용) | Module 4 운영 API | P1 |
| F-FE-06 | 시니어 에스컬레이션 수신 & 승인 화면 | Module 4 평가 API | P0 |

---

## 7. Harness Engineering (LangSmith)

모든 에이전트 실행은 LangSmith로 추적·평가.



### LangSmith가 하는 것

| 기능 | 설명 |
|------|------|
| **Trace 수집** | 모든 Agent 호출, LLM 호출, 도구(DB/Parser 등) 호출 자동 추적 |
| **자동 평가** | 품질 리포트, 평가/누락률, 검증 품질, 처리 시간/토큰 수집 |
| **피드백 루프** | 실패 사례 분석 → 프롬프트 개선 → 모델/파싱 전략 개선 |
| **대시보드** | 실시간 모니터링, 트레이스 탐색, 에러 유형 Top N |

### Trace ID 체계

```
각 문서 처리 파이프라인 실행 시:

trc_0001  Markdown 변환 Agent
trc_0002  Markdown 검증 Agent
trc_0003  청킹 Agent
trc_0004  Chunk 검증 Agent
trc_0005  메타데이터 추출 Agent
trc_0006  저장 & 라우팅

PostgreSQL에 trace 로그 저장:
{
  "trace_id": "trc_0001",
  "agent_name": "MarkdownConverterAgent",
  "input_summary": "...",
  "output_summary": "...",
  "status": "success | fail | review",
  "started_at": "ISO8601",
  "ended_at": "ISO8601",
  "error_message": "if any"
}
```

### LangSmith 성과 지표 (예시)

| 지표 | 목표값 |
|------|--------|
| 전체 성공률 | ≥ 95% |
| 검증 통과율 | ≥ 90% |
| 평균 처리 시간 | ≤ 30초 / 문서 |
| Human 개입률 | ≤ 10% |
| 에러 유형 Top N | 매주 리뷰 |

---

## 8. 에이전트 간 API 계약

### 입력 계약: 오케스트레이터 → 분석 에이전트 (Module 2, Module 3)

```json
{
  "task_id": "uuid",
  "pr_id": "github-pr-number",
  "pr_diff": "string (unified diff format)",
  "context": {
    "architecture_docs": ["chunk_id_1", "chunk_id_2"],
    "coding_conventions": "string",
    "previous_pr_issues": ["N+1 쿼리", "SQL 인젝션"]
  },
  "developer": {
    "id": "string",
    "skill_level": "junior | mid | senior",
    "tech_stack": ["python", "fastapi", "postgresql"]
  }
}
```

### 출력 계약: 분석 에이전트 → 평가 에이전트 (Module 4)

```json
{
  "task_id": "uuid",
  "agent": "static_analysis | security_scan | test_verification | performance",
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
  "summary": { "critical": 0, "major": 2, "minor": 5 },
  "execution_ms": 1200
}
```

### 출력 계약: 평가 에이전트 → 프론트엔드 / GitHub / Slack

```json
{
  "task_id": "uuid",
  "pr_id": "string",
  "verdict": "lgtm | rework | escalate",
  "comment_body": "string (마크다운 형식 GitHub 코멘트)",
  "learning_resources": [
    { "title": "사내 N+1 쿼리 가이드", "url": "notion://..." }
  ],
  "escalation": {
    "required": true,
    "slack_channel": "#team-security",
    "message": "Critical SQL 인젝션 탐지. PR #123 즉시 확인 필요."
  },
  "onboarding_update": {
    "issue_pattern": "N+1 쿼리",
    "occurrence_count": 3
  }
}
```

---

## 9. 사용자 흐름 스토리보드

### 신입 개발자 흐름

```
[Day 1 — 입사]
커리큘럼 에이전트가 기술스택 기반 주차별 로드맵 자동 생성
  → "1주차: REST API 설계 원칙 → 사내 문서 3개 자동 추천"
  → 프론트엔드 대시보드에서 학습 현황 확인

[Day 5 — 첫 PR 제출]
신입이 GitHub에 PR 올림
  ↓ 자동 (신입은 아무것도 안 해도 됨)
1. Module 1: GitHub Webhook 수신 → KMS 관련 문서 검색
2. Module 2 + Module 3: 4개 에이전트 병렬 분석 (~30초)
3. Module 4: 결과 종합 → 판정
4. GitHub 코멘트 자동 등록:
   "line 42: N+1 쿼리 발생. 지금 수준에서 자주 나오는 실수예요.
    참고 문서: [사내 DB 쿼리 최적화 가이드] (Notion, 2025-09)"
  ↓
LGTM → 시니어에게 최종 승인 요청
재작업 → 힌트 받고 수정 후 재제출
Critical → Slack으로 시니어에게 즉시 알림

[2주 후 — 성장 추적]
개인화 에이전트가 "N+1 쿼리 지적 0회, 커버리지 평균 +15%"
  → 커리큘럼 다음 단계 자동 진급
  → 프론트엔드 성장 그래프 업데이트
```

### 팀장/시니어 흐름

```
[평소 — KMS 활용]
"우리 팀 인증 방식이 뭐였지?" → KMS 검색 → 즉시 답변 + 출처 문서
  ↓
피드백루프 에이전트가 Slack으로:
  "6개월 지난 문서 3개 업데이트 필요합니다. [승인] 버튼 클릭 시 자동 갱신"

[신입 PR Critical 발생 시]
Slack: "신입 김OO의 PR에서 SQL 인젝션 취약점 발견. #team-backend"
  → 링크 클릭 → PR 코멘트 확인 → LGTM / 머지 거절
  → 피드백루프에 기록 → 코딩 가이드 업데이트 제안 수신

[주간 리포트]
프론트엔드 대시보드:
  "이번 주 신입 3명 PR 12건.
   반복 실수 패턴: N+1 쿼리 (7회), 테스트 누락 (4회).
   → 사내 코딩 가이드에 섹션 추가 제안합니다. [승인 / 수정 후 승인]"
```

---

## 10. 시스템 아키텍처 개요

```
[사용자 / 클라이언트]
    프론트엔드 (React + TypeScript)
         │
         ▼
[Module 1] 오케스트레이터 에이전트 ─────────────── LangSmith 추적
    의도 분류 · 에이전트 라우팅 · 결과 취합
    LangGraph StateGraph
         │
    ┌────┼───────────────────────┐
    │    │                       │
    ▼    ▼                       ▼
[Mod2] 정적분석  [Mod2] 보안스캔  [KMS 컨텍스트]
[Mod3] 테스트    [Mod3] 성능분석   (pgVector 검색)
    └───────────────────┘
              │
              ▼
[Module 4] 커리큘럼 에이전트 (Evaluator)
    LangGraph conditional_edges
         │
    ┌────┼────┐
    ▼    ▼    ▼
  LGTM 재작업 에스컬레이션
              │
              └──► Slack 알림

[Module 4] 온보딩 이력 + 피드백 루프
    LangGraph cyclical graph
         │
    [패턴 감지] → [가이드 업데이트 제안] → [승인] → [파이프라인 재실행]

[공유 저장소 레이어]
┌────────────────────────────────────────────────┐
│  Storage(S3)  │  PostgreSQL(라우터)  │  pgVector  │  GraphDB  │
└────────────────────────────────────────────────┘
         공통 Key (doc_id / chunk_id / trace_id)

[Harness]
LangSmith ── 모든 에이전트 호출 자동 추적 + 품질 대시보드

[외부 도구]
GitHub · Slack · Confluence · Notion · Google Drive
```

---

## 11. 비기능 요구사항

| 항목 | 요구사항 |
|------|----------|
| **응답 시간** | PR 제출 → 코멘트 등록: 60초 이내 (4개 에이전트 병렬 기준) |
| **문서 처리** | 문서 1건 파이프라인 완료: 30초 이내 (Human 개입 없을 때) |
| **보안** | GitHub Webhook HMAC-SHA256 서명 검증 |
| **추적성** | 모든 에이전트 실행에 trace_id 부여. LangSmith에 로그 저장. |
| **확장성** | 에이전트 추가 시 오케스트레이터 라우팅 테이블만 수정 |
| **테스트** | 각 에이전트 단위 테스트 + E2E 시나리오 테스트 필수 |
| **HITL** | 예외 상황 Human 개입률 목표 ≤ 10% |

---

## 12. 기술 스택

| 레이어 | 기술 | 비고 |
|--------|------|------|
| 언어 | Python 3.11+ | 에이전트 서버 |
| 에이전트 프레임워크 | **LangGraph** | MAS 구현 핵심 |
| LLM | Claude (claude-sonnet-4-6) / Gemini Multimodal | 피드백 생성, 멀티모달 문서 처리 |
| 문서 변환 | **UnStructured.io** + Gemini Multimodal | PDF/DOCX → Markdown |
| Vector DB | **pgVector** (PostgreSQL 확장) | 청크 임베딩 저장 |
| 메타 DB | **PostgreSQL** | 라우터 역할, 메타데이터, trace 로그 |
| 원본 저장소 | **S3 / MinIO** | 이미지, Markdown, Docx 원본 |
| Graph DB | **GraphDB / Neo4j** | 관계 맵, 엔티티 관계 |
| GitHub 연동 | PyGitHub | Webhook + PR 코멘트 |
| 알림 | Slack Webhook API | 에스컬레이션, 갱신 알림 |
| **Observability** | **LangSmith** | 에이전트 추적, 품질 대시보드 |
| 프론트엔드 | React + TypeScript | 단일 UI |
| 로컬 통합 | Docker Compose | 전체 스택 단일 실행 |

---

## 13. 개발 우선순위

| 우선순위 | 기준 |
|----------|------|
| **P0** | MVP 데모에 필수. 없으면 시연 불가. |
| **P1** | MVP에 포함 권장. 시간 여유 시 구현. |
| **P2** | 다음 버전. 이번 MVP 스코프 밖. |

---

## 14. 마일스톤

| 주차 | 목표 | 완료 기준 |
|------|------|-----------|
| **Week 1** | 팀 전체: DB 스키마 + API 계약 합의 + LangSmith 연동 | 계약 문서 완성, mock 서버 세팅, LangSmith 프로젝트 생성 |
| **Week 2~3** | 각자 P0 기능 구현 (mock 기반 병렬 개발) | 각 서비스 독립 실행 + 단위 테스트 통과 |
| **Week 4** | 문서 파이프라인 5단계 완성 (공동) | 실제 문서 업로드 → pgVector 저장 확인 |
| **Week 5** | Mock → 실제 에이전트 연결 (통합) | PR 제출 → 코멘트 등록 E2E 동작 확인 |
| **Week 6** | P1 기능 + 버그 수정 + 발표 준비 | 전체 데모 시나리오 동작 상태 |

---

## 15. 데모 시나리오 (발표용)

```
시나리오: "신입 개발자 김OO의 첫 주 온보딩"

Step 1. 입사 첫날
  - 기술스택 입력: "Python, FastAPI, PostgreSQL"
  - 커리큘럼 에이전트: 4주차 학습 로드맵 자동 생성

Step 2. 사내 지식 검색
  - 질문: "우리 팀 API 설계 가이드가 있나요?"
  - KMS: pgVector 검색 → 관련 Notion 문서 답변 + 출처 명시

Step 3. 첫 PR 제출 (N+1 쿼리 포함 코드)
  - GitHub PR 제출 → Webhook 수신
  - 4개 에이전트 병렬 분석 (~30초)
  - GitHub 자동 코멘트: "N+1 쿼리 감지. 참고: [사내 쿼리 최적화 가이드]"

Step 4. 재작업 후 재제출
  - 수정된 PR → 자동 재분석 → LGTM
  - 시니어에게 머지 승인 요청

Step 5. 3주 후 — 피드백 루프 동작
  - N+1 쿼리 패턴 7회 감지
  - 팀장 Slack: "코딩 가이드 업데이트 제안. [승인]"
  - KMS 자동 갱신 → 다음 신입부터 반영
```

---

## 16. 스코프 밖 (Out of Scope — MVP)

- 개발자 외 직군 온보딩 (영업, 디자인, PM)
- 실시간 음성/화상 온보딩
- 외부 고객 대상 서비스
- 멀티 테넌시
- 모바일 앱
- 자동 머지 (시니어 최종 승인은 항상 사람이)
- 실제 Confluence/Notion 연동 (MVP는 샘플 문서 파일로 대체)

---

## 17. 리스크 및 해결 방안

| 리스크 | 영향도 | 해결 방안 |
|--------|--------|-----------|
| DB 스키마 합의 지연 → 전체 블로킹 | 높음 | Week 1에 mock API 먼저 제공. 실제 DB는 후에 교체. |
| UnStructured.io 변환 품질 낮음 | 중간 | HITL 기준 강화. 품질 점수 임계치 올려서 Human Review 유도. |
| LLM API 비용 초과 | 중간 | 개발 중 mock LLM. 실제 API는 통합 테스트 + 데모 시에만. |
| 4개 에이전트 병렬 타임아웃 | 중간 | 에이전트별 30초 타임아웃. 초과 시 해당 에이전트 결과 제외 후 진행. |
| pgVector 검색 품질 저하 | 중간 | Parent/Child 청킹 + Re-ranking 전략. LangSmith로 정확도 모니터링. |
