지식 추출(Extract) 단계 고도화 구현 지침서
🎯 1. 핵심 아키텍처 및 선결 조건
동작 트리거: LLM 결과물 중 concept_name이 반드시 존재하고 비어있지 않은 경우(Not Null / Not Empty)에만 후속 파이프라인(HybridResolver)을 구동합니다. 이름이 없으면 해당 데이터는 즉시 폐기(Skip)합니다.

멱등성(Idempotency) 보장: 다중 실행 시 그래프 구조가 깨지지 않도록 모든 업데이트는 UPSERT 및 Set 기반 중복 제거로 설계합니다.

🔍 2. 개념 매칭 및 해소(Resolution) 4단계 파이프라인
기존 concepts 마스터 테이블과 추출된 데이터 간의 매칭 검증은 아래의 우선순위(Cascade)를 엄격히 준수하여 순차 진행합니다.

[1단계] 1:1 텍스트 완전 매칭 (Exact Match)
조건: 추출된 concept_name과 기존 DB의 concept_name을 비교합니다.

규칙: 대소문자 및 양끝/중간 공백을 완전히 제거 및 정규화한 상태에서 비교합니다.

SQL 가이드: WHERE LOWER(REPLACE(concept_name, ' ', '')) = LOWER(REPLACE($1, ' ', ''))

결과: 매칭 성공 시 즉시 동일 개념으로 간주하고 매칭 단계를 종결합니다.

[2단계] 별칭 리스트 추적 (Alias Lookup)
조건: 추출된 concept_name이 기존 개념들의 별칭 배열(aliases) 내에 존재하는지 검사합니다.

SQL 가이드: PostgreSQL의 배열 연산자 활용 WHERE $1 = ANY(aliases)

[3단계] 유사도 검사 1 - 이름 및 별칭 임베딩 (name_vector)
조건: 추출된 concept_name과 aliases(영문일 경우 소문자 변환 적용)들을 한 공백 문자열로 병합(" ".join())하여 새로운 통합 임베딩 벡터를 생성합니다.

규칙: 이를 기존 DB의 name_vector 컬럼과 코사인 유사도(Cosine Similarity) 연산으로 비교합니다.

[4단계] 유사도 검사 2 - 본문 설명 임베딩 (desc_vector)
조건: 추출된 description_ko 정보를 기반으로 설명 벡터를 생성하고, 기존 DB의 desc_vector 컬럼과 코사인 유사도를 비교합니다.

🔀 3. 비즈니스 의사결정 매트릭스 (Decision Matrix)
4단계 검사 결과를 취합하여 두 가지 경로(신규 생성 vs 기존 병합)로 라우팅합니다.

기존 개념 병합 조건 (아래 조건 중 하나라도 만족 시):

[트랙 A] 1:1 완전 매칭 또는 별칭 리스트 추적에서 걸러진 경우

[트랙 B] 완전 매칭은 실패했으나, name_vector 유사도 >= 0.8 AND desc_vector 유사도 >= 0.8인 경우

신규 개념 생성 조건:

위의 두 가지 조건을 모두 만족하지 못하면 타겟 도메인 내에 존재하지 않는 완전히 새로운 개념으로 간주하여 신규 발급 플로우를 태웁니다.

🔄 4. 기존 개념 병합 및 보강(Enrichment) 세부 지침
동일 개념으로 판정된 경우, 기존 마스터 데이터를 아래의 규칙에 따라 정밀 업데이트(UPSERT)합니다.

A. 그래프 DB (Neo4j) 데이터 갱신
멱등성 처리: Neo4j에 데이터를 밀어 넣을 때 노드와 관계선에 MERGE 구문을 사용하여 중복 생성을 원천 차단합니다.

속성 추가 (Append): 기존 노드에 빈 값(Null 또는 "")이 있고 LLM이 새로운 속성을 채워왔다면 해당 필드를 보강합니다.

