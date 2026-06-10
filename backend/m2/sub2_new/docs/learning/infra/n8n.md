# n8n 학습 노트

**날짜**: 2026-05-22
**복습 예정**: D+1, D+3, D+7

---

## 한 줄 요약
코드 없이 여러 서비스를 연결하는 자동화 도구 — "GitHub에서 PR이 열리면 자동으로 스캔해줘"를 GUI로 만든다.

---

## 1. 비유

**n8n 없이:**
```
개발자가 PR 올림 → 누군가 수동으로 스캔 API 호출 → 결과 확인
```

**n8n 있이:**
```
개발자가 PR 올림 → GitHub Webhook → n8n이 자동으로 POST /scan 호출
```

n8n = 서비스들 사이의 자동 배달부.

---

## 2. 개념

> **n8n**: 노드(Node) 기반 워크플로우 자동화 도구.
> 각 노드가 "작업 하나"를 담당하고, 노드를 연결해 흐름을 만든다.

**핵심 용어:**

| 용어 | 설명 | 예시 |
|------|------|------|
| Workflow | 전체 자동화 흐름 | GitHub PR → Dev2 스캔 |
| Node | 흐름 안의 개별 작업 | Webhook 수신, HTTP 요청 |
| Trigger | 워크플로우를 시작하는 노드 | GitHub Webhook |
| HTTP Request | 외부 API 호출 노드 | POST /scan |

---

## 3. 왜 쓰나

- **없으면**: GitHub PR 감지 → Dev2 호출을 코드로 직접 구현해야 함 (GitHub App 등록, 서버 필요)
- **있으면**: n8n GUI에서 노드 연결만 하면 완성. 코드 불필요.

Dev 2에서: `GitHub Webhook 수신 → payload 가공 → POST /scan 호출`

---

## 4. 코드 (Dev 2)

**n8n 워크플로우 JSON (Export 형식):**

```json
{
  "nodes": [
    {
      "name": "GitHub Webhook",
      "type": "n8n-nodes-base.webhook",
      "parameters": {
        "path": "github-pr",
        "httpMethod": "POST"
      }
    },
    {
      "name": "PR 이벤트 필터",
      "type": "n8n-nodes-base.if",
      "parameters": {
        "conditions": {
          "string": [{ "value1": "={{$json.action}}", "value2": "opened" }]
        }
      }
    },
    {
      "name": "Dev2 스캔 요청",
      "type": "n8n-nodes-base.httpRequest",
      "parameters": {
        "url": "http://dev2:8002/scan",
        "method": "POST",
        "body": {
          "task_id": "={{$uuid}}",
          "pr_id": "={{$json.pull_request.number}}",
          "pr_diff": "={{$json.pull_request.diff_url}}"
        }
      }
    }
  ],
  "connections": {
    "GitHub Webhook": { "main": [[ {"node": "PR 이벤트 필터"} ]] },
    "PR 이벤트 필터": { "main": [[ {"node": "Dev2 스캔 요청"} ]] }
  }
}
```

**흐름 요약:**
```
GitHub PR 오픈
    → n8n Webhook 수신
    → action == "opened" 인지 확인 (필터)
    → POST http://dev2:8002/scan { task_id, pr_id, pr_diff }
```

---

## 복습 퀴즈

1. Q: n8n의 Trigger 노드 역할은?
   A: (워크플로우를 시작하는 노드. GitHub Webhook처럼 외부 이벤트를 수신)

2. Q: Dev 2에서 n8n을 쓰는 이유는?
   A: (GitHub PR 오픈 이벤트를 코드 없이 감지해서 POST /scan을 자동 호출하기 위해)

3. Q: n8n과 직접 코드 구현의 차이는?
   A: (n8n은 GUI로 노드 연결만 하면 됨. 직접 구현하면 GitHub App 등록 + 서버 코드 필요)
