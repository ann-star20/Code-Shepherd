

# crawling-chunking-guide-v2.md: Pydantic 기반 온톨로지 데이터 무결성 강제 지침 개선안

> 목적: 강력한 검증 로직과 프롬프트 엔지니어링 기법(Few-Shot, 부정 지시어)이 완벽하게 반영되도록 업데이트

---

## 1. 데이터 검증 아키텍처 (Validation Architecture)

데이터 정제 파이프라인은 단순한 문자열 포매팅에 의존하지 않고, [원시 HTML 파싱 ➔ 3~4만 자 구조적 청킹 ➔ Pydantic 강제 파싱 ➔ 논리 무결성 검증 ➔ Staging 적재]의 5단계 방어벽 아키텍처를 추종한다. LLM이 스키마 규칙을 단 1바이트라도 위반할 경우, 디스크 적재를 차단하고 즉시 파이프라인 세션을 `FAILED`로 전이시킨다.

---

## 2. 무결성 강제형 Pydantic 온톨로지 스키마 설계 (`models.py`)

LLM이 컨셉 유형(`concept_type`)에 따라 필요한 하위 관계 필드들을 모순 없이 채우도록 유도하고, 본문 외 노이즈를 걸러내는 밸리데이터 계층을 도메인 모델에 주입한다.

```python
# backend/app/domain/models.py 내 추가 규격
# backend/app/domain/models.py 내 추가 규격
import re
from pydantic import BaseModel, Field, root_validator, validator
from typing import List, Optional

class ConceptExtractionSchema(BaseModel):
    """
    Gemini 추출 결과의 물리적/논리적 무결성을 엄격하게 강제하는 정형화 구조 스키마
    """
    # Layer 1 & 2 코어 데이터 명세
    concept_name: str = Field(
        ...,
        pattern=r"^[A-Z][a-zA-Z0-9]+$", 
        description="핵심 주제어. 반드시 PascalCase 규칙을 따르는 단일 명사여야 함. (예: CsrfProtection, NextProxy). 'concept_' 접두사나 해시 접미사(_b6ce44 등) 절대 금지."
    )
    concept_type: str = Field(
        ...,
        description="엔티티 유형. 반드시 다음 중 하나여야 함: 'concept', 'mechanism', 'property', 'root_cause', 'component'"
    )
    description_ko: str = Field(
        ...,
        description="본문 내용에 기반한 객관적인 한국어 핵심 요약 설명. 문서 외곽의 메타 정보, 링크 안내, 메뉴판 텍스트가 포함되면 즉시 거부됨."
    )
    domains: List[str] = Field(
        ...,
        description="상위 매핑 도메인 분류 리스트 (예: ['security'] 또는 ['performance'])"
    )
    
    # Layer 2 하위 관계 레이어 명세
    mechanism: List[str] = Field(default=[], description="유형이 'concept'인 경우, 이를 해결/방어하기 위한 하위 메커니즘 리스트")
    root_cause: Optional[str] = Field(default=None, description="유형이 'root_cause' 또는 'property'인 경우 결함의 근본 원인")
    affected_components: List[str] = Field(default=[], description="영향을 받거나 연관된 소프트웨어 컴포넌트 목록")
    
    # 보안/성능 특화 레이어 메타데이터
    cwe_id: Optional[str] = Field(default=None, description="보안 취약점인 경우 매핑될 CWE 식별자 (예: CWE-352)")
    owasp_id: Optional[str] = Field(default=None, description="OWASP TOP 10 식별자 코드")
    severity: Optional[str] = Field(default=None, description="위험도 등급: critical, high, medium, low")

    # 1차 검증: concept_type 리터럴 제한
    @validator("concept_type")
    def validate_type_enum(cls, v):
        allowed = ['concept', 'mechanism', 'property', 'root_cause', 'component', 'performance_antipattern']
        if v.lower() not in allowed:
            raise ValueError(f"concept_type은 반드시 {allowed} 중 하나여야 합니다.")
        return v.lower()

    # 2차 강력 인터락: 데이터 논리 모순 및 배너 광고 노이즈 검증기
    @root_validator(pre=False)
    def validate_ontology_logic(cls, values):
        c_type = values.get("concept_type", "").lower()
        mechanisms = values.get("mechanism", [])
        desc = values.get("description_ko", "")
        
        if not desc:
            return values
            
        # 1. 공식 문서 외곽 배너 및 메뉴판 노이즈 유입 차단 필터
        # [개선] 공백/개행을 모두 제거하고 소문자로 정규화하여 검증력 극대화
        normalized_desc = re.sub(r'\s+', '', desc.lower())
        
        # 차단할 타겟 노이즈 키워드 (공백 제거 상태 기준)
        noise_triggers = [
            "availableasmarkdown", 
            "next.jsdocumentation", 
            "llms.txt", 
            "lastupdated",
            "wasthishelpful",
            "menubars",
            "approuter"
        ]
        
        # [수정] 정규화된 텍스트(normalized_desc)를 기준으로 검사하도록 수정
        if any(trigger in normalized_desc for trigger in noise_triggers):
            raise ValueError("❌ 설명 필드 내에 기술문서 본문과 무관한 웹사이트 레이아웃 UI 노이즈가 포함되어 있습니다.")

        # 2. 계층조직 모순 차단: 개념 엔티티인데 하위 대응책(Mechanism)을 누락한 뇌절 방어
        if c_type == "concept" and not mechanisms:
            raise ValueError("concept 유형의 엔티티는 이를 해결하기 위한 구체적인 'mechanism' 요소가 최소 1개 이상 바인딩되어야 합니다.")
            
        return values
```

