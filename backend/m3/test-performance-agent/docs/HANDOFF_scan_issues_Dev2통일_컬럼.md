# 📦 핸드오프 — scan_issues 컬럼 Dev2와 통일 (GCP 변경은 팀 합의 후)

> Dev2와 **같은 `scan_issues` 테이블**을 쓰기 위해 컬럼 구조를 통일.
> **Dev3 코드 + 로컬 SQLite + 테스트는 완료**(아래 §1). 작성일 2026-06-04, 브랜치 `test-performance-agent`.
> ⚠️ **GCP 공유 DB 변경(ADD/DROP)은 운영 장애·Dev2 영향을 막기 위해 팀 합의 후 "한 번에" 적용.**
> 지금 gateway 라이브 INSERT는 **바꾸지 않았음** — GCP 표에 새 컬럼이 없는 상태에서 INSERT를 먼저 바꾸면 PR 분석 저장이 통째로 실패하기 때문.

---

## 0. 무엇을 / 왜

Dev2와 컬럼을 맞춰 공유 테이블을 함께 사용.

### ➕ 추가 5컬럼
| 컬럼 | 의미 | 채우는 곳 (사실/LLM) |
|---|---|---|
| `github_id` | PR 작성자 GitHub 아이디(문자) | `main.run` → `developer.id`. 모든 이슈 |
| `code_snippet` | **문제 함수 전체 소스** | `enrich/code_context.py` AST 추출 (LLM 아님=사실). **PERF 이슈만**. 키 없어도 채워짐 |
| `programming_language` | `python` 등 | `enrich/framework.py` requirements 감지. 모든 이슈 |
| `framework` | `django`/`fastapi`/`flask` | `enrich/framework.py` requirements 파싱. 모든 이슈 |
| `framework_version` | 프레임워크 핀 버전 (예 `4.2.1`) | 동상. 핀 없으면 빈 값 |

### ➖ 삭제 2컬럼 (코드에서만 제거됨)
| 컬럼 | 처리 |
|---|---|
| `sub_keyword` | Issue 모델·탐지기·로컬 SQLite·어댑터에서 제거. **GCP 컬럼은 아직 DROP 안 함**(§3) |
| `metric_value` | 동상 |

> `code_context`(함수 한 줄 LLM 설명)·`code_snippet`(함수 전체 소스)는 **둘 다 성능(PERF) 이슈에만** 채움 (Dev4가 성능 분석에만 사용). `keyword`·`sub_category`는 유지.

---

## 1. ✅ 이미 완료 (Dev3 소유, 코드·로컬·테스트)

- `contracts.py` `Issue`: 5컬럼 추가(기본 빈 문자열) + `sub_keyword`·`metric_value` 제거.
- 탐지기 6개에서 `sub_keyword=`·`metric_value=` 제거.
- `enrich/code_context.py`: `code_snippet`(AST, 키 없이도) + `code_context`(LLM, 키 있을 때) 채움. `main.py`에서 **PERF 이슈만** enrich.
- `enrich/framework.py` 신규: requirements.txt(없으면 pyproject.toml) 파싱 → language/framework/version, 모든 이슈에 채움.
- `main.py`: `github_id`(developer.id) 모든 이슈에 채움.
- 로컬 SQLite(`persist.py`) 스키마·INSERT 반영(5컬럼 추가, 2컬럼 제거) + 라운드트립 테스트.
- `webhook-gateway/agents/dev3_adapter.py` dict: 삭제 2키 제거 + 신규 5키 추가(gateway INSERT 연결은 §2에서 GCP ALTER 후).
- 테스트: `test_framework.py`(9)·`test_github_id.py`(2)·`test_code_context.py`(+2)·`test_task1_contracts.py`(+1)·persist(+1) — **test-performance 215 PASS, webhook-gateway·pr-comment 그대로 PASS**.

---

## 2. ⏳ 미적용 — GCP 공유 DB **추가**(ADD) + gateway 연결 (팀 합의 후, 순서 엄수)

