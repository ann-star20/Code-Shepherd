# crawling-chunking-guide.md — 문맥 보존형 정적 청킹 및 지식 추출 지침서 (온톨로지 통합본)

> 목적: `beautifulsoup4`로 추출한 기술 문서 본문을 `gemini-2.5-flash` 모델의 100만 컨텍스트 윈도우 스펙에 맞춰 최적의 크기로 청킹하고, 정보 소실 없이 **4-Layer 온톨로지 구조**를 무결하게 추출하기 위한 백엔드 스크립팅 명세.
이 지침을 가장 우선으로 적용한다.
---

## 1. 기반 인프라 및 LLM 스펙 규격

* **대상 모델**: `gemini-2.5-flash`
* **컨텍스트 윈도우**: 최대 입력 1,048,576 토큰 / 최대 출력 65,535 토큰
* **무료 티어 제약 조건**: 분당 최대 20회 요청 제한 (20 RPM)
* **영속화 인프라**: PostgreSQL (vector(1024), HNSW) + Neo4j (자연키 MERGE)

---

## 2. 4-Layer 온톨로지 추출 스키마 정의

LLM이 3~4만 자의 대용량 텍스트 청크를 분석할 때, 아래의 **4-Layer 계층형 온톨로지 컨벤션**에 맞춰 구조화된 JSON 데이터셋을 반환하도록 프롬프트 컨텍스트를 강제한다.

| 레이어 레벨 | 온톨로지 엔티티 유형 (Type) | 세부 역할 및 데이터 매핑 제약 조건 |
| --- | --- | --- |
| **Layer 0** | `Domain` | 파이프라인 진입점. `allowed_domains` 메타데이터(예: `security`, `performance`)를 기반으로 분류되며, Neo4j의 최상위 동적 라벨(`:Security`, `:Performance`)과 1:1 매핑됨. |
| **Layer 1** | `Concept` | 기술 문서가 다루는 고유한 핵심 지식 단위를 추출 (예: `SQL Injection`, `Query Optimization`). |
| **Layer 2** | `Mechanism` / `Property` /<br>

<br>`RootCause` / `Component` | 개념을 구성하는 다차원 속성 레이어.<br>

<br>• **Mechanism**: 방어 대책, 튜닝 메커니즘 (예: `Parameterized Queries`).<br>

<br>• **Property**: 엔티티의 특성 지표.<br>

<br>• **RootCause**: 취약점이나 성능 저하의 근본 원인.<br>

<br>• **Component**: 연관된 소프트웨어 구성 요소. |
| **Layer 3** | `CodeExample` | 최하위 구현 레이어. 메커니즘을 실제 코드로 증명하는 영역으로, 파일 내에서 `unq_id = f"{mechanism}_{lang}_{lang_version}_{framework}_{framework_version}"` 식별자를 생성하여 버전별로 엄격히 분리 적재함. |

---

## 3. 구조적 청킹 (Structural Chunking) 설계 표준

무조건적인 글자 수 슬라이싱 방식은 상위 개념 설명부와 하위 코드 구현부를 분리시켜 4-Layer 온톨로지의 연결 고리를 파괴하므로, BeautifulSoup4 파싱 후 아래의 **3단계 구조적 청킹 메커니즘**을 강제한다.

### 3.1 청크 크기 규격 (Chunk Size Metric)

* **목표 청크 크기**: **30,000자 ~ 40,000자 (공백 포함 글자 수 기준)**
* **설계 근거**: 8,000자 내외의 협소한 청킹은 기술 스펙 문서의 개념설명(`Concept`)과 해결대책(`Mechanism`)의 관계를 단절시킴. 3~4만 자(약 1만~1.5만 토큰) 단위를 유지해야만 Layer 1부터 Layer 3까지 연결되는 전역적 지식 그래프 스키마를 단일 컨텍스트 안에서 유실 없이 온전히 보존할 수 있음.

### 2.2 청크 경계 결정 알고리즘 (Boundary Logic)

