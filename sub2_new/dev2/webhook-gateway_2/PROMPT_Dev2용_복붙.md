# 🤖 [Dev2용] Claude Code 복붙 프롬프트

> 이 문서를 받은 사람(Dev2 등)이 그대로 따라 하면, 자기 분석 에이전트를
> 공용 게이트웨이에 연결할 수 있습니다.

---

## 📦 1단계: 받아야 할 파일 (이 폴더 통째로)

`webhook-gateway/` 폴더 전체를 받으세요. 핵심은 아래 4개:

```
webhook-gateway/
├── registry.py                       # 플러그인 등록 시스템 (수정 X)
├── gateway.py                        # clone·집계·코멘트 (수정 X)
├── server.py                         # Webhook 수신 서버 (import 1줄만 추가)
├── HANDOFF_Dev2_연동가이드.md         # 상세 가이드
└── agents/
    ├── dev3_adapter.py               # 참고용 (Dev3 예시)
    └── dev2_adapter_TEMPLATE.py      # 이걸 복사해서 채움
```

> 그리고 Dev2 자신의 **분석 코드**(ESLint/Pylint/보안 스캔 모듈)도 준비.

---

## 💬 2단계: Claude Code에 이 프롬프트 그대로 복붙

```
공용 Webhook 게이트웨이(webhook-gateway/)에 내 분석 에이전트를 연결하려고 해.

먼저 다음 파일들을 읽고 구조를 파악해줘:
  - webhook-gateway/HANDOFF_Dev2_연동가이드.md  (연동 방법 설명)
  - webhook-gateway/registry.py                 (등록 규약 + PRContext 정의)
  - webhook-gateway/agents/dev3_adapter.py      (참고 예시)
  - webhook-gateway/agents/dev2_adapter_TEMPLATE.py  (내가 채울 템플릿)

내 분석 에이전트는 [정적분석·보안] 이고, 다음 일을 해:
  [여기에 본인 분석 설명 — 예: "clone된 코드에 Pylint/ESLint 돌리고
   SQL 인젝션·XSS·OWASP Top10 패턴을 탐지한다"]
내 분석 코드는 [경로 또는 모듈명]에 있어.

할 일:
1. dev2_adapter_TEMPLATE.py 를 agents/dev2_adapter.py 로 복사
2. analyze(ctx) 함수 안에 내 실제 분석을 연결:
   - ctx.work_dir = clone된 코드 경로. 여기서 파일 읽어서 분석
   - 찾은 이슈를 표준 dict 형식으로 반환:
     {"severity": "Critical|Major|Minor", "file": "...", "line": int,
      "message": "...", "rule_id": "SEC-xxx 또는 SA-xxx",
      "suggestion": "...", "_agent": "security_scan"}
   - severity 기준: SQL인젝션·인증우회 등 즉시위험=Critical,
     중요하지만 즉시사고 아님=Major, 권장사항=Minor
3. server.py 에 "import agents.dev2_adapter" 한 줄 추가
4. 등록 확인:
   py -c "import agents.dev2_adapter; from registry import registered_agents; print([a.name for a in registered_agents()])"
   → 내 에이전트 이름이 목록에 나오면 성공

★ 중요: registry.py / gateway.py / server.py 의 기존 로직은 건드리지 마.
  (server.py는 import 한 줄 추가만)
★ TDD로: 내 analyze() 함수에 대한 단위 테스트(가짜 ctx로 이슈 반환 검증)도 같이 만들어줘.
```

---

## ✅ 3단계: 연결 후 동작 방식 (자동)

Dev2 어댑터가 등록되면, 신입 PR이 올 때:
```
PR 수신 → clone → [Dev3 분석 + Dev2 분석 동시 실행]
  → 이슈 전부 합침 → 중복 제거 → 판정 → Gemini 코멘트 → GitHub 등록
```
→ Dev2는 **자기 analyze() 함수만** 책임지면 됨. 나머지는 게이트웨이가 처리.

---

## 📋 체크리스트 (Dev2가 다 됐는지 확인)

- [ ] `agents/dev2_adapter.py` 만듦
- [ ] `analyze(ctx)` 가 `list[dict]` 반환 (표준 형식)
- [ ] `@register("security_scan")` 데코레이터 붙임
- [ ] `server.py` 에 `import agents.dev2_adapter` 추가
- [ ] 등록 확인 명령에서 내 에이전트 이름 나옴
- [ ] analyze() 단위 테스트 통과

---

## ⚠️ 자주 막히는 곳

| 문제 | 해결 |
|---|---|
| import 에러 (내 분석 모듈) | 어댑터 안에서 sys.path 추가 (dev3_adapter.py 참고) |
| 동명 모듈 충돌 (contracts 등) | dev3_adapter.py의 sys.modules 정리 패턴 참고 |
| 이슈가 코멘트에 안 나옴 | dict 키 이름 정확한지 확인 (severity/file/line/message/rule_id) |

---

*제공: Dev3 / 게이트웨이 문의: Dev3*
