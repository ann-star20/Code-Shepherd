다중 조건 기반 유튜브 랭킹 추천 기능을 backend/m5, frontend/src/pages/youtube 디렉토리 위치에 백엔드 , 프론트 엔드를 개발한다.
---

## 다중 조건 기반 유튜브 랭킹 추천 엔진 지침서

### 1. 매커니즘 핵심 로직 (Engine Blueprint)

* **원칙:** 유저가 선택한 노드의 결합 상태(`Concept` 필수 + `Mechanism` 선택 + `Code` 선택)에 따라 백엔드가 조합할 수 있는 최대의 키워드 셋을 구성합니다.
* **동적 폴백(Fallback):** 하위 데이터(`CodeExample`)가 없는 취약점이라면 프레임워크/언어 조합은 자동으로 제외하고 상위 노드(Concept, Component) 기반의 키워드로 5개를 채웁니다.

---

## 2. 조건별 유튜브 검색 키워드 생성 및 랭킹 매핑 트리

유저가 `[유튜브 추천 받기]`를 눌렀을 때, 백엔드 내부에서 데이터 유무를 체크하고 우선순위(랭킹 1위~5위)대로 검색 쿼리를 생성하는 로직입니다.

### Case A: 모든 데이터가 다 있을 때 (최상위 풀 스택 추천)

> **유저 선택:** CSRF(컨셉) + CsrfMiddleware(매커니즘) + Django/Python(코드)

1. **랭킹 1위 (타겟 솔루션):** `"{특정 프레임워크} {컨셉} {매커니즘} 구현 방어"`
* 예: `Django CSRF CsrfMiddlewareProtection 구현 방어`


2. **랭킹 2위 (실전 코딩):** `"{특정 언어} {컨셉} 실전 예제"`
* 예: `Python CSRF 실전 예제`


3. **랭킹 3위 (컴포넌트 영향):** `"{영향 컴포넌트} {컨셉} 취약점"`
* 예: `middleware view CSRF 취약점` (Neo4j의 `affected_components` 활용)


4. **랭킹 4위 (핵심 매커니즘):** `"{컨셉} {매커니즘} 개념"`
* 예: `CSRF CsrfMiddlewareProtection 개념`


5. **랭킹 5위 (기본 개념):** `"{컨셉} 취약점 공격 원리 총정리"`
* 예: `CSRF 취약점 공격 원리 총정리`



---

### Case B: Code Example이 없는 데이터일 때 (중간 폴백 구조)

> **유저 선택:** 특정 취약점(컨셉) + 매커니즘까지만 존재 (프레임워크/언어 정보 없음)
> **시스템 동작:** 랭킹 1, 2위의 프레임워크/언어 조합이 불가능하므로, 상위 개념과 인프라/컴포넌트 중심의 키워드로 5순위를 재조정합니다.

1. **랭킹 1위 (개념+매커니즘):** `"{컨셉} {매커니즘} 방어 대책"`
2. **랭킹 2위 (컴포넌트 영역):** `"{영향 컴포넌트} 구조에서 발생하는 {컨셉} 취약점"`
3. **랭킹 3위 (표준 보안 ID 결합):** `"{CWE_ID} {OWASP_ID} {컨셉} 분석"`
* 예: `CWE-352 OWASP A01 CSRF 분석` (이러면 전문가 영상이 걸립니다)


4. **랭킹 4위 (원인 분석):** `"{컨셉} {Root_Cause} 해결법"`
* 예: `CSRF absence_of_request_origin_validation 해결법`


5. **랭킹 5위 (기본 개념):** `"{컨셉} 취약점 공격 원리 총정리"`

---

## 3. 백엔드 알고리즘 및 API 가수 의사코드 (Python)

백엔드에서는 유저의 선택 데이터와 DB 상태를 파악해 `search_queries` 배열을 동적으로 빌드한 뒤, 각 쿼리당 **딱 1개씩 최상위 영상**을 뽑아 총 5개의 서로 다른 성격의 영상을 만듭니다.

