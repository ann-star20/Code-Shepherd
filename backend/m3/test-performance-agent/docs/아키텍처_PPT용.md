# 🏗️ Dev3 아키텍처 다이어그램 (PPT용)

> Mermaid 다이어그램 모음. VS Code 미리보기(Ctrl+Shift+V)로 보고 **캡처해서 PPT에 붙이세요.**
> 레벨별로 정리 — 청중·시간에 맞게 골라 쓰면 됩니다.

---

## 🎯 다이어그램 0. 상세 전체 흐름 — 검출 → 코멘트 (메인 ⭐⭐)

> **언제 쓰나**: 가장 핵심 슬라이드. "검출부터 코멘트까지 어떻게 흐르나" 전 과정.

```mermaid
flowchart TD
    A["📥 PR 수신: pr_diff · repo · scan_id"] --> B["① shallow clone + checkout(commit_sha)"]
    B --> C["② Docker 샌드박스: pytest --cov 실측"]
    C --> D["커버리지 측정 → TEST-001 + metrics(line/branch/func)"]
    C --> E["③ AST 병렬 탐지 (asyncio.gather · 부분 실패 허용)"]
    E --> E1["테스트 누락 함수 · TEST-004"]
    E --> E2["N+1 쿼리 · PERF-002 (Major)"]
    E --> E3["시간복잡도 O(n^k) · PERF-001"]
    E --> E4["엣지케이스/메모리누수 · TEST-003/PERF-003 (LLM)"]
    D --> F["④ diff 교집합 필터: 신입이 바꾼 함수 범위만"]
    E1 --> F
    E2 --> F
    E3 --> F
    E4 --> F
    F --> G["⑤ 조립: AgentOutput 2개(test_verification · performance) + summary"]
    G --> H["⑥ 저장: scan_issues · scan_summaries · agent_traces (scan_id 공유)"]

    G --> J["⑦ 집계: M2(보안)+M3 이슈 합치고 중복 제거"]
    J --> K{"⑧ 판정 규칙"}
    K -->|"Critical ≥ 1"| K1["🔴 escalate (긴급)"]
    K -->|"Major ≥ 3"| K2["🟠 rework (재작업)"]
    K -->|"그 외"| K3["🟢 lgtm (통과)"]
    K1 --> L["⑨ LLM 코멘트 생성 (Gemini · 신입 수준 맞춤)"]
    K2 --> L
    K3 --> L
    L --> M["⑩ GitHub PR 코멘트 등록"]
    K1 -.-> N["📢 Slack 긴급 알림"]

    style C fill:#fde,stroke:#933
    style F fill:#efd,stroke:#393
    style J fill:#eef,stroke:#369
    style L fill:#eef,stroke:#369
    style M fill:#dfd,stroke:#393
```

🎙️ **말하기 (한 흐름으로)**:
"신입 PR이 들어오면 — ① 코드를 통째로 받아서 ② Docker에서 진짜 테스트를 돌려 커버리지를 재고 ③ 동시에 6개 탐지기로 N+1·복잡도 등을 찾아요. ④ 그중 신입이 바꾼 부분만 걸러서 ⑤ 표준 데이터로 조립하고 ⑥ DB에 저장합니다. 여기까지가 **검출**(test-performance-agent)이에요.
그 다음 ⑦ 보안 결과까지 합쳐서 ⑧ 통과·재작업·긴급을 자동 판정하고 ⑨ Gemini로 신입 수준에 맞춘 코멘트를 만들어 ⑩ GitHub에 등록합니다. 긴급이면 Slack 알림도 가고요. 이게 **코멘트**(pr-comment-agent) 단계입니다."

> **두 모듈 경계**: ①~⑥ = `test-performance-agent` (검출·저장) / ⑦~⑩ = `pr-comment-agent` (집계·코멘트). 둘 다 내 파트.

---

## 🎯 다이어그램 1. 전체 시스템 한눈에 (가장 큰 그림)

> **언제 쓰나**: 오프닝. "전체 중 내가 어디"를 보여줄 때.

