# corpus/ — 미니 KMS 컨벤션 코퍼스 (세션 C 작성, 정현 현실성 검수)

마크다운 규칙 문서 5~8개. **일반 모범사례 금지** — 가상의 사내 사고 이력이 동기인
"우리 회사 특수 규칙"으로 쓴다. 세계 표준과 일부러 어긋나도 된다 (그게 차별점 시연의 핵심:
"일반 코드리뷰 AI는 세상 기준, 이 에이전트는 우리 회사 기준").

## 문서 템플릿 (팀 KMS 포맷 합의안 — 브리프 §1.3)

```markdown
# [rule_id] 규칙 제목
- severity: Major | Minor | Info
- 배경(사고 이력): YYYY-MM 어떤 사고로 이 규칙이 생겼는지 1~3문장

## §1 규칙
(조항 본문 — judge가 인용할 문장이므로 명확한 단정문으로)

## §2 올바른 예시
```python ...```

## §3 잘못된 예시
```python ...```

## §4 예외 조항
(없으면 "예외 없음". 있으면 적용 제외 경로/상황을 명시 — 오탐 회피 장면의 근거)
```

## 작성 규칙

- 청크는 §단위로 잘린다 (ingestion). 한 §에 한 가지 주장만.
- rule_id 는 `CONV-<도메인>-NNN` (예: CONV-API-001). 골든셋 label.yaml 이 이 id를 참조한다.
- **장면 매핑 필수**: 장면1·4용 규칙(async 내 동기 HTTP 금지 → httpx 강제)은 핫스왑 때
  본문 "httpx → aiohttp" 한 줄만 바꿔 판정이 뒤집히도록 문장을 설계할 것.
- 장면2용 규칙에는 §4 예외 조항(scripts/ 등 배치 경로 적용 제외)이 반드시 있어야 한다.
- 장면3(지침공백)용으로, 어떤 규칙에도 안 걸리는 패턴 영역을 일부러 비워 둔다.

후보 규칙 8개 초안과 가상 사고 이력은 docs/PRD.md §6 표 참조.

## 확정 코퍼스 — 시연 장면 매핑표 (D1 세션 C, 정현 검수 반영: 8종 전부 채택)

| rule_id | 파일 | severity | 장면 | 검수 반영 메모 |
|---|---|---|---|---|
| CONV-API-001 | external_api.md | Major | 1·2·4 | §1 마지막 줄이 핫스왑 대상 한 줄 (`httpx.AsyncClient` → `aiohttp.ClientSession`) |
| CONV-TIME-002 | time_handling.md | Major | 백업 위반 | — |
| CONV-LOG-003 | logging.md | Major | 백업 위반 | — |
| CONV-DB-004 | db_query.md | Major | AST stretch 연계 | 교정 지시를 사내 API 로: `repo.bulk_fetch()` (정현 검수). 위반 정의는 유지 |
| CONV-DEP-005 | js_deps.md | Minor | 코퍼스 현실감 | §1 에 JS/TS 한정 명시 — 파이썬 PR 이 인용하면 환각 (하네스 체크 대상) |
| CONV-ERR-006 | error_handling.md | Major | 백업 위반 | 기존 `errors.report` 그대로 |
| CONV-CFG-007 | config_env.md | Minor | 정상 변형 (pr_010) | — |
| CONV-SQL-008 | sql_binding.md | Major | 위반 변형 (pr_005) | 교정 지시를 사내 API 로: `db.safe_query()` (정현 검수). 위반 정의는 유지 |

- **의도된 지침공백 영역 (장면 3)**: subprocess/외부 명령 실행, 난수·토큰 생성. 이 영역의 규칙을
  나중에 추가하면 golden pr_011·pr_012 의 gap 라벨이 깨진다 — 골든셋과 연동(게이트 1).
- 핫스왑 시연(장면 4) 절차: external_api.md §1 마지막 줄의 `httpx.AsyncClient` 를
  `aiohttp.ClientSession` 으로 수정 → `make reindex` → pr_008 재실행 → 정상→위반으로 뒤집힘.
