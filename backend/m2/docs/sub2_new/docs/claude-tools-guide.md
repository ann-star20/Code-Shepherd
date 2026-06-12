# 3rd-Project-sub2 Claude Code 도구 가이드

> Claude Code에서 사용할 수 있는 Agents / Skills / Commands의 역할과 사용 시점 안내

---

## 세 가지 도구의 차이

| 도구 | 호출 방법 | 로딩 시점 | 역할 |
|------|---------|---------|------|
| **Agents** | 대화 중 자동 or 명시 호출 | 호출 시에만 | 특정 전문 역할을 맡은 전담 AI |
| **Skills** | `/스킬명` or Claude가 판단 | 호출 시에만 | 특정 작업의 실행 패턴·가이드 |
| **Commands** | `/커맨드명` | 호출 시에만 | 반복 워크플로우 자동화 |

**비유:**
- Agent = 전문가 (건축가, 보안 전문가 등)
- Skill = 매뉴얼 (NestJS 작성법, 테스트 작성법 등)
- Command = 버튼 (push 한 번으로 커밋→PR→리뷰 자동화)

---

## Agents — 전문가에게 맡기기

`.claude/agents/` 에 위치. 특정 전문 역할로 독립적으로 동작하는 AI.

### 언제 쓰나?
> "이 작업은 전문가한테 맡기고 싶다"는 생각이 들 때

---

### 개발 전문가 에이전트

| 에이전트 | 언제 호출 | 예시 상황 |
|---------|---------|---------|
| `architect` | 구조 설계 결정 시 | "클린 아키텍처 어떻게 나눌까?" |
| `planner` | 큰 기능 구현 전 | "멀티 에이전트 구현 순서 잡아줘" |
| `rag-architect` | RAG 파이프라인 설계 | "Hybrid Search 구조 어떻게 짜지?" |
| `data-pipeline-engineer` | Airflow·dbt·BigQuery 작업 | "DAG 구조 검토해줘" |
| `prompt-engineer` | LangGraph 프롬프트 최적화 | "개인화 에이전트 프롬프트 개선" |

### 코드 리뷰 에이전트

| 에이전트 | 언제 호출 | 담당 언어/프레임워크 |
|---------|---------|----------------|
| `code-reviewer` | 전반적 코드 리뷰 | 전체 |
| `typescript-reviewer` | React·TypeScript 코드 작성 후 | TypeScript |
| `python-reviewer` | FastAPI·LangGraph 코드 작성 후 | Python |
| `database-reviewer` | Supabase 스키마·쿼리 작성 후 | SQL·PostgreSQL |
| `security-reviewer` | API·인증·환경변수 관련 코드 작성 후 | 보안 전반 |

### 품질 개선 에이전트

| 에이전트 | 언제 호출 | 역할 |
|---------|---------|------|
| `tdd-guide` | 테스트 작성 시 | pytest·Jest·Playwright 가이드 |
| `performance-optimizer` | 응답속도 느릴 때 | Redis 캐싱·쿼리 최적화 |
| `harness-optimizer` | 하네스 실험 설계 시 | 2×2 매트릭스 실험 최적화 |
| `refactor-cleaner` | 클린 아키텍처 리팩토링 시 | 데드코드 제거·구조 정리 |
| `silent-failure-hunter` | 버그 잡기 어려울 때 | 조용히 실패하는 코드 탐지 |

### 학습 에이전트

| 에이전트 | 언제 호출 | 역할 |
|---------|---------|------|
| `learning-mentor` | 모르는 개념·코드 흐름·왜 쓰는지 전부 | 3-Layer 비유 설명 + 학습 노트 자동 저장 |
| `planner-agent` | 오늘 학습 계획 세울 때 | ADHD 친화적 마이크로태스크 분해 |

---

## Skills — 작업 매뉴얼

`.claude/skills/` 에 위치. 특정 기술 작업의 베스트 프랙티스 패턴 모음.

### 언제 쓰나?
> "이걸 어떻게 잘 만들지?" 또는 Claude가 자동으로 판단해서 적용

---

### Sprint별 주로 쓰는 Skills

**Sprint 1 — 인프라·로그인·뼈대**
| 스킬 | 쓰는 상황 |
|------|---------|
| `docker-patterns` | Docker Compose 구성 시 |
| `nestjs-patterns` | NestJS 모듈·컨트롤러·가드 작성 시 |
| `postgres-patterns` | Supabase 스키마 설계 시 |
| `database-migrations` | Supabase 마이그레이션 작성 시 |
| `security-review` | JWT 인증·RLS 설정 시 |
| `git-workflow` | 브랜치 전략·커밋 컨벤션 |

