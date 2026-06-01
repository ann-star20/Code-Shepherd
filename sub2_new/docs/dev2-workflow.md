# Dev2 전체 워크플로우

## 단계별 설명

**1. GitHub PR 생성**
사용자가 PR을 올리면 GitHub Webhook이 Dev1으로 전달된다.

**2. Dev1 Orchestrator**
Webhook 서명 검증 후 의도를 분류하고, KMS에서 관련 문서를 검색해 TaskPayload를 만든다. Dev2와 Dev3을 `asyncio.gather`로 동시에 실행한다.

**3. POST /scan (FastAPI)**
Dev2가 요청을 받으면 202를 즉시 반환하고, 실제 분석은 BackgroundTasks로 분리해 비동기 실행한다.

**4. run_tools (노드 1)**
PR diff에서 변경 파일을 추출하고 언어를 감지한다. Pylint / Bandit / ESLint / Semgrep 등 CLI 도구를 언어별로 병렬 실행한다(30초 타임아웃).

**5. vector_search (노드 2)**
탐지된 이슈를 임베딩해 pgVector에서 과거 유사 이슈를 검색한다. 결과가 없으면 빈 리스트로 계속 진행한다.

**6. llm_judge (노드 3)**
이슈 severity에 따라 LLM을 다르게 라우팅한다. Critical은 claude-sonnet-4-6, Major는 claude-haiku-4-5, Minor는 LLM 없이 통과. JSON 파싱 실패 시 1회 재시도 후 원래 severity 유지.

**7. escalate (노드 4, 조건부)**
Critical 이슈가 1건이라도 있으면 Dev4에 즉시 HTTP 알림. 알림 실패해도 파이프라인은 계속된다.

**8. store (노드 5)**
Pydantic으로 AgentOutput을 검증한 뒤 PostgreSQL(운영 조회용)과 BigQuery(분석용)에 저장한다. BigQuery 실패 시 로그만 남기고 스킵.

**9. Dev4 Aggregator**
Dev2와 Dev3 결과를 합쳐 3-Way 판정(lgtm / rework / escalate)을 내린다. GitHub에 코멘트를 달고, Critical이면 Slack에 에스컬레이션한다.

**10. Dev5 / 대시보드**
판정 결과를 바탕으로 개발자 커리큘럼을 갱신하고 React 대시보드에 반영한다.

---

```mermaid
%%{init: {'flowchart': {'rankSpacing': 120, 'nodeSpacing': 25}}}%%
flowchart LR
    GH([GitHub PR 생성])
    GH -->|Webhook| D1

    D1["Dev1 Orchestrator\nWebhook 검증 / 의도 분류 / KMS 검색"]
    D1 -->|asyncio.gather 병렬| DEV2
    D1 -->|asyncio.gather 병렬| D3["Dev3\n테스트 검증 / 성능분석"]

    subgraph DEV2["Dev2 - 정적분석 / 보안스캔 에이전트"]

        SCAN["POST /scan\n202 Accepted 즉시 반환\nBackgroundTasks로 분리"]
        SCAN --> N1

        subgraph LANGGRAPH["LangGraph StateGraph"]
            N1["노드 1: run_tools\nPylint / Radon / Bandit / ESLint\nSemgrep / Roslyn / HTMLHint\nasyncio.gather 30초 타임아웃"]
            N2["노드 2: vector_search\n이슈 임베딩\npgVector 코사인 검색\n과거 유사 이슈 조회"]
            N3["노드 3: llm_judge\nCritical - claude-sonnet-4-6\nMajor - claude-haiku-4-5\nMinor - LLM 생략"]
            COND{Critical >= 1?}
            N4["노드 4: escalate\nDev4 Webhook 즉시 알림\n실패시 로그만 기록"]
            N5["노드 5: store\nPydantic AgentOutput 검증\nPostgreSQL + BigQuery 적재"]

            N1 -->|static_raw / security_raw| N2
            N2 -->|enriched| N3
            N3 --> COND
            COND -->|Yes| N4 --> N5
            COND -->|No| N5
        end

        N5 -.-> INSIGHTS["Insights API\nGET /insights/developer\nGET /insights/team\nGET /insights/trends\nPATCH /issues/dismiss"]
        N5 -.-> DAGS["Airflow DAGs\ndaily_etl / weekly_report"]
    end

    N5 -->|final_output Output Contract| D4
    D3 -->|AgentOutput| D4

    D4["Dev4 Aggregator\n3-Way 판정: lgtm / rework / escalate"]
    D4 -->|GitHub 코멘트| GH
    D4 -->|Critical| SL([Slack 에스컬레이션])
    D4 --> D5["Dev5\n커리큘럼 / 피드백 루프"]
    D5 --> FE([React 대시보드])

    style DEV2 fill:#e8eaf6,stroke:#3949ab,stroke-width:2px
    style LANGGRAPH fill:#f0f4ff,stroke:#4a6fa5
    style N1 fill:#fff8e1,stroke:#f9a825
    style N2 fill:#e8f5e9,stroke:#388e3c
    style N3 fill:#fce4ec,stroke:#c62828
    style N4 fill:#f3e5f5,stroke:#6a1b9a
    style N5 fill:#e3f2fd,stroke:#1565c0

