# Frontend Integration Spec — dev3 http_adapter

> 작성: D4 (2026-06-12). 1단계 읽기 전용 분석 결과.

## m1 → m3 호출 계약 (정본)

**파일**: `Code-Shepherd/backend/m1/app/clients/module_clients.py`

| 항목 | 값 |
|---|---|
| URL | `POST http://m3:8004/review` (env: `M3_URL=http://m3:8004`) |
| 인증 | 없음 (Docker 내부망) |
| Timeout | 60초 |

### Request — M3ReviewRequest
```json
{
  "task_id": "uuid-string",
  "pr_id": "string",
  "repository": "owner/repo",
  "pr_number": 123,
  "static_analysis": null,
  "security_scan": null,
  "test_verification": null,
  "performance": null,
  "developer": {"id": "string", "skill_level": "junior"},
  "trace_id": null
}
```

### Response — M3ReviewResponse
```json
{
  "task_id": "string",
  "pr_id": "string",
  "verdict": "lgtm|rework|escalate",
  "comment_posted": true,
  "comment_url": "https://github.com/.../...",
  "persisted": true
}
```

## Frontend → m3 조회 계약 (GET)

**파일**: `Code-Shepherd/frontend/src/lib/api.ts` (`m3Client`)  
**BaseURL**: `VITE_M3_API_URL` (기본: `/m3-api` → `http://m3:8004`)

```
GET /review/{owner}/{repo}/{pr_number}
```

**Response** (ReviewPage.tsx가 렌더하는 형식):
```json
{
  "found": true,
  "verdict": "lgtm|rework|escalate|null",
  "verdict_reason": "Major 2건 ≥ 기준 2건 → 수정 요청",
  "comment": "## 🔍 코드리뷰 에이전트 결과\n...",
  "issues": [
    {
      "severity": "Major",
      "file": "src/api.py",
      "line": 42,
      "message": "...",
      "rule_id": "CONV-API-001",
      "suggestion": "...",
      "rag_context": "...",
      "source_url": "corpus/conv_api.md"
    }
  ],
  "rich_issues": [
    {
      "agent": "dev3",
      "severity": "Major",
      "keyword": "동기 HTTP 호출",
      "sub_category": "CONV-API-001",
      "code_context": "+    response = requests.get(url)",
      "code_snippet": "async def fetch_data():\n    ...",
      "suggestion": "httpx.AsyncClient 로 교체",
      "name_of_function": "fetch_data",
      "programming_language": "python",
      "framework": null
    }
  ]
}
```

## 프론트 렌더 컴포넌트 매핑

| dev3 출력 필드 | 프론트 data-testid | 렌더 내용 |
|---|---|---|
| verdict | `review-verdict` | VerdictBadge (LGTM/REWORK/ESCALATE) |
| comment_md | `review-comment` | 마크다운 코멘트 전문 |
| issues[i] | `issue-row-{i}` | severity·file·line·message·rule_id |
| issues[i].rag_context | `issue-rag-{i}` | 사내 규칙 인용 |
| rich_issues[i] | `review-rich-{i}` | 함수명·키워드·코드 스니펫 |
| verdict_reason | `review-verdict-reason` | 판정 근거 한 줄 |

## dev3 verdict 매핑

| dev3 ReviewOutput | m3 verdict |
|---|---|
| findings 중 violation 있음 | `rework` |
| gap_report 있음 (지침공백) | `escalate` |
| findings 비어있음 | `lgtm` |

## 전제 조건 요약

- **인증**: m1→m3 경로는 인증 없음. 프론트→m3 직접 호출은 JWT 선택적.
- **WebSocket**: 없음. 전부 HTTP 요청/응답.
- **diff 소스**: M3ReviewRequest에 diff 없음 → GitHub API로 직접 fetch (`GITHUB_TOKEN` 필요).
- **포트**: 8004 (기존 m3 포트 승계).
- **CORS**: `localhost:5173` 허용 (프론트 Vite dev server).

## 기존 m3 service와의 drop-in 관계

`src/adapters/http_adapter.py`가 기존 `Code-Shepherd/backend/m3/app/main.py`의 drop-in.
- 같은 엔드포인트 2개: `POST /review`, `GET /review/{owner}/{repo}/{pr_number}`
- 같은 포트: 8004
- 입출력 스키마 동일 (M3ReviewRequest / M3ReviewResponse)
- 내부 구현만 dev3 파이프라인으로 교체