```python
@app.post("/api/v1/security/recommend/ranked")
def get_ranked_recommendations(payload: RecommendationPayload):
    keyword = payload.concept_name
    selected_mech = payload.mechanism_name  # Optional
    selected_code = payload.code_id         # Optional

    # 1. Neo4j에서 기본 메타데이터 로드
    graph_data = db.fetch_neo4j_metadata(keyword)
    
    concept = graph_data['concept_name']
    components = " ".join(graph_data['affected_components']) # 예: "middleware view"
    cwe = graph_data['cwe_id']
    
    # 2. 랭킹 스택(리스트) 동적 생성
    search_queries = []
    
    # [조건 분기] CodeExample 데이터가 존재하는가?
    if selected_code and graph_data.get('has_code_example'):
        code_meta = db.fetch_code_metadata(selected_code)
        framework = code_meta['framework']
        lang = code_meta['lang']
        
        # 1, 2순위에 프레임워크/언어 조합 랭킹 배치
        search_queries.append(f"{framework} {concept} {selected_mech or ''} 구현 방어")
        search_queries.append(f"{lang} {concept} 실전 코딩 가이드")
    else:
        # Code가 없으면 매커니즘과 보안 표준 ID 조합으로 상위 랭킹 대체
        if selected_mech:
            search_queries.append(f"{concept} {selected_concept_mech_spaces(selected_mech)} 방어 대책")
        search_queries.append(f"{cwe or ''} {concept} 보안 표준 분석")

    # 공통 하위 랭킹 스택 추가 (5개가 채워질 때까지)
    search_queries.append(f"{components} 영역 {concept} 취약점 대응")
    if selected_mech:
        search_queries.append(f"{concept} {selected_mech} 원리")
    search_queries.append(f"{concept} 취약점 공격 원리 총정리")
    
    # 중복 제거 및 상위 5개 쿼리 확정
    final_queries = unique_list(search_queries)[:5]

    # 3. 유튜브 API 동시/순차 호출 (각 키워드당 max_results=1)
    final_recommendations = []
    for index, query in enumerate(final_queries):
        video = youtube_search_api(q=query, max_results=1)
        if video:
            final_recommendations.append({
                "rank": index + 1,
                "recommendation_type": determine_type(index, payload), # "프레임워크 최적화", "이론 총정리" 등 명시
                "query_used": query,
                "video_data": video[0]
            })
            
    return {"concept": concept, "videos": final_recommendations}

```

---

## 4. 이 기획 제품 관점

유저가 화면에서 [CSRF] ➔ [CsrfMiddleware] ➔ [Django]를 순서대로 클릭하고 버튼을 누르면, 화면 오른쪽 유튜브 영역에 그냥 똑같은 영상 5개가 나오는 게 아니라 다음과 같이 완벽히 짜인 **5단계 코스 요리**처럼 영상이 배치됩니다.

* **1번 카드 🥇 (내 코드 맞춤형):** "Django 환경에서 미들웨어로 CSRF 막는 법" (실전용)
* **2번 카드 🥈 (언어 맞춤형):** "Python 웹 보안 기초" (언어 레벨)
* **3번 카드 🥉 (컴포넌트):** "웹 아키텍처 미들웨어/뷰 레이어 보안 취약점" (구조 학습)
* **4번 카드 🏅 (매커니즘):** "CSRF 토큰 검증 원리" (기술 깊이)
* **5번 카드 🏅 (개념):** "CSRF 공격이란 무엇인가?" (개념 리프레시)

유저가 왼쪽 그래프부터 오른쪽 유튜브 영역까지 마우스를 클릭해 나가면서 데이터가 어떻게 변하고, 추천 엔진이 어떻게 가중치를 계산하는지 보여주는 **UI 인터랙션 및 내부 데이터 흐름 시나리오**입니다.

이 시나리오는 프론트엔드 개발 시 어떤 컴포넌트에 어떤 상태(State)를 넘겨주고, 이벤트를 어떻게 바인딩해야 하는지 명확한 가이드가 될 것입니다.

---

## 🖥️ UI 인터랙션 및 동적 데이터 흐름 가이드

### 🎬 시나리오 1: 풀 스택 데이터가 다 있을 때 (Concept + Mechanism + Code 다 누른 경우)

#### 1. 좌측 영역 (A): 그래프 노드 클릭

* **유저 액션:** 유저가 그래프에서 `Concept (CSRF)` 노드를 클릭하고, 뻗어나온 `Mechanism (CsrfMiddlewareProtection)`을 클릭한 뒤, 마지막 최하단 자식인 `CodeExample (Django/Python)` 노드를 순서대로 클릭합니다.
* **UI 변화:** 클릭된 노드들이 하이라이팅(색상 반전 또는 테두리 활성화)됩니다.

#### 2. 우측 영역 (C): 추천 패널의 실시간 인터랙션