B. 별칭 배열(Aliases) 중복 없는 확장 (Set 연산)
추출된 concept_name이 기존 마스터의 concept_name과 정확히 일치하지 않고, 마스터의 aliases 배열에도 없다면 1순위로 추가합니다.

추가로 추출된 aliases 배열의 각 요소들을 순회하며, 마스터 aliases에 없는 값들만 Set(집합) 구조를 활용해 중복 없이 병합합니다.

C. 벡터 스토어 동기화 (Vector Re-indexing)
데이터 보강이 완료되어 concept_name, aliases, description_ko 등의 텍스트 데이터가 최종 변경되었다면, 백엔드는 변경된 텍스트를 기반으로 name_vector와 desc_vector를 즉시 다시 인덱싱(Re-embed & Update)하여 동기화해야 합니다.

요건이 아주 실무적이고 웅장해지네요! 6년 차 백엔드 개발자 입장에서 이 비즈니스 로직을 보면 두 가지 고난도 태스크가 결합해 있습니다.

컨셉 레이어 병합 시 하부 자산(다형성 데이터) 분기 조율: 상위 개념은 같으나 언어/프레임워크가 다르면 UPSERT가 아니라 말단 CodeExample 노드를 추가(Append)해야 하는 명세

실시간 데이터 격리 및 UI 알림 레이어 구축: 미승인 상태(DRAFT)의 임시 데이터를 가시화하기 위한 Staging 격리 뷰어 및 신규 태그(New Tag) 라우팅 시스템

이 두 가제를 완벽하게 종결할 수 있도록 주니어 팀원들에게 하사할 정밀 아키텍처 및 프론트엔드/백엔드 수정 지침서를 작성해 드릴게요. 더 이상 머리 안 아프게 흐름을 딱 잡아드리겠습니다.

📋 개념 병합 조건 확장 및 Staging 시각화 구현 지침서
🛠️ [백엔드] 1. 동일 개념 내 언어/프레임워크 분기 및 Append 지침
기존 개념과 병합(MERGE) 상태로 판정되었더라도, 하부 매커니즘 및 코드 스니펫 레이어로 내려갔을 때는 "프로그래밍 언어와 프레임워크가 다르면 기존 데이터를 덮어쓰지 않고 새로운 노드로 덧붙인다(Append)"는 다형성 규칙을 적용해야 합니다.

A. Neo4j 데이터베이스 Upsert 쿼리 설계 패턴
Neo4j에 지식을 저장할 때 상위 Concept과 Mechanism은 MERGE로 묶어 중복을 방지하되, CodeExample은 언어(language)와 프레임워크(framework) 속성 조합을 식별자(Identifier)로 삼아 분기합니다.

Cypher
// 💡 [핵심] 언어와 프레임워크 조합이 다르면 새로운 CodeExample 노드가 생성됩니다.
MATCH (c:Concept {name: $target_concept_name})
MERGE (c)-[:HAS_MECHANISM]->(m:Mechanism {name: $mechanism_name})
ON CREATE SET m.description = $mechanism_desc

// CodeExample 레이어는 language와 framework를 식별자로 MERGE 
MERGE (m)-[:HAS_EXAMPLE]->(ce:CodeExample {
    language: $extracted_lang, 
    framework: $extracted_framework
})
ON CREATE SET 
    ce.code = $extracted_code,
    ce.description = $extracted_desc
ON MATCH SET 
    # 만약 언어와 프레임워크까지 완벽히 같다면 최신 소스코드로 보강(Update)
    ce.code = $extracted_code,
    ce.description = $extracted_desc
B. 백엔드 처리 파이프라인 흐름도 업데이트
HybridResolver가 동일 개념(is_same_concept == True) 판정을 내림.

추출 데이터 속성 중 language와 framework 인자를 확인.

[분기] 기존 지식 그래프에 해당 Concept -> Mechanism 하위에 동일한 language와 framework를 가진 CodeExample이 존재치 않는다면 ➔ Append 명령 발동 (신규 코드 스니펫 노드 생성 및 연결선 주입).