### (A) GCP Postgres — scan_issues 컬럼 추가 (안전: ADD IF NOT EXISTS, DEFAULT '')
```sql
ALTER TABLE scan_issues
  ADD COLUMN IF NOT EXISTS github_id            text DEFAULT '',
  ADD COLUMN IF NOT EXISTS code_snippet         text DEFAULT '',
  ADD COLUMN IF NOT EXISTS programming_language text DEFAULT '',
  ADD COLUMN IF NOT EXISTS framework            text DEFAULT '',
  ADD COLUMN IF NOT EXISTS framework_version    text DEFAULT '';
```

### (B) `webhook-gateway/gateway.py` `_persist_to_db` — scan_issues INSERT에 5컬럼 추가
> ⚠️ (A) ALTER를 **먼저** 실행한 뒤에만 배포. 어댑터 dict엔 이미 5키가 들어오므로 `i.get(...)`로 받으면 됨.
```python
INSERT INTO scan_issues
  (scan_id, agent, severity, rule_id, file, line, message, suggestion,
   keyword, sub_category, code_context,
   github_id, code_snippet, programming_language, framework, framework_version)
VALUES (%s, ... 16개 ...)
# 값: ..., i.get("github_id",""), i.get("code_snippet",""),
#     i.get("programming_language",""), i.get("framework",""), i.get("framework_version","")
```
> 현재 gateway INSERT는 13컬럼(keyword·sub_keyword·metric_value·sub_category·code_context 포함) 그대로 둠.
> 새 5컬럼을 넣을 때, 삭제 예정인 `sub_keyword`·`metric_value`는 §3 DROP 시점에 같이 빼는 것을 권장(한 PR로).

> ⚠️ `persist.py`의 `persist_pg()`(GCP 경로)는 이 컬럼들을 **아직 INSERT하지 않음**(로컬 `persist()`만). 실제 GCP 적재는 gateway 경로가 담당. persist_pg도 쓰려면 함께 갱신.

---

## 3. ⚠️ 미적용 — GCP 컬럼 **삭제**(DROP), 가장 신중하게

`sub_keyword`·`metric_value`는 **코드에서만** 제거했고 GCP 컬럼은 그대로 둠.
**Dev2·Dev4가 이 두 컬럼을 더 이상 안 읽는다고 확인된 뒤에만** 아래를 별도 실행:

```sql
-- 사전 확인: 두 컬럼을 읽는 코드/대시보드/쿼리가 없는지 팀 합의
ALTER TABLE scan_issues DROP COLUMN IF EXISTS sub_keyword;
ALTER TABLE scan_issues DROP COLUMN IF EXISTS metric_value;
```
> DROP 전까지: GCP 컬럼이 남아 있어도 무해. gateway가 `i.get("sub_keyword","")`로 빈 문자열을 넣으므로(어댑터가 더 이상 값을 안 보냄) 기존 INSERT는 계속 성공. DROP은 **되돌리기 어렵다** → 반드시 합의 후.

---

## 4. 적용 순서 요약 (운영 안전)
1. (A) `ALTER ... ADD COLUMN IF NOT EXISTS` 5개 실행·커밋.
2. (B) gateway INSERT 16컬럼으로 배포 (어댑터는 이미 5키 전달 중).
3. 동작 검증(롤백 트랜잭션으로 INSERT→SELECT).
4. Dev2/Dev4 미사용 확인 후, 별도로 (§3) `DROP sub_keyword, metric_value` — 한 번에.

## 5. Dev2에게 공유할 메시지 (제안)
> "scan_issues를 함께 쓰기 위해 컬럼을 맞췄습니다. 추가: `github_id`(작성자 아이디)·`code_snippet`(문제 함수 전체 소스, 성능 이슈만)·`programming_language`·`framework`·`framework_version`. 제거 예정: `sub_keyword`·`metric_value`(저희 코드에선 이미 안 씀 — 두 분이 안 읽으시면 DROP 합의 부탁). ADD는 `IF NOT EXISTS`라 안전하고, gateway INSERT 연결은 ADD 실행 직후 배포합니다."