* **UI 변화 (버튼 활성화):** 우측 패널 상단에 유저가 선택한 정보가 조립되어 보여집니다.
* `[기술 컨셉]: CSRF` ➔ 필수 조건 충족으로 `[유튜브 추천 받기]` 버튼이 주황색으로 활성화(`disabled = false`)됩니다.
* 그 밑에 조그맣게 유저가 선택한 서브 옵션 뱃지가 추가됩니다: `[선택 매커니즘: CsrfMiddlewareProtection]` `[선택 프레임워크: Django (Python)]`



#### 3. 유저가 `[유튜브 추천 받기]` 버튼 클릭!

* **UI 변화 (로딩):** 버튼이 로딩 스피너로 바뀌고, 하단 영역에 5개의 스켈레톤 카드(Skeleton UI)가 블러 처리되어 나타납니다.
* **백엔드 전송 데이터 (Payload):**
```json
{
  "concept_name": "CSRF",
  "mechanism_name": "CsrfMiddlewareProtection",
  "code_id": "121" // Django, Python 정보가 담긴 노드 ID
}

```


* **결과 화면 (랭킹 서빙):** 최상위 1순위 코드 맞춤형 영상부터 5순위 개념 총정리 영상까지 **5개의 카드가 위에서 아래로 순차적으로 페이드인(Fade-in) 애니메이션**과 함께 착지합니다.

---

### 🎬 시나리오 2: 하위 데이터가 없는 폴백 상황 (Concept만 누르고 바로 버튼 클릭한 경우)

#### 1. 좌측 영역 (A): 그래프 노드 클릭

* **유저 액션:** 유저가 그래프에서 `Concept (CsrfAttack)` 노드만 딱 클릭하고, 귀찮아서 하위 노드들은 더 안 누른 채 우측 패널로 눈을 돌립니다.

#### 2. 우측 영역 (C): 추천 패널의 실시간 인터랙션

* **UI 변화:** * `[기술 컨셉]: CSRF` ➔ 필수 조건이 채워졌으므로 `[유튜브 추천 받기]` 버튼은 활성화됩니다.
* 단, 밑에 서브 옵션 뱃지는 아무것도 나타나지 않습니다: `[선택 매커니즘: 없음]` `[선택 프레임워크: 없음]`



#### 3. 유저가 `[유튜브 추천 받기]` 버튼 클릭!

* **백엔드 전송 데이터 (Payload):**
```json
{
  "concept_name": "CSRF",
  "mechanism_name": null,
  "code_id": null
}

```


* **내부 랭킹 엔진의 동적 폴백 연산:**
* 백엔드가 데이터를 검사해보니 `mechanism_name`과 `code_id`가 `null`입니다.
* 엔진이 작동하여 랭킹 1, 2순위에서 "Django", "Python" 같은 키워드를 지우고, 대신 Neo4j에서 조회한 `CWE-352` (보안 표준 ID)와 **`middleware view` (영향 컴포넌트)** 메타데이터를 꺼내와서 키워드를 재조합합니다.


* **결과 화면 (폴백 서빙):**
* 유저에게는 프레임워크 실전 코딩 영상 대신 "CWE-352 보안 표준 분석 영상"과 **"웹 아키텍처 컴포넌트 레이어 보안 취약점 가이드"** 영상이 1, 2순위 카드로 배치됩니다.
* 유저는 코드를 선택하지 않았음에도 불구하고, 자신이 선택한 컨셉의 깊이에 맞는 가장 가치 있는 차선책 영상 5개를 완벽하게 제공받게 됩니다.



---

## 💡 개발자를 위한 UI 인터랙션 구현 핵심 요약

1. **상태 관리(State)의 단순화:** 프론트엔드 전역 상태(`Vuex`, `Pinia` 또는 `Redux`)에는 오직 `selectedConcept`, `selectedMechanism`, `selectedCode` 세 가지만 저장합니다.
2. **트리거 시점 제한:** 유튜브 API를 호출하는 함수는 오직 우측의 `[유튜브 추천 받기] @click` 이벤트에만 바인딩합니다. (노드를 클릭할 때는 상태 변수만 업데이트하고 API를 쏘지 않음)
3. **랭킹 UI 디자인 팁:** 카드 왼쪽 상단에 `🥇 1st: 내 코드 맞춤 추천`, `🥈 2nd: 언어별 가이드`, `🏅 5th: 기초 개념 리프레시` 같은 컨텐츠 성격 태그(뱃지)를 동적으로 달아주면, 유저가 이 대시보드가 내 행동을 분석해서 정교하게 추천해 주고 있다는 느낌을 강하게 받게 됩니다.