---

## 3. `PydanticOutputParser` 연동 코어 파이프라인 (`tasks.py`)
LangChain의 PromptTemplate에 Few-Shot 예시와 부정 지시어를 결합하여, LLM이 처음부터 오염된 데이터를 생성할 확률을 획기적으로 낮춥니다.
```python
# backend/app/worker/tasks.py 내 추가 구현부
# backend/app/worker/tasks.py 내 추가 구현부
import time
import logging
from typing import List
from langchain_core.output_parsers import PydanticOutputParser
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import PromptTemplate

logger = logging.getLogger("pipeline")

# 무결성 검증 파서 인스턴스 초기화
parser = PydanticOutputParser(pydantic_object=ConceptExtractionSchema)

# Few-Shot과 강력한 제약 조건이 결합된 프롬프트 템플릿 정의
prompt_template = PromptTemplate(
    template="""
당신은 공식 문서 분석가이자 Neo4j 지식 그래프 아키텍트입니다.
아래 문서 청크(대상 환경: {framework}, {language})를 분석하여 핵심 기술 및 보안 개념을 완벽한 온톨로지 위계에 맞춰 적재할 수 있는 JSON 배열로만 응답하라. 스키마에 명시되지 않은 필드는 임의로 창작할 수 없다.

## [절대 엄수 제약 조건 - 위반 시 시스템 크래시 발생]
1. 노이즈 차단: 'This page is also available as Markdown', 'Was this helpful?', 'Last updated', 메뉴명, 링크 안내 등 기술 본문과 무관한 웹사이트 레이아웃 텍스트는 철저히 무시하라.
2. 명명 규칙 강제: 'concept_name'은 순수 파스칼케이스(PascalCase) 명사여야 한다. 접두사('concept_'), 해시 접미사('_b6ce44' 등), 프레임워크 이름('NextJs' 등)을 절대 포함하지 마라.
3. Null 처리: 문서 내용에 해당하는 정보가 없는 메타 필드는 키를 누락시키지 말고 반드시 'null' 또는 빈 배열('[]')로 명시하라.

## Neo4j 그래프 매핑 — 온톨로지 계층 및 다중 라벨 생성 헌법
1. [Concept 노드 축]: 'concept_name'이 병합 기준 마스터 키이다. 기술적 이론, 메커니즘의 상위 추상 개념, 취약점 유형 등 '순수 개념' 명칭이어야 한다.
   올바른 예시: CSRF, XSS, RateLimiting, MemoryLeak
   → [물리 다중 라벨 처리]: 허용 도메인 범주({allowed_domains}) 중 해당하는 것을 Capitalize하여 물리 다중 라벨로 처리.
2. [aliases]: 영문 Full Name, 영문 파스칼케이스, 한글 번역명, 약어를 포함하는 플랫 배열.
3. [Mechanism 노드 축]: 언어/프레임워크 종속적인 구체적 방어책. (명칭은 소문자 스네이크케이스 강제)
4. [CodeExample 노드 축]: Mechanism 하위 위계 종속. 실제 동작 가능한 현실적인 코드(`\\n` 개행 직렬화 포함)와 문맥(description)을 정밀 추출.

## 모범 출력 예시 (Few-Shot)
입력된 텍스트가 메모리 누수에 관한 것이라면 아래와 같이 출력해야 한다:
[
  {{
    "concept_name": "MemoryLeak",
    "concept_type": "performance_antipattern",
    "cwe_id": "CWE-401",
    "owasp_id": null,
    "severity": "high",
    "domains": ["performance", "security"],
    "description_ko": "메모리 누수는 더 이상 사용하지 않는 메모리를 해제하지 않아 힙이 지속 증가하는 안티패턴. 장기 운영 시 OOM 크래시 또는 DoS로 이어진다.",
    "aliases": ["Memory Leak", "Heap Growth", "OutOfMemory", "메모리 누수", "OOM"],
    "root_cause": "object_reference_retained_preventing_gc",
    "affected_components": ["long_running_worker", "cache_layer"],
    "mechanism": [
      {{
        "mechanism_name": "bounded_cache_eviction",
        "code_examples": [
          {{
            "lang": "python",
            "lang_version": ">=3.10",
            "framework": "fastapi",
            "framework_version": ">=0.100",
            "code": "from functools import lru_cache\\n@lru_cache(maxsize=512)\\ndef expensive(key: str) -> str:\\n    ...",
            "description": "maxsize 제한 + TTL 만료로 캐시 무한 증가 차단"
          }}
        ]
      }}
    ],
    "config_properties": [
      {{"key": "cache_max_size", "value": "512", "type": "tuning"}}
    ]
  }}
]

마크다운 래핑 기호 외에 어떠한 부연 설명 텍스트도 출력하지 마라.

---
[분석할 본문 청크 원문]
{chunk_text}
---

{format_instructions}
""",
    input_variables=["framework", "language", "allowed_domains", "chunk_text"],
    partial_variables={"format_instructions": parser.get_format_instructions()}
)

@celery_app.task
def extract_task(session_id: str, framework: str, language: str):
    _set_state(session_id, "EXTRACTING") # 5단계 상태 머신 진입
    
    doc_metadata = db.query(KnowledgeDocument).filter_by(session_id=session_id).first()
    allowed_domains = doc_metadata.allowed_domains if doc_metadata else []
    
    chunks: List[str] = get_cleaned_chunks_from_storage(session_id)
    app_mode = get_app_mode()
    
    # 환각 방지를 위해 일관성 100% 매핑 모드(temperature=0.0) 설정
    llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash", temperature=0.0)
    extracted_payloads = []
    
    for idx, chunk in enumerate(chunks):
        if app_mode == "PRODUCTION" and idx > 0:
            time.sleep(4) # 무료 티어 20 RPM 에러 우회용 하드 슬립
        if app_mode == "MOCK" and idx > 0:
            break
            
        try:
            # 선형 체인 결합 연산 수행
            chain = prompt_template | llm | parser
            
            # 밸리데이터를 통과한 완벽한 규격의 인스턴스 획득
            verified_data: ConceptExtractionSchema = chain.invoke({
                "framework": framework,
                "language": language,
                "allowed_domains": allowed_domains,
                "chunk_text": chunk
            })
            
            extracted_payloads.append(verified_data.dict())
            
        except Exception as e:
            # 스키마 요건 충족 실패 또는 모순 데이터 감지 시 적재 레이어를 차단하고 프로세스 폭파
            logger.error(f"❌ [Data Pollution Blocked] Chunk {idx+1} failed validation: {str(e)}")
            _set_state(session_id, "FAILED") # FAILED 클린 리부팅 트리거 가동
            raise e
            
    # 무결성이 100% 검증된 페이로드 셋만 디스크에 플러시
    write_staging_draft(session_id, extracted_payloads)
    _set_state(session_id, "EXTRACTED")
```

---

## 4. 파이프라인 연동 시 예외 통제 조건

* **온톨로지 유형 바인딩 가이드**: LLM이 `concept_type`을 매핑할 때, `mechanism`이나 `property` 등 도출된 레이어 유형에 맞춰 데이터 필드가 상호 보완적으로 채워졌는지 Pydantic 스키마가 실시간 인터락하는지 상시 검증한다.
* **429 레이트 리밋 예외 제어**: `PydanticOutputParser` 도입으로 인해 프롬프트의 길이가 늘어났으므로, 3~4만 자의 대용량 청킹 구조 표준을 철저히 유지하여 분당 총 호출 수 자체를 낮게 억제해야 한다.

