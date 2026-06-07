<!-- CLAUDE.md -->
## 컨텍스트 주입 규칙

태스크별로 필요한 PRD 파일만 로드한다.
PRD 전체를 한 번에 로드하지 않는다.

| 태스크 유형 | 로드할 파일 |
|------------|------------|
| 도메인 모델·유즈케이스 | PRD-domain-V2.md |
| DB 스키마·Cypher | PRD-schema-V2.md |
| 테스트 작성 | PRD-qa.md |
| 인프라·Docker | PRD-infra-V2.md |
| 폴더·아키텍처 확인 | PRD-arch.md |

## 8. 개발 순서 (Development Phases)

### Phase 1 — Backend Core
1. PostgreSQL + Neo4j 스키마 설계 및 마이그레이션 (`staging_concepts` 포함)
2. OWASP Top 10 / CWE SW Dev View / CWE Top 25 시드 데이터 적재 스크립트
3. FastAPI 라우터 구성 (URL 입력 API, Pre-scan API, 파이프라인 트리거 API)
4. Celery + Redis 비동기 태스크 구성 및 상태 관리
5. **[LangSmith]** 테스트 하네스 환경 구성 (`docker-compose.test.yml`, DB 픽스처)

### Phase 2 — Agent Pipeline
6. Pre-scan Layer: URL 패턴 파싱 + HTML 메타 추론 + Human-in-the-Loop API
7. Crawler Agent: 웹 크롤링 및 텍스트 정제
8. **[LangSmith]** Pre-Eval 실행: `extractor_schema_eval` 데이터셋 구성 → `gemini-2.5-flash` 프롬프트 후보 평가 → 스키마 이탈률 0% 달성 프롬프트 확정
9. Extractor Agent: 확정 프롬프트 적용, 4종 컨셉 타겟, `concept_domain` 필드 포함 JSON 추출 → `staging_concepts` DRAFT 적재. LangSmith `@traceable` 래핑
10. 최종 승인 게이트 API (`/approve`, `/reject`, `/diff`) 구현
11. Graph Writer Agent: APPROVED 항목 → `concept_domain` 기반 다중 라벨 결정 → `MERGE` 단일 노드 → `apoc.create.addLabels` 라벨 누적 → state = COMMITTED
12. Link Resolver Agent: SAME_AS 탐색, 유사도 기반 노드 병합. LangSmith 트레이싱 적용
13. **[LangSmith]** 하네스 통합 테스트 실행: 레이스 컨디션, DB 락, MERGE 멱등성, 다중 라벨 누적 검증

### Phase 3 — Frontend
14. React + TypeScript + Vite 프로젝트 셋업
15. Human-in-the-Loop 메타데이터 검증 UI (추론 신뢰도 배지, 인터락 폼)
16. 파이프라인 5단계 상태 인디케이터 컴포넌트
17. WebSocket/SSE 기반 실시간 로그 콘솔
18. 가상 노드 미리보기: `GET /api/graph/topology` + `GET /api/staging/{session_id}` 클라이언트 병합 렌더링
19. 승인 UI: DRAFT 노드 점선/반투명 스타일, 개별 승인/거부 토글, diff 요약, 최종 승인 버튼
20. react-force-graph 토폴로지 뷰 (온톨로지 계층 필터, 색상 범례, COMMITTED 후 가상→실제 노드 전환)
21. 컨셉 인스펙터 패널 (4종 컨셉 타입 필터 + 상세 대응 방안)

### Phase 4 — 프로덕션 모니터링 (LangSmith)
22. **[LangSmith]** HITL 수정 피드백 기록: 관리자 수정 diff → `client.create_feedback()` 연동
23. **[LangSmith]** 피드백 환류: 수정 빈도 높은 패턴 → `extractor_schema_eval` 데이터셋 추가 → Pre-Eval 재실행
24. **[LangSmith]** 모니터링 알림 설정: 스키마 이탈 1건/시간 → Slack, HITL 수정률 ≥ 20% → 프롬프트 재평가 트리거

## 세션 비용 관리