1. **HTML 헤더 기반 스냅 (`<h1>`, `<h2>`, `<h3>`)**: BeautifulSoup으로 정제된 본문 텍스트 스트림을 누적하다가, 30,000자가 넘어가는 시점 이후에 등장하는 **가장 가까운 마크다운 헤더 또는 HTML 제목 태그 직전**에서 청크를 마감하여 논리적 챕터 구조를 유지한다.
2. **문단 기호 기반 폴백 (`\n\n`)**: 적절한 헤더 태그가 식별되지 않는 문서의 경우, 35,000자 통과 시점 이후 가장 먼저 등장하는 **개행 기호 문자열 또는 문장 마침표 뒤**에서 잘라 문장이 절단되는 현상을 방어한다.
3. **컨텍스트 오버랩 (Overlap) 세팅**: 청크 간의 연속성 유지를 위해, 이전 청크의 마지막 **2,000자 ~ 3,000자 분량의 텍스트를 다음 청크의 최상단에 중복 적재**하여 문맥의 연속성을 보장한다.

---

## 4. 백엔드 `extract_task` 파이프라인 구현 명세

`backend/app/worker/tasks.py` 내부의 3단계 추출 엔진 스크립트 작성 시 아래의 **온톨로지 메타 주입 및 Rate Limit 인터락 코드**를 의무적으로 준수한다.

### 4.1 온톨로지 주입형 코어 스크립트 구조

```python
import time
import logging
from typing import List
from app.infrastructure.llm.factory import BgeEmbeddingClient # 1024차원 싱글톤 보장

logger = logging.getLogger("pipeline")

@celery_app.task
def extract_task(session_id: str, framework: str, language: str):
    """
    BeautifulSoup4로 청킹 완료된 원시 텍스트 리스트를 순회하며 
    4-Layer 온톨로지 메타 데이터 구조에 맞게 지식을 추출하는 코어 태스크
    """
    _set_state(session_id, "EXTRACTING") # 상태 전이 바인딩
    
    # 🎯 [온톨로지 인터락 1] 영속성 레이어에서 허용 도메인 명세 추출 (Layer 0 결합)
    doc_metadata = db.query(KnowledgeDocument).filter_by(session_id=session_id).first()
    allowed_domains = doc_metadata.allowed_domains if doc_metadata else []
    
    # 🎯 [온톨로지 인터락 2] 4-Layer 결합을 위한 LLM 주입용 메타데이터 사전 정의
    metadata = {
        "framework": framework,
        "language": language,
        "allowed_domains": allowed_domains # LLM이 컨셉별 상위 도메인 분류 배지를 달 수 있도록 강제
    }
    
    chunks: List[str] = get_cleaned_chunks_from_storage(session_id)
    app_mode = get_app_mode() # PRODUCTION / MOCK 분기 제어
    
    extracted_payloads = []
    
    for idx, chunk in enumerate(chunks):
        logger.info(f"[{session_id}] Processing chunk {idx+1}/{len(chunks)} ({len(chunk)} chars)")
        
        # [인터락 1] PRODUCTION 모드 시 무료 티어 20 RPM 우회 강제 제어
        if app_mode == "PRODUCTION" and idx > 0:
            logger.info("Enforcing 4-second sleep to prevent Gemini 429 Rate Limit Error...")
            time.sleep(4) # 4초 하드 슬립 주입으로 안정적 트래픽 유지
            
        # [인터락 2] MOCK 모드 시 중복 적재 방지를 위한 단 1회 호출 계약 이행
        if app_mode == "MOCK" and idx > 0:
            logger.info("Mock Mode active: Skipping remaining chunks to avoid redundant staging dedup.")
            break
            
        # 🎯 [온톨로지 인터락 3] 청크 텍스트와 4-Layer 매칭용 메타데이터 구조를 함께 전송
        raw_ontology = client.extract_concepts(chunk, doc_id=doc_metadata.id, metadata=metadata)
        extracted_payloads.append(raw_ontology)
        
    # 데이터 영속화 레이어로 전송 (staging_concepts 테이블에 DRAFT 상태로 적재)
    write_staging_draft(session_id, extracted_payloads)
    _set_state(session_id, "EXTRACTED")

```

---

## 5. 구현 체크포인트 & 수치 무결성 검증

* **도메인 배지 누락 검증**: 추출되어 `staging_concepts`에 적재된 JSON 결과물 내에 `domains` 배열 필드가 비어있지 않고, `allowed_domains`에 지정된 값으로 정상 분류되었는지 차단 검증(Assertion) 코드를 추가한다.
* **BGE-M3 차원 정합성**: 추출된 온톨로지 텍스트 요소가 임베딩 가속 레이어로 진입할 때, 반드시 단일 `BgeEmbeddingClient(1024-dim)` 싱글톤 클래스를 거쳐 PostgreSQL의 벡터 컬럼 규격과 밀도가 완벽히 일치하는지 확인한다.
