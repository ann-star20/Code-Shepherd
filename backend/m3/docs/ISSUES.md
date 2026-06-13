# ISSUES.md — 지금 처리할 것

> 앞으로의 기능 계획은 ROADMAP.md, 시연 준비는 REHEARSAL.md.
> 이 문서는 "지금 고쳐야/처리해야 하는 것"만 담는다.

---

## 🔴 긴급 — 시연 전 수정

### ISSUE-1. 코멘트 중복 출력
**증상:** PR 하나에서 같은 규칙(CONV-SQL-008)이 두 개의 코멘트로 따로 나옴. `get_user`와 `get_orders` 두 함수가 같은 규칙 위반인데 각각 별도 블록으로 출력됨.

**기대 동작 (둘 중 택1 — 결정 필요):**
- (A) 같은 rule_id는 하나의 코멘트로 묶고, 위반 위치(함수·라인)를 목록으로 나열
- (B) 위반 함수별로 따로 두되, 코멘트가 완전히 중복되지 않게 (함수명·라인만 다르게)

**추천:** A — 규칙 1개당 코멘트 1개 + "위반 위치: get_user(L5), get_orders(L10)" 식. 리뷰가 깔끔해지고 중복 인상 제거.

**수정 위치:** `src/nodes/compose_comment.py` (findings를 rule_id로 group by)

**✅ 해결:** 추천안 A로 구현. `_compose_findings`가 violation을 rule_id로 group by → 규칙당 코멘트 1개 + `위반 위치: get_user, get_orders` 나열(`_extract_location`이 evidence_lines에서 함수명 추출). 라이브 서버 반영 확인.

---

### ISSUE-2. 출처 링크 깨짐
**증상:** 코멘트의 출처 링크가
`https://github.com/kskt1234-netizen/-dev3-demo/pull/corpus/sql_binding.md`
로 나오는데, 이 경로는 실제로 존재하지 않음 (PR 경로에 corpus를 붙인 잘못된 조합).

**기대 동작:** 실제 corpus 파일을 가리키거나, 링크가 불가능하면 파일명만 텍스트로 표기 (예: "출처: corpus/sql_binding.md §1").

**수정 위치:** `src/nodes/compose_comment.py` 의 출처 URL 생성 로직

**✅ 해결:** `([출처](corpus/...))` 마크다운 링크 → `(출처: corpus/sql_binding.md)` 텍스트로 교체. GitHub가 상대경로를 PR URL로 오해해 깨진 링크를 만들던 문제 제거.

---

## 🟡 팀 공지 필요 (우리 수정 범위 밖)

### ISSUE-3. m1 이벤트 필터 없음
**증상:** m1 `triggers.py`에 이벤트 필터가 없어 closed·reopened PR에도 전체 m2→m3 파이프라인이 실행됨. 우리 m3(webhook_adapter)는 이미 opened·synchronize만 처리하도록 수정됨(67bc24d5 이전 커밋)이나, m1이 m3를 호출하기 전 단계라 무의미.

**조치:** 팀 슬랙 공지 — "m1 triggers.py가 opened·synchronize만 트리거하도록 필터 필요." m1은 팀 모듈이므로 직접 수정 금지.

---

## ✅ 수정 완료 (기록용)

### ChromaDB stale UUID 캐시 (67bc24d5)
reindex가 collection을 삭제+재생성하면서 UUID가 바뀌는데, retrieve.py 전역 캐시가 옛 UUID를 참조해 500 NotFoundError. → count() liveness probe로 stale 캐시 자동 무효화. 20/20 테스트 통과.

### ⭐ m3 컨테이너가 stale 이미지 코드 실행 (시연 4장면 500의 진짜 원인)
**증상:** 67bc24d5(위 ChromaDB fix)를 src에 커밋했는데도, 리허설 4장면에서 corpus 스왑→reindex→reopen 시 m3 `/review`가 여전히 500(`NotFoundError: Collection [...] does not exist`)·m1은 502. fix가 적용 안 된 것처럼 동작.

**원인:** `docker-compose.override.yml`이 m3를 `dev3-m3:latest` **이미지 베이크본 `/app/src`**로 실행하도록 설계됨(`uvicorn src.adapters.http_adapter:app`, WORKDIR `/app`). 마운트본 `/app/service/src`(=호스트 backend/m3/src, fix 포함)는 서버가 import하지 않음 → **src를 고쳐도 이미지 재빌드 전까지 서버에 반영되지 않음.** 67bc24d5도 compose_comment ISSUE-1/2 fix도 전부 미반영 상태였다. (eval은 `cd service && python -m eval.harness`로 마운트본을 직접 실행해 통과했으므로 이 괴리를 못 잡음.)

**해결:** override의 m3 volumes에 `./backend/m3/src:/app/src` 라이브 마운트 추가 → 서버가 호스트 src를 직접 실행. 이제 src 변경이 `docker compose up -d m3` 재시작만으로 반영(재빌드 불필요). 검증: reindex→트리거→reindex(캐시 stale화)→트리거 = **둘 다 HTTP 200**(과거 두 번째에서 500).

---

## v1 잔여 작업 (기능 아님 — 마무리)

- [x] ISSUE-1, ISSUE-2 수정 (라이브 서버 반영 확인)
- [x] m3 stale 이미지 코드 → src 라이브 마운트로 해결 (4장면 500 원인)
- [ ] 리허설 4장면 2회 통과 (REHEARSAL.md 참조)
- [ ] `git push origin feat/m3-dev3-integration`
- [ ] ISSUE-3 팀 공지

> 로딩 스피너·실시간 trace 등 "기능 추가"는 v1 잔여가 아니라 ROADMAP.md v2.