```mermaid
flowchart TB
    DEV["👨‍💻 신입 개발자<br/>PR 제출"]

    subgraph SYSTEM["🤖 AI 코드 리뷰 시스템 (Multi-Agent)"]
        direction TB
        ORC["오케스트레이터<br/>(요청 라우팅)"]

        subgraph ANALYZE["분석 단계 (병렬)"]
            M2["정적분석·보안<br/>(다른 팀)"]
            M3["⭐ 테스트·성능 분석<br/>(test-performance-agent)<br/>= 내 파트"]
        end

        REVIEW["⭐ 종합·코멘트 작성<br/>(pr-comment-agent)<br/>= 내 파트"]
    end

    DB[("🗄️ 공유 DB<br/>GCP PostgreSQL")]
    OUT["💬 GitHub PR 코멘트<br/>📢 Slack 알림"]

    DEV --> ORC
    ORC --> M2
    ORC --> M3
    M2 --> REVIEW
    M3 --> REVIEW
    M3 -.저장.-> DB
    REVIEW --> OUT

    style M3 fill:#cde,stroke:#369,stroke-width:3px
    style REVIEW fill:#cde,stroke:#369,stroke-width:3px
```

🎙️ "전체 시스템에서 제가 만든 건 **파란 두 개** — 코드를 검사하는 분석 모듈과, 그 결과로 코멘트를 만드는 모듈입니다."

---

## 🎯 다이어그램 2. 내 모듈 상세 흐름 ⭐ (메인 아키텍처)

> **언제 쓰나**: 핵심 슬라이드. "내가 만든 게 어떻게 동작하는지".

```mermaid
flowchart TB
    IN["📥 입력<br/>PR 코드 · scan_id"]

    subgraph DEV3["⭐ test-performance-agent (검출)"]
        direction TB
        CLONE["① GitHub clone<br/>(코드 통째로)"]
        SANDBOX["② Docker 샌드박스<br/>진짜 pytest 실행"]
        DETECT["③ 6개 탐지기 병렬<br/>커버리지·N+1·복잡도·누수…"]
        FILTER["④ diff 필터<br/>신입이 바꾼 부분만"]
        JSON["⑤ 표준 JSON 생성"]
        CLONE --> SANDBOX --> DETECT --> FILTER --> JSON
    end

    subgraph COMMENT["⭐ pr-comment-agent (집계·코멘트)"]
        direction TB
        AGG["⑥ 집계·판정<br/>통과/재작업/긴급"]
        REFINE["⑦ LLM 코멘트 생성<br/>(신입 수준 맞춤)"]
        POST["⑧ GitHub 등록"]
        AGG --> REFINE --> POST
    end

    DB[("🗄️ GCP DB<br/>scan_issues·summaries")]

    IN --> CLONE
    JSON --> AGG
    JSON -.저장.-> DB
    POST --> OUT["💬 PR 코멘트"]

    style DEV3 fill:#eef,stroke:#369
    style COMMENT fill:#efe,stroke:#393
```

🎙️ "왼쪽이 **검출**(코드 받아서 → 도커에서 실행 → 문제 찾기), 오른쪽이 **집계·코멘트**(문제 모아서 판정 → 코멘트 작성 → 등록). 이 8단계가 한 흐름으로 자동으로 돕니다."

---

## 🎯 다이어그램 3. "추정 vs 측정" 철학 (차별점)

> **언제 쓰나**: 차별점 강조할 때. 개발자·심사 대상.

```mermaid
flowchart LR
    subgraph OLD["❌ 기존 도구"]
        O1["코드를 글자로 읽음"] --> O2["'문제 같다' 추측"]
    end
    subgraph NEW["✅ Dev3"]
        N1["AST로 구조 분석<br/>(정확한 사실)"] --> N3
        N2["Docker에서 실제 실행<br/>(실측값)"] --> N3
        N3["사실 + 측정값"] --> N4["LLM은 설명만<br/>(환각 방지)"]
    end

    style NEW fill:#efe,stroke:#393,stroke-width:2px
    style OLD fill:#fee,stroke:#933
```

🎙️ "기존 도구는 코드를 읽고 추측해요. Dev3는 **실제로 돌려서 측정**하고, 사실은 도구로 정확히 뽑은 다음 설명만 AI한테 맡깁니다."

---

## 🎯 다이어그램 4. 데이터 흐름 + 판정 로직 (집계 상세)

