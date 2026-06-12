# dev2 폴더 이전 파이프라인 (sub2_new/dev2 → backend/m2/dev2)

**일자**: 2026-06-12 | **브랜치**: `feature/module2-static-security`
**작업**: 내 풀 설계 패키지 `dev2`를 `sub2_new` 래퍼에서 꺼내 운영 폴더와 **같은 레벨(backend/m2)** 로 통째 이동.
**방식**: Option A (패키지 통째 이동) — `app/` 가동 구조는 건드리지 않음.

---

## 1. Before → After 폴더 구조

### Before
```
backend/m2/
  app/                 ← docker가 호출하는 운영 실체 (app.main:app)
  sub2_new/
    dev2/              ← 내 풀 설계 (LangGraph 7노드 + 코멘트/알림/벡터)
      api/ nodes/ tools/ prompts/ repositories/ ...
      graph.py db.py schema.py main.py
    docs/ common/ db_schema/ .claude/ ... (설계·학습 문서 다수)
```

### After
```
backend/m2/
  app/                 ← (무수정) 운영 실체
  dev2/                ← ★ 여기로 이동 (app과 형제 레벨)
    api/ nodes/ tools/ prompts/ repositories/ ...
    graph.py db.py schema.py main.py
  sub2_new/            ← dev2 빠진 나머지 (docs/·설계md·.claude/ 등 약 230파일, 미이전)
  reports/
```

---

## 2. 이동의 핵심 — 왜 이렇게 옮겼나

| 항목 | 내용 |
|------|------|
| **이동 단위** | `dev2/` 패키지 **통째**. 내부 `from dev2.* import` 를 한 줄도 안 고쳐도 됨 |
| **왜 backend/m2 직속?** | 이전엔 `dev2`가 `sub2_new/` 안에 있어 import하려면 PYTHONPATH=sub2_new 필요. 이제 `app`과 동일하게 backend/m2가 루트 → `app`·`dev2` **둘 다 최상위 패키지** 로 나란히 import 가능 |
| **app/ 무수정** | `app/`은 `from dev2`를 **전혀 import하지 않음**(grep 확인). 따라서 dev2 위치가 바뀌어도 `/analyze/static`·`/analyze/security`·`app/main.py`·`app/analyzer.py` 에 영향 0 |
| **이동 도구** | `git mv`는 dev2 내부 ignored 파일(`.env`, `__pycache__/`, `result_all.txt`)에 막힘 → 일반 `mv` 후 `git add`로 스테이징. git rename 감지로 **히스토리 보존**(R 표시) |

---

## 3. 네임스페이스 모델 (이동 후)

```
backend/m2/  (= 패키지 루트, PYTHONPATH 기준)
├── app/      →  import app.main / app.analyzer / app.orchestrator   (운영, 가동 중)
└── dev2/     →  import dev2.graph / dev2.schema / dev2.db ...        (풀 설계, 미연결)
```

- 두 패키지는 **독립**. 서로 import하지 않는다(현재).
- `app/db.py`는 과거 `dev2/db.py`에서 복사해 둔 사본 — 이동과 무관하게 그대로.
- 향후 연결이 필요하면 **app 쪽에서만** 최소 import (예: `from dev2.graph import run_dev2`). dev2를 app 하위로 분산 흡수하지 않음(이번 결정의 핵심 제약).

---

## 4. 배포 영향 (Docker)

`backend/m2/Dockerfile`:
```dockerfile
COPY m2 /app/service        # backend/m2 전체 복사 → dev2도 /app/service/dev2 로 함께 들어감
WORKDIR /app/service
RUN uv sync --no-dev --extra analysis
CMD ["uv","run","uvicorn","app.main:app","--host","0.0.0.0","--port","8003"]
```

| 점검 | 결과 |
|------|------|
| 빌드가 `sub2_new/dev2` 경로를 참조? | ❌ 안 함. `COPY m2`로 트리 전체 복사라 경로명 무관 |
| 컨테이너가 dev2를 실행? | ❌ `app.main:app`만 기동. dev2는 이미지에 포함되나 import 안 됨 |
| 결론 | **이동이 런타임/배포에 영향 0.** 재빌드 시 dev2 위치만 `/app/service/dev2`로 바뀜 |

---

## 5. 검증 체크리스트

- [x] `dev2` → `backend/m2/dev2` 이동 완료 (tracked 99파일, git rename 보존)
- [x] `sub2_new/dev2` 제거됨
- [x] `app/`에 `from dev2` import 없음 → `/analyze/*` 영향 없음 (grep 확인)
- [x] Dockerfile/compose/pyproject에 `sub2_new` 참조 없음
- [x] dev2 내부 `from dev2.*` import 불변 (네임스페이스 그대로)
- [~] 잔여 스테일 주석 2건(`dev2/webhook-gateway_2/agents/dev2_adapter.py`, `dev2/tests/test_dev2_adapter.py`의 `# sub2_new` 주석) — 동적 경로 계산이라 **기능 정상**, 주석만 구형. 비운영(gateway/test)이라 보류
- [ ] 잔여 `sub2_new/*`(docs·설계md·.claude 등 ~230파일) 미이전 — 별도 결정 필요(§6)

---

## 6. 남은 일 — sub2_new 잔여 파일

`dev2`만 꺼냈고 `sub2_new`에는 아직 약 230개 파일이 남아 있다:

| 그룹 | 수 | 성격 | 제안 행선지 |
|------|----|------|------------|
| `sub2_new/docs/` | 136 | 설계·학습·런북 문서 | `backend/m2/docs/` 통합 또는 보존 |
| `sub2_new/.claude/` | 53 | Claude 커맨드/에이전트/스킬 | 보존 또는 상위 `.claude`와 정리 |
| `db_schema/`·`googlecloud_schema.sql`·`DB_데이터_요구사항.md` | — | DB 스키마/요구사항 | `backend/m2/docs/` 또는 dev2/migrations 인접 |
| 설계 `.md`(dev2-architecture, 정적분석dev2 등)·PDF 2종 | — | 설계 산출물 | `backend/m2/docs/` |
| `common/`·test 스크립트(run_*.py, *_test.py)·result_*.txt | — | 실행 스크립트/산출물 | dev2 인접 또는 폐기 |
| `CLAUDE.md`(sub2_new PRD) | 1 | PRD 전문 | `backend/m2/docs/` |

> 이들은 코드가 아니라 **참고/설계 자료**라 행선지 판단이 필요하다. 어디로 보낼지(또는 폐기) 정해주면 이어서 옮긴다.

---

## 7. 이전 문서와의 관계

`reports/sub2_new_to_app_pipeline.md`는 **Option B(파일을 app/ 하위로 분산 흡수)** 가정의 개념 매핑이었다.
이번엔 **Option A(패키지 통째 이동)** 를 채택했으므로, 폴더 구조 관점에서는 본 문서가 우선한다.
(단 그 문서의 "노드↔운영 단계 의미 매핑"은 향후 app↔dev2 연결 시 참고 가치가 있어 유지한다.)
