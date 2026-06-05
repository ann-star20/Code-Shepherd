# 브랜치 전략

**프로젝트**: 사내 지식 관리 + 신입 개발자 온보딩 플랫폼  
**팀 구성**: 6명 (FE 1 + 서비스 5)

---

## 1. 브랜치 구조

```text
main                            ← 배포 브랜치
├── api-core                    ← API 공통 코어
├── dev                         ← 통합 개발 브랜치 (feature/* PR 대상)
├── feature/module0-kms         ← KMS 문서 파이프라인 (담당: Dev1)
├── feature/module1-orchestrator← 오케스트레이터 + Webhook (담당: Dev2)
├── feature/module2-static-security  ← 정적분석 + 보안 (담당: Dev3)
├── feature/module3-test-performance ← 테스트 + 성능 (담당: Dev4)
├── feature/module4-curriculum  ← 커리큘럼 에이전트 (담당: Dev5)
└── feature/module5-graph-youtube    ← GraphDB + YouTube 추천 (담당: Dev6)
```

---

## 2. 모듈별 담당 브랜치

| 모듈 | 브랜치 | 담당 역할 |
|------|--------|-----------|
| Module 0 | `feature/module0-kms` | KMS 문서 파이프라인 (PDF/DOCX → pgVector) |
| Module 1 | `feature/module1-orchestrator` | Webhook 수신, 의도 분류, 병렬 실행 조율 |
| Module 2 | `feature/module2-static-security` | ESLint/Pylint, SQL 인젝션/XSS/CSRF 탐지 |
| Module 3 | `feature/module3-test-performance` | 커버리지 측정, N+1 쿼리 감지 |
| Module 4 | `feature/module4-curriculum` | 3-Way 판정, GitHub 코멘트, Slack 에스컬레이션 |
| Module 5 | `feature/module5-graph-youtube` | Neo4j 엔티티 추출, YouTube 학습 추천 |

---

## 3. 개발 플로우

### 일반 개발 (Week 2~4)

```text
feature/{module}
    │
    │  (기능 개발 + 단위 테스트 작성)
    ▼
PR 생성 (feature/* → dev)
    │
    │  (코드 리뷰 — 최소 1명 승인)
    ▼
dev 머지
```

### 통합 주간 (Week 5)

```text
dev
└── integration/week5          ← Week 5 전용 통합 브랜치
      ├── feature/dev1-real-connect
      ├── feature/dev2-real-connect
      └── feature/dev3-real-connect

통합 브랜치 → E2E 확인 → dev → main
```

---

## 4. 브랜치 명명 규칙

```text
# 새 기능
feature/module{N}-{기능요약}
예: feature/module0-parser-quality-loop
    feature/module2-sql-injection-scan

# 버그 수정
fix/module{N}-{버그요약}
예: fix/module1-kms-empty-result

# 프론트엔드
feature/fe-{기능명}
예: feature/fe-pr-review-dashboard

# 통합 (Week 5)
integration/week5
```

---

## 5. PR 규칙

### PR 대상

```text
feature/* → dev        (일반 개발)
integration/* → dev    (통합 주간)
dev → main             (배포, 팀장 승인 필요)
```

### PR 체크리스트

```text
□ 단위 테스트 통과 (Mock 기반, 실 DB/LLM 없이)
□ Output Contract 변경 → docs/MODULE_CONTRACT.md 업데이트 + 영향 모듈 담당자 공지
□ src/common/state.py 변경 → PR description 명시 + 전 모듈 알림
□ Harness 실행 결과 또는 LangSmith trace_id 첨부
□ 최소 1명 코드 리뷰 승인
```

### 절대 금지

```text
✗ main 직접 push
✗ 다른 모듈 담당 파일 임의 수정
✗ --force push (force push는 팀장 승인 후 예외적으로만)
✗ --no-verify (hook 우회)
✗ 자동 머지 코드 (PR 최종 결정은 항상 사람이 한다)
```

---

## 6. 주간 마일스톤

| 주차 | 브랜치 상태 | 완료 기준 |
|------|------------|-----------|
| Week 1 | feature/* 생성 | DB 스키마 합의, API 계약 문서 완성, seed 데이터 INSERT |
| Week 2~3 | feature/* 개발 중 | 독립 실행 + 단위 테스트 통과 |
| Week 4 | feature/* → dev PR | 실제 문서 → pgVector 저장 확인 |
| Week 5 | integration/week5 | PR 제출 → 코멘트 등록 E2E 확인 |
| Week 6 | dev → main | 전체 데모 시나리오 동작 |
