# SESSION 6 — m3 분석 이슈를 공용 `review_issue` 테이블에 적재 (TDD) (VS Code 복붙용)

> 목적: dev4가 만든 팀 공용 **`review_issue`** 테이블에, m3가 자기 분석 이슈(**test_verification · performance**)를
> 한 행씩 채워 넣는다. → 다른 모듈과 같은 테이블을 공유해 대시보드/프론트가 한곳에서 읽게 된다.
>
> 역할 분담(중요): `review_issue` 16개 컬럼 중 **m3는 "내용 컬럼" 14개만 채운다.**
> **`pull_request_id`·`user_id` 2개는 dev4가 채운다 — m3는 비워둠(NULL).**
> (이 둘은 dev4네 PR/유저 테이블의 내부 번호표라 m3가 모른다. 합의됨.)
>
> 실제로 m3가 **새로 만들 코드는 사실상 `name_of_function` 한 필드뿐**이다. 나머지 값은 m3가 이미 생산 중.

> 선행: 아래 [확인 0]의 dev4 합의 항목 — 특히 **그 4개 컬럼(id/created_at/pull_request_id/user_id)이 NULL 허용 또는 DB 기본값인지** 먼저 확인. (m3가 비우고 INSERT하려면 필수)
> 단, TDD 자체는 로컬 SQLite로 자가검증하므로 **합의 전에도 코드+테스트는 진행 가능**(실 DB 접속은 마지막 배선 단계).

---