> **언제 쓰나**: "판정이 어떻게 나오나" 설명할 때.

```mermaid
flowchart TB
    ISSUES["검출된 이슈들<br/>(각각 Critical/Major/Minor 등급)"]
    COUNT["심각도별 개수 세기"]
    ISSUES --> COUNT
    COUNT --> CHECK{"판정 규칙"}
    CHECK -->|"Critical ≥ 1"| ESC["🔴 escalate<br/>긴급 (시니어 호출)"]
    CHECK -->|"Major ≥ 3"| RWK["🟠 rework<br/>재작업"]
    CHECK -->|"그 외"| LGTM["🟢 lgtm<br/>통과"]

    ESC --> CMT["코멘트 + 알림"]
    RWK --> CMT
    LGTM --> CMT

    style ESC fill:#fdd,stroke:#933
    style RWK fill:#fed,stroke:#963
    style LGTM fill:#dfd,stroke:#393
```

🎙️ "문제를 심각도별로 센 다음, 정해진 규칙으로 통과·재작업·긴급을 자동 판정합니다."

---

## 🎯 다이어그램 5. 기술 스택 (한 장 요약)

> **언제 쓰나**: "뭘로 만들었나" 물어볼 때. 부록용.

```mermaid
flowchart LR
    subgraph T["검출 기술"]
        AST["Python AST<br/>(코드 구조 분석)"]
        DOCKER["Docker<br/>(격리 실행)"]
        PYTEST["pytest-cov<br/>(커버리지 실측)"]
    end
    subgraph S["저장·추적"]
        PG["PostgreSQL<br/>(GCP)"]
        LS["LangSmith<br/>(추적)"]
    end
    subgraph Q["품질"]
        TDD["TDD<br/>131 테스트 PASS"]
    end
    T --> S
    T --> Q
```

🎙️ "검출은 AST·Docker·pytest로 실측하고, 결과는 GCP DB에 쌓고, 전 과정을 TDD로 검증했습니다."

---

## 🎯 다이어그램 6. 미래 로드맵 (확장 가지)

> **언제 쓰나**: 마무리. "여기서 더 발전한다".

```mermaid
flowchart LR
    NOW["현재<br/>커버리지=실측 ✅<br/>N+1=추정 ⚠️"]
    NOW --> A2["A2 쿼리 카운팅<br/>'쿼리 87번' 증명"]
    NOW --> B1["B1 뮤테이션 테스팅<br/>껍데기 테스트 폭로"]
    NOW --> C1["C1 회귀 감지<br/>main 대비 비교"]
    A2 --> GOAL["🎯 완전한<br/>'실측 엔진'"]
    B1 --> GOAL
    C1 --> GOAL

    style GOAL fill:#cde,stroke:#369,stroke-width:2px
```

🎙️ "지금은 커버리지만 실측인데, N+1·복잡도까지 전부 실측으로 확장하는 게 다음 단계예요."

---

# 📋 PPT 구성 추천 (다이어그램 어디에 쓸지)

| 슬라이드 | 다이어그램 | 한 줄 |
|---|---|---|
| 1. 전체 시스템 | **1번** | "전체 중 내가 어디" |
| 2. 내 모듈 흐름 | **2번** ⭐ | "8단계로 자동 동작" |
| 3. 차별점 | **3번** | "추측 아니라 측정" |
| 4. 판정 로직 | **4번** | "통과/재작업/긴급 자동" |
| 5. 기술·품질 | **5번** | "AST·Docker·TDD" |
| 6. 미래 | **6번** | "실측 엔진으로 확장" |

---

# 🖼️ PPT에 넣는 법

1. VS Code에서 이 파일 열기
2. `Ctrl + Shift + V` (미리보기)
3. 다이어그램이 그림으로 보임
4. **캡처(Win + Shift + S)** 해서 PPT에 붙이기

> 또는 다이어그램 코드를 [mermaid.live](https://mermaid.live)에 붙여넣으면 **고화질 PNG 다운로드** 가능 (PPT용으로 더 깔끔).

---

*아키텍처 다이어그램 끝 · 연계: 발표자료_DEV3.md, 발표자_검출집계_설명.md*
