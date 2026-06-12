# TODOS

## KMS 문서 관리 패널 — 역할 기반 탭 노출 제어

**What:** `[기술 정보]` 탭(청크 분석 + 파이프라인)을 개발자 역할에게만 노출하는 기능.

**Why:** 팀장·신입에게 Parent/Child chunk, Token 수, Agent 실행 ms는 의미없는 노이즈다. 기술 탭은 파이프라인 디버깅 용도이므로 개발자에게만 필요하다.

**Pros:**
- 팀장/신입 입장에서 패널이 훨씬 깔끔해짐
- "이게 뭐지?" 혼란 제거
- 탭이 3개 → 2개로 줄어 클릭 대상이 명확해짐

**Cons:**
- KMS_USER_ROLE 스키마 설계 필요 (현재 `team` / `user_id` 만 있음)
- 역할 판정 로직을 프론트에 두면 보안 우회 가능 → API 레벨 판단 또는 JWT claim 추가 필요

**Context:** `[문서 현황] [활용 & 연관] [기술 정보]` 3탭 재설계 후 추가. 현재는 role 무관 3탭 모두 노출. `/plan-design-review` 리뷰에서 도출 (2026-06-12).

**Depends on:** JWT claim에 role 필드 추가 또는 `/auth/me` 응답에 kms_role 포함.

---

## StoredDocsList 페이지네이션 버그

**What:** `StoredDocsList`에서 `stored` + `stored_partial` 두 목록을 같은 `offset/limit`으로 각각 조회한 뒤 클라이언트에서 병합·재정렬한다. 결과적으로 "2페이지" 버튼을 누르면 각 상태의 2페이지가 병합되는 것이지, 전체 통합 목록의 2페이지가 아니다.

**Why 지금은 OK:** 총 문서 수가 적고 사용자가 페이지를 잘 넘기지 않아 체감 버그가 없다. 그러나 문서 현황 탭을 통해 적극적으로 문서를 관리하는 시나리오에서 노출될 수 있다.

**Fix:** 백엔드에서 두 상태를 하나의 쿼리로 통합 (`upload_status IN ('stored', 'stored_partial')`)하거나, 프론트에서 전체 목록을 한 번에 받아 클라이언트 페이지네이션으로 전환.

**Context:** `/plan-eng-review` 외부 검토에서 식별됨 (2026-06-12).
