# 📨 [Dev2 전달용] Webhook 게이트웨이 연동 가이드

> **From**: Dev3 / **To**: Dev2 (정적분석·보안)
> **요약**: 신입이 PR을 올리면 자동으로 분석·코멘트하는 공용 게이트웨이를 만들어뒀어요.
>          Dev2는 **어댑터 파일 1개 + import 1줄**만 추가하면 자동으로 끼어듭니다.

---

## 1. 이게 뭐냐 (30초)

```
신입 PR 올림 → GitHub Webhook → 게이트웨이(server.py)
  → 등록된 분석 에이전트 전부 자동 호출
       ├─ test_verification_and_performance (Dev3, 이미 등록됨)
       └─ security_scan / static_analysis (Dev2, 여기에 추가하면 됨)  ← 당신
  → 결과 합쳐서 집계·판정·코멘트 → GitHub PR에 자동 등록
```

→ 게이트웨이가 **clone·diff·코멘트 등록**을 다 해줘요. Dev2는 **"코드 받아서 이슈 찾는 함수"만** 만들면 됩니다.

---

## 2. 할 일 — 딱 3단계

### 1단계: 템플릿 복사
```
agents/dev2_adapter_TEMPLATE.py  →  agents/dev2_adapter.py 로 복사
```

### 2단계: 분석 로직 채우기
`dev2_adapter.py`의 `analyze()` 함수 안 TODO 부분을 Dev2 실제 분석으로 교체.
- `ctx.work_dir` = clone된 코드의 로컬 경로 (여기 파일 읽어서 ESLint/Pylint/보안 검사)
- 찾은 이슈를 아래 형식 dict로 반환

### 3단계: server.py에 한 줄 추가
```python
# server.py 상단, 기존 import 아래에:
import agents.dev2_adapter      # 🟢 이 한 줄
```
→ 끝. PR 오면 Dev2 분석도 자동으로 같이 돌아갑니다.

---

## 3. 반환 형식 (표준 Issue — 이것만 지키면 됨)

```python
{
    "severity": "Critical",          # "Critical" | "Major" | "Minor"
    "file": "src/auth.py",           # 파일 경로 (ctx.work_dir 기준 상대경로)
    "line": 23,                      # 줄 번호 (없으면 None)
    "message": "SQL 인젝션 가능성: 사용자 입력이 쿼리에 직접 삽입됨",
    "rule_id": "SEC-001",            # 보안=SEC-xxx, 정적분석=SA-xxx
    "suggestion": "파라미터 바인딩을 사용하세요",
    "_agent": "security_scan",       # @register 이름과 동일
}
```

→ 이 dict 목록(`list[dict]`)을 반환하면, 게이트웨이가 알아서:
- Dev3 결과랑 합치고
- 중복 제거하고
- 판정(Critical 1개→escalate / Major 3개→rework / 그외 lgtm)하고
- Gemini로 신입 맞춤 코멘트 만들어서
- GitHub PR에 등록합니다.

---

## 4. severity 기준 (Dev4 판정과 직결 — 합의값)

| severity | 언제 | 판정 영향 |
|---|---|---|
| **Critical** | SQL인젝션·인증우회 등 즉시 위험 | 1개라도 → escalate(긴급) |
| **Major** | 중요하지만 즉시 사고는 아님 | 3개 이상 → rework |
| **Minor** | 권장·개선 사항 | 다수여도 통과 가능 |

→ 보안은 Critical이 많을 거예요. **`Critical` 하나면 PR이 자동으로 "긴급(escalate)" 판정**됩니다.

---

## 5. 테스트 방법

어댑터 만들고 등록되는지 확인:
```powershell
cd webhook-gateway
py -c "import agents.dev2_adapter; from registry import registered_agents; print([a.name for a in registered_agents()])"
# → ['test_verification_and_performance', 'security_scan'] 나오면 성공
```

서버 켜고 가짜 PR로 전체 테스트:
```powershell
py server.py     # 다른 터미널에서
# → /health 열어보면 등록된 에이전트 목록 확인 가능
```

---

## 6. 참고 — Dev3 어댑터 예시

`agents/dev3_adapter.py` 를 보면 실제로 어떻게 만들었는지 참고 가능.
(Dev3는 clone된 코드를 Docker에서 pytest 돌려 분석하지만, Dev2는 ESLint/Pylint 정적 실행이라 더 간단할 거예요.)

---

## 7. 정리

```
복사:   dev2_adapter_TEMPLATE.py → dev2_adapter.py
채우기: analyze() 안에 Dev2 분석 + 이슈 dict 반환
등록:   server.py 에 import agents.dev2_adapter 한 줄
→ 끝. 게이트웨이가 나머지(clone·합치기·판정·코멘트·등록) 전부 처리.
```

문의: Dev3