- 한 세션 = 태스크 1개 (G1~G10 각각 독립 세션)
- 세션 시작 전: /cost 확인
- $20 초과 시: /compact 실행 후 계속
- $50 초과 시: 세션 종료 후 새 세션으로 다음 태스크 시작

## /compact 타이밍

구현 GREEN 확인 직후, 커밋 전에 /compact 실행
→ 대화 이력 압축, 생성된 코드는 파일에 이미 저장됨


## 12. 형상 관리 및 Git 커밋 규칙 (Git Commit Convention)

모든 개발자 및 AI 협업 도구는 소스코드 변경 이력을 명확히 추적하고 코드 리뷰 효율을 높이기 위해 **Conventional Commits 1.0.0** 규격을 준수한다.

### 12.1. 커밋 메시지 구조

```
<type>(<scope>): <subject>          ← Header (필수)

[body]                              ← Body (선택, 변경 이유 및 상세 설명)

[footer]                            ← Footer (선택, 이슈 번호, Breaking Change)
```

- **Header**: 소문자, 50자 이내, 명령형 현재 시제
- **Body**: 72자 줄바꿈, "무엇을 왜" 설명
- **Footer**: `Closes #123`, `BREAKING CHANGE: ...`

### 12.2. 필수 커밋 타입 (Type)

| 타입 | 설명 | 예시 |
|------|------|------|
| `feat` | 새로운 기능 추가 | 에이전트 로직 구현, API 엔드포인트 신설 |
| `fix` | 버그 수정 | 파이프라인 락 에러 해결, JSON 파싱 예외 처리 |
| `docs` | 문서 수정 | PRD 업데이트, README.md 수정 |
| `style` | 코드 포맷팅, 세미콜론 누락 등 | 비즈니스 로직 변경 없음 |
| `refactor` | 코드 리팩토링 | 기능 추가나 버그 수정 없는 구조 개선 |
| `test` | 테스트 코드 추가 및 수정 | 테스트 하네스, PyTest 스크립트 추가 |
| `chore` | 빌드, 패키지 매니저, 도커파일 수정 | 프로덕션 코드 변경 없음 |

### 12.3. 프로젝트 전용 Scope 규정

제목의 `()` 안에 들어갈 Scope는 아래 항목으로 강제한다.

| Scope | 변경 모듈 |
|-------|-----------|
| `input` | Input Agent 및 URL Pre-scan 관련 |
| `crawler` | Crawler Agent 및 DOM 정제 관련 |
| `extractor` | Extractor Agent 및 Gemini 프롬프트/JSON 스키마 관련 |
| `writer` | Graph Writer Agent 및 PostgreSQL/Neo4j 적재 관련 |
| `resolver` | Link Resolver Agent 및 벡터 유사도 병합 관련 |
| `db` | 마이그레이션 스크립트, 시드 데이터(`schema.sql`, `seed_data.cypher` 등) 관련 |
| `infra` | Docker, Docker Compose, Cloud SQL Proxy 설정 관련 |
| `frontend` | UI 컴포넌트, 상태 관리, react-force-graph 관련 |

### 12.4. 커밋 예시

```bash
# 기능 추가 — Mechanism/Property 통합 노드 및 TUNED_BY 관계 도입 반영
feat(extractor): unify mechanism and property nodes for security and performance domains

# 버그 수정
fix(writer): rollback postgresql on neo4j connection timeout

# 테스트 — Mechanism 통합 및 HAS_EXAMPLE 경로 변경 유닛 테스트
test(writer): add T04 neo4j mechanism unified label dedup harness test

# 인프라
chore(infra): add cloud-sql-proxy service with gcp profile

# DB 스키마 — domains TEXT[] 배열 구조 수용 DDL 반영
feat(db): add staging_concepts table with array validation and state machine columns

# 리팩터
refactor(resolver): extract alias similarity into shared util

# BREAKING CHANGE 포함
feat(writer): enforce two-phase commit for cross-db atomicity

BREAKING CHANGE: graph_writer_task now raises CrossDbCommitError
on neo4j failure instead of silently continuing
```

---