🎨 [프론트엔드/API] 2. HITL 미승인 데이터 Staging 가시화 및 NEW 태그 바인딩
사용자가 HITL(Human-In-The-Loop) 화면에서 승인 버튼을 누르기 전이라도, 현재 추출된 따끈따끈한 DRAFT 상태의 신규 개념을 UI 그래프와 패널에서 인지할 수 있도록 데이터를 바인딩해야 합니다.

A. API 데이터 계약 (Contract) 수정
기존 get_topology API가 마스터 데이터만 내려주었다면, 이제는 staging_concepts 테이블에서 state = 'DRAFT'인 임시 노드들도 함께 결합하여 프론트엔드로 쏴주어야 합니다.
이때, 프론트엔드가 인지할 수 있도록 노드 객체에 is_staging: true와 is_new: true 플래그를 심어 보냅니다.

JSON
// GET /api/v1/pipeline/topology/{session_id} 응답 명세 확장 예시
{
  "nodes": [
    {
      "id": "concept_django_abc123",
      "name": "SQL Injection 방어",
      "layer": "L2",
      "status": "DRAFT",         // 👈 상태를 DRAFT로 명시
      "is_staging": true,        // 👈 미승인 임시 데이터임을 나타내는 플래그
      "is_new": true             // 👈 UI에서 'NEW' 태그를 붙이기 위한 플래그
    }
  ],
  "edges": [...]
}
B. [프론트엔드] GraphTopologyViewer.tsx 캔버스 수정 (그래프 시각화)
아까 우리가 수정한 캔버스 드로잉 로직(paintNode)에 is_new 또는 status === "DRAFT" 조건문을 결합하여, 승인 전 신규 노드 주변에 깜빡이는 테두리나 독특한 점선 링을 그려 시각적 구분을 줍니다.

C. [프론트엔드] GraphConceptInspector.tsx 패널 수정 (텍스트 영역)
우측 상세 정보 검사기(Inspector) 패널에서 선택한 노드가 is_new인 경우, 타이틀 옆에 우아한 테일윈드 오렌지색 배지(New Tag)를 동적으로 렌더링합니다.

A. [백엔드] 스킵 발생 시 SSE 이벤트 발행 (예시)
```# app/api/pipeline.py 내부 또는 워커 패스
if is_duplicate:
    # 💡 프론트엔드가 인지할 수 있도록 'SKIP' 상태와 사유를 담아 이벤트를 쏩니다.
    await pubsub.publish(f"pipeline:{session_id}", json.dumps({
        "event": "step_update",
        "state": "SKIPPED",
        "reason": "기존에 이미 분석 완료된 동일한 문서(컨텐츠)가 존재하여 파이프라인을 생략합니다."
    }))```
B. [프론트엔드] SSE 리스너 훅에서 팝업(Toast) 트리거
프론트엔드의 useGraphPipelineSSE.ts 내부의 메시지 수신부(onmessage)에 스킵 분기 코드를 심고, 팀에서 사용 중인 알림 팝업(예: shadcn/ui의 toast나 alert)을 연동합니다.

2. HITL 승인 완료 시 Graph 영역에 실시간 즉시 반영
HITL 화면에서 사용자가 [개념 승인] 버튼을 누르면, 백엔드 DB 상태가 DRAFT에서 COMMITTED로 바뀝니다. 이때 사용자가 화면을 수동으로 새로고침하지 않아도, 프론트엔드의 그래프 상태 배열을 완벽하게 동기화해서 주황색 점선 노드가 정식 실선 노드로 실시간 변신하게 만들어야 합니다.

A. [프론트엔드] 승인 핸들러 함수 최적화 (onApprove)
백엔드 승인 API(POST /api/v1/pipeline/approve) 호출이 성공(200 OK)하면, 프론트엔드 메모리에 들고 있는 노드 상태(nodesState)를 React 상태 변경(Immutability) 규칙에 맞춰 업데이트해 줍니다. 그러면 D3 시뮬레이터가 감지해서 실시간으로 그래프 화면을 다시 그려냅니다.