**Sprint 2 — 데이터 파이프라인·MVP**
| 스킬 | 쓰는 상황 |
|------|---------|
| `python-patterns` | FastAPI·Airflow·dbt 코드 작성 시 |
| `python-testing` | pytest 작성 시 |
| `deployment-patterns` | CI/CD·Docker 배포 설정 시 |

**Sprint 3 — 멀티모달 RAG·멀티 에이전트·프론트엔드**
| 스킬 | 쓰는 상황 |
|------|---------|
| `agentic-engineering` | LangGraph 멀티 에이전트 설계 시 |
| `cost-aware-llm-pipeline` | OpenAI·Upstage API 비용 최적화 시 |
| `frontend-patterns` | React 컴포넌트 작성 시 (FeedCard·RagasDashboard·ABCompare) |

> **프론트엔드 컴포넌트 3종**
> - `FeedCard` (기존): 피드 카드
> - `RagasDashboard` (신규): RAGAS 수치 카드 + 라인 차트, FeedPage 하단 좌측
> - `ABCompare` (신규): 4가지 RAG 조합 비교 테이블, FeedPage 하단 우측
> - 추가 패키지: `recharts` (라인 차트용)

**Sprint 4 — 하네스 실험·테스트**
| 스킬 | 쓰는 상황 |
|------|---------|
| `tdd-workflow` | TDD로 테스트 먼저 작성 시 |
| `e2e-testing` | Playwright E2E 테스트 작성 시 |
| `verification-loop` | 구현 완료 후 검증 시 |

**언제든지**
| 스킬 | 쓰는 상황 |
|------|---------|
| `brainstorming` | 새 기능 설계 전 |
| `writing-plans` | 구현 계획 문서 작성 시 |
| `github-ops` | PR·이슈 관리 시 |
| `deep-research` | 기술 리서치가 필요할 때 |
| `product-lens` | 기능 방향 검토 시 |
| `adhd-study-planner` | 학습 계획 수립 시 |
| `project-learning` | 프로젝트 학습 정리 시 |

---

## Commands — 워크플로우 버튼

`.claude/commands/` 에 위치. `/커맨드명` 으로 실행.

| 커맨드 | 언제 | 하는 일 |
|--------|------|---------|
| `/push` | 작업 완료 후 | 중간보고서 작성 → git add → commit → push → PR 생성 → 코드 리뷰 |
| `/plan` | 하루 시작 전 | 오늘 학습·개발 계획 수립 (ADHD 마이크로태스크) |
| `/feature-dev` | 새 기능 개발 시작 전 | 상태 파악 → 계획 → TDD → 구현 → 리뷰 순서로 진행 |
| `/save-qa` | 대화가 길어졌을 때 | 중요한 Q&A 추출해서 `docs/qa/` 에 저장 |
| `/workflow-orchestrator` | 복잡한 자동화 설계 시 | 의존성 있는 작업 흐름 설계 |
| `/tdd` | 새 기능·버그픽스 시작 전 | Red(테스트 작성) → Green(구현) → Refactor 커밋 사이클 안내 |
| `/cost-check` | LLM 호출 코드 작성 후 | tiktoken 기반 토큰 사용량 측정 + 절감 전략 점검 |
| `/update-docs` | 기능·컴포넌트·API 추가 후 | 5개 핵심 문서 일괄 업데이트 |

---

## 한눈에 보는 상황별 선택

```
코드를 짰다
  └── 리뷰 받고 싶다
        ├── TypeScript/NestJS → typescript-reviewer 에이전트
        ├── Python/FastAPI    → python-reviewer 에이전트
        ├── SQL/Supabase      → database-reviewer 에이전트
        └── 보안 관련         → security-reviewer 에이전트

기능을 새로 만들어야 한다
  └── /feature-dev [기능명]
        → brainstorming 스킬 → writing-plans 스킬 → 구현 → /push

모르는 개념이 생겼다
  └── 전부                    → learning-mentor

오늘 하루를 계획하고 싶다
  └── /plan

작업을 커밋하고 싶다
  └── /push

새 기능을 TDD로 만들고 싶다
  └── /tdd [기능명]
        → 테스트 먼저 작성 → 구현 → refactor 커밋

LLM 호출 비용이 걱정된다
  └── /cost-check
        → 토큰 수 측정 → truncation·캐시 전략 점검

문서가 코드와 맞지 않는다
  └── /update-docs [추가된 것]
        → 5개 핵심 문서 일괄 업데이트
```