```
너는 우리 팀 시니어 백엔드 엔지니어다. 작업 디렉토리: C:\Users\user\Code-Shepherd\backend\m3
반드시 TDD 스킬(레드-그린-리팩터)로 진행한다 — 테스트를 먼저 쓰고, 실패를 본 뒤, 통과시킨다.
기존 패턴을 그대로 따른다: test-performance-agent/contracts.py(Issue), enrich/code_context.py(AST 추출),
persist.py(SQLite + Postgres 두 경로, 정직한 skip). 다른 모듈 담당 파일은 건드리지 않는다.

[배경 — 우리가 채울 테이블]
dev4가 공용 테이블 review_issue 를 만들었다. 컬럼 16개:
  id, pull_request_id, user_id, github_id, agent, severity, keyword, sub_category,
  code_context, code_snippet, suggestion, programming_language, framework,
  framework_version, name_of_function, created_at

m3는 자기 분석 이슈(test_verification · performance)만 이 테이블에 행으로 넣는다.
(static_analysis · security_scan 등 다른 모듈 이슈는 m3가 넣지 않는다.)

[컬럼 매핑 — review_issue ← m3 Issue/AgentOutput]
  id                    → 넣지 않음 (DB 기본값/dev4)         ※ NULL 또는 DB default 필요
  pull_request_id       → 넣지 않음 (dev4가 채움)            ※ NULL 필요
  user_id               → 넣지 않음 (dev4가 채움)            ※ NULL 필요
  github_id             → issue.github_id
  agent                 → output.agent  ("test_verification" | "performance")
  severity              → map(issue.severity): Critical→critical, Major→major, Minor→minor (소문자)
  keyword               → issue.keyword
  sub_category          → issue.sub_category
  code_context          → issue.code_context      (성능 이슈만 채워짐; 없으면 "")
  code_snippet          → issue.code_snippet       (성능 이슈만; 함수 전체 소스, AST=사실)
  suggestion            → issue.suggestion
  programming_language  → issue.programming_language
  framework             → issue.framework
  framework_version     → issue.framework_version
  name_of_function      → issue.name_of_function   ★신규 — 아래 [만들 것 2]
  created_at            → 넣지 않음 (DB now()/기본값)        ※ DB default 필요

중요: 위 풍부한 필드(keyword/code_snippet/name_of_function/framework…)는
run() 이 돌려주는 list[AgentOutput] 의 Issue 객체에만 살아있다.
app/main.py 의 /verify·/analyze 응답(IssueItem)은 필드를 버리므로 거기서 적재하면 안 된다.
→ persist.py 의 persist(scan_id, outputs) 가 받는 그 'outputs'(enrich 끝난 run 결과)를 그대로 쓴다.

[만들 것]
1. contracts.py 의 Issue 에 필드 추가:  name_of_function: str = ""   (기본 빈 문자열, 출력계약 불변)

2. enrich/code_context.py 에서 name_of_function 채우기:
   - 이미 _enclosing_function_source 가 이슈가 가리키는 줄을 감싸는 함수를 AST로 찾는다.
   - 그 함수 노드의 이름(node.name)을 함께 꺼내 issue.name_of_function 에 넣는다.
     (code_snippet 을 채우는 바로 그 지점. 함수 못 찾으면 "" 그대로.)
   - LLM 키와 무관하게 채운다(이름은 사실=AST, 키 없어도 됨). code_snippet 과 같은 조건.

3. persist.py 에 review_issue 적재 함수 추가 — 기존 persist()/persist_pg() 패턴 그대로:
   - SQLite 경로(로컬·테스트용): review_issue 테이블을 CREATE TABLE IF NOT EXISTS 로 보장.
     로컬 테스트 스키마는 id/created_at 에 DB 기본값을 주고, pull_request_id/user_id 는 NULL 허용으로.
       id            TEXT PRIMARY KEY DEFAULT (lower(hex(randomblob(16))))
       created_at    TEXT DEFAULT (datetime('now'))
       pull_request_id TEXT,  user_id TEXT,   (둘 다 NULL 허용)
       나머지 14개 컬럼 텍스트.
   - INSERT 는 위 [컬럼 매핑]대로 14개 내용 컬럼만 넣는다(id/created_at/pull_request_id/user_id 생략).
   - 한 outputs 안의 모든 AgentOutput 의 모든 issue 를 각각 한 행으로.
   - severity 매핑은 작은 dict 로 분리해 dev4 합의 시 한 곳만 고치면 되게 한다.
   - SQL 은 반드시 파라미터 바인딩(%s/?)만. f-string SQL 조합 금지.
   - Postgres 경로(실 dev4 DB): persist_pg 와 같은 형태로 INSERT 작성하되,
     실 접속/배선은 [확인 0] 합의 후 마지막에. (이번 TDD 의 green 기준은 SQLite 경로.)

4. 정직성: DB 미가용·예외 시 적재만 정직하게 skip(예외를 위로 던지지 않음, 로그만).
   가짜 행을 만들지 않는다.

[호출 연결 — 어디서 부르나]
- persist(scan_id, outputs) 가 호출되는 바로 그 지점에서, 같은 outputs 로 새 적재 함수도 호출한다
  (scan_issues 저장 옆에 review_issue 저장을 나란히). 정확한 한 줄 배선 위치가 애매하면 멈추고 물어봐라.

[TDD — 아래가 전부 green 이어야 끝]
- test: Issue 에 name_of_function 필드 존재(기본 "").
- test: enrich 가 함수를 찾으면 issue.name_of_function 에 함수 이름을 채운다(LLM 키 없이도).
        함수 못 찾으면 "" 유지.
- test: severity 매핑 Critical→critical / Major→major / Minor→minor.
- test: 적재 라운드트립 — 풍부한 Issue 가 담긴 outputs 를 넣고 review_issue 에서 다시 읽어
        14개 내용 컬럼이 매핑대로 들어갔는지, 그리고 pull_request_id·user_id 가 NULL,
        id·created_at 이 자동으로 채워졌는지 검증.
- test: DB 실패 시 적재가 예외를 던지지 않고 정직하게 skip.
- 기존 m3 테스트(test-performance 전체) 그대로 green 유지.
- 테스트는 test_review_persist.py 처럼 tempfile SQLite + persist.DB_PATH monkeypatch 로 격리(자격증명 없이 자가검증).

[확인 0 — dev4에게 물어 확정할 것 (코드는 진행하되, 실 DB 배선 전 합의)]
1. review_issue 의 id·created_at·pull_request_id·user_id 가 NULL 허용 또는 DB 기본값인가?
   (아니면 m3가 비우고 INSERT 못 함 → 그때만 pull_request_id/user_id 를 m3가 넘겨받는 방식으로 전환)
2. severity 허용값이 critical/major/minor 인가, 아니면 critical/high/medium/low 인가? (Major 매핑 결정)
3. agent 허용값이 test_verification/performance 그대로인가? (예시엔 code_quality/security_scan)
4. review_issue 행을 m3가 직접 INSERT 하는 게 맞나(공용 DB 쓰기 접속 문자열 필요)?
   — 맞다면 접속 정보(env)를, 아니면 m3 출력을 dev4가 받아 넣는 방식인지 확정.
5. (참고) review_issue 엔 message/file/line 칸이 없어 m3의 '문제 설명·위치'는 저장 안 됨 — 데모상 OK인지.

[지킬 것]
- TDD 먼저. 가짜 데이터 금지. f-string SQL 금지(파라미터 바인딩만).
- 다른 모듈 담당 파일 수정 금지. 출력계약(AgentOutput) 불변.
- 막히면 멈추고 물어봐라. 마지막에 [변경파일 / 테스트결과(통과 수) / 남은 확인사항] 정리.
```

---

## 참고 (사용자용 메모)

- 이게 끝나면 **m3 분석 이슈가 dev4 공용 테이블 `review_issue` 에 그대로 쌓인다.** 같은 표를 다른 모듈/프론트가 함께 읽음.
- m3가 채우는 건 **내용 14칸**. `pull_request_id`·`user_id` 2칸은 **dev4 몫**(네가 신경 안 써도 됨).
- 진짜 새로 만드는 코드는 **함수 이름(`name_of_function`) 하나뿐** — 나머지는 m3가 이미 만들던 값들이라 "옮겨 담기"에 가깝다.
- TDD는 **네 노트북의 임시 SQLite로 혼자 검증**되게 짜놨다(접속 정보·자격증명 없이 돌아감). 실제 dev4 DB에 꽂는 건 [확인 0]을 dev4와 맞춘 뒤 마지막 한 단계.
- dev4한테 물어볼 5가지는 [확인 0]에 정리됨 — 그중 **1번(그 4칸이 비워도 되는지)**이 제일 중요. "안 된다"면 그때만 `pull_request_id`/`user_id`를 m3가 넘겨받는 방식으로 살짝 바꾸면 된다.
