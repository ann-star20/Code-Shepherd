## **1. 프로젝트 개요 (Project Overview)**

* **프로젝트 명**: 에이전트 기반 보안·기술 지식 그래프 자동화 파이프라인 및 웹뷰  
  *(Knowledge Graph Extraction Agent Pipeline — Tech Issue & Solution KG)*  
* **목적**: 외부 프레임워크/언어의 공식 문서(URL)를 입력받아 보안 이슈 및 핵심 기술 개념을 자동으로 추출·구조화하고, 이를 PostgreSQL 및 Neo4j Graph DB에 실시간 적재하여 관리자에게 토폴로지 뷰와 인스펙터 형태로 시각화하는 에이전트 기반 자동화 파이프라인 구축.  
* **주요 가치**:  
  * 신규 프레임워크 버전 및 보안 명세 업데이트 시 수동 분석 공수 제거.  
  * LLM 기반 지식 추출을 통해 비정형 공식 문서로부터 표준화된 지식 그래프(Knowledge Graph) 형성.  
  * 비동기 처리를 통한 안정적인 대량 문서 파싱 및 시각적 영향도 분석.  
  * **확장 목표**: 보안(Security KG)에 국한하지 않고, 기술 이슈 & 솔루션 지식 그래프(Tech Issue & Solution KG)로 도메인 확장 가능한 구조 설계.

## **2. 타겟 유저 및 유즈케이스 (Target Users & Use Cases)**

* **타겟 유저**: 시니어 백엔드 엔지니어, 보안 검수 담당자, AI 서비스 아키텍트, 신입 사원 코드 검수 대응 부서.  
* **주요 유즈케이스**:  
  1. 관리자가 확장성 메타데이터(언어, 버전, 프레임워크 등)와 함께 공식 문서 URL들을 입력.  
  2. 시스템이 URL을 선행 스캔하여 메타데이터를 자동 추론 → 관리자가 검증/보완(Human-in-the-Loop).  
  3. 비동기 파이프라인이 트리거되어 백그라운드에서 크롤링 및 LLM 분석 수행.  
  4. 추출된 기술 개념을 기구축된 도메인 시드 데이터와 매핑 및 멱등성 기반 증분 업데이트(Merge).  
  5. 프론트엔드 대시보드를 통해 실시간 파이프라인 상태, 로그 콘솔, Neo4j 기반 4레이어 토폴로지 관계도 확인.

## **3. 핵심 기능 요구사항 (Functional Requirements)**

### **3.1. 메타데이터 수집 반자동화 — Human-in-the-Loop (Input Agent)**

URL 입력 직후, 파이프라인 본 실행 전에 선행 파싱 레이어(Pre-scan Layer)를 수행하여 관리자의 메타데이터 입력 부담을 최소화한다.

#### **3.1.1. 선행 파싱 레이어 (Auto-Inference)**

시스템이 입력된 URL을 경량 스캔하여 메타데이터를 자동으로 추론한다.

| 추론 소스 | 추론 대상 | 예시 |
| :---- | :---- | :---- |
| URL 경로 패턴 | 언어, 버전, 프레임워크 | en/6.0/topics/security/ → { lang: EN, version: 6.0, framework: Django } |
| HTML <meta> 태그 | 문서 제목, 언어 | <meta name="description">, <html lang="en"> |
| <title> / <h1> | 프레임워크명 키워드 매칭 | "Spring Security Reference" → framework: Spring |
| Sitemap / robots.txt | 버전 경로 구조 파악 | — |

#### **3.1.2. 휴먼 인 루프 검증 및 인터락 (Interlock Policy)**

* **자동 추론 성공 시**: 추론된 메타데이터를 입력 폼에 자동 채워넣고(Pre-fill), 관리자가 검토 후 확인(Confirm) 클릭으로 파이프라인 진행.  
* **자동 추론 실패 / 데이터 누락 시**: 파이프라인을 PENDING 상태로 일시 정지하고, 관리자가 프레임워크 / 버전 / 언어를 **직접 선택 또는 입력**해야만 다음 단계로 진행되는 인터락(Interlock)을 적용.  
* **인터락 UI 요소**: 입력 폼에 추론 신뢰도 표시(예: 자동 추론됨 ✓ / 수동 입력 필요 ⚠), 누락 필드 하이라이팅.

#### **3.1.3. 기타 Input Agent 정책**

* **다중 URL 지원**: 1개부터 최대 5개까지 동시 입력 및 대기열 추가.  
* **유효성 검증**: URL 형식 검사 및 ETag/변경 이력 분석을 통한 중복 수집 방지(Idempotency).  
* **확장성 메타데이터 필드**: SW 관련 개념, 프로그래밍 언어, 버전, 프레임워크 — 노드 속성으로 확장 가능하도록 설계.

#### **3.1.4. 문서 고유 식별자(doc_id) — 마스터 키 설계**

PostgreSQL documents 테이블과 Neo4j Document 노드 간의 **매핑 키**로 사용되는 마스터 키 체계를 정의한다. 동일 URL의 콘텐츠 변경 추적과 해시 충돌 방지를 동시에 달성한다.

* **구조**: doc_id = [출처_Prefix]_[정규화된_URL]_[콘텐츠_또는_ETag_SHA-256_앞_8자리]  
* **출처 Prefix 정의**:  
  * EXT: 외부 공식 문서 (인터넷 공개 URL - 예: Django Docs, Spring Docs)  
  * INT: 사내 지식 관리 시스템 (Internal Wiki - 예: Confluence, Notion)

import hashlib, re  
from urllib.parse import urlparse, urlunparse

def build_doc_id(prefix: str, url: str, content: str = None, etag: str = None) -> str:  
    parsed = urlparse(url)  
    normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))  
    url_part = re.sub(r"[:/.]", "-", normalized).strip("-")  
    raw = etag if etag else (content or "")  
    hash8 = hashlib.sha256(raw.encode()).hexdigest()[:8]  
    return f"{prefix}_{url_part}_{hash8}"

* **콘텐츠 변경 추적 및 Idempotency 규칙**:  
  * 동일 URL + 동일 해시 → doc_id 동일: PostgreSQL UPSERT 무시, Neo4j MERGE 무변화 (재처리 방지)  
  * 동일 URL + 다른 해시 → doc_id 신규: 신규 버전으로 적재, 이전 Document 노드 보존 (버전 히스토리)  
* **PostgreSQL documents 테이블 핵심 컬럼**:

CREATE TABLE IF NOT EXISTS documents (  
  doc_id           TEXT PRIMARY KEY,  
  source_prefix    TEXT NOT NULL,  
  original_url     TEXT NOT NULL,  
  content_hash     CHAR(8) NOT NULL,  
  etag             TEXT,  
  lang             TEXT,  
  framework        TEXT,  
  version          TEXT,  
  state            TEXT NOT NULL DEFAULT 'PENDING',  
  created_at       TIMESTAMPTZ DEFAULT now(),  
  updated_at       TIMESTAMPTZ,  
  CONSTRAINT documents_state_check CHECK (state IN ('PENDING','CRAWLING','EXTRACTED','COMMITTED','FAILED'))  
);

* **Neo4j Document 노드 구조 및 매핑 원칙**:  
  * doc_id는 양쪽 DB에서 **완전히 동일한 값**을 사용한다. 별도 매핑 테이블 없이 doc_id 하나로 직접 조인/탐색 가능.

MERGE (d:Document {id: "EXT_https---docs-djangoproject-com..._a3f9c21b"})  
ON CREATE SET  
  d.source_prefix  = "EXT",  
  d.original_url   = "[https://docs.djangoproject.com/en/6.0/topics/security/](https://docs.djangoproject.com/en/6.0/topics/security/)",  
  d.content_hash   = "a3f9c21b",  
  d.framework      = "Django",  
  d.version        = "6.0",  
  d.created_at     = timestamp()  
WITH d  
MATCH (c:Concept {name: "XSS"})  
MERGE (d)-[:REFERENCES]->(c)

### **3.2. 멀티링구얼 지원 및 로컬라이제이션 (Translation & Extraction)**

* **다국어 소스 분석**: 영어(EN) 및 한국어(KO) 문서를 모두 파싱하고 LLM 컨텍스트로 주입 가능해야 함.  
* **한국어 표준화 저장**: 원문이 영어이더라도, 최종 지식 그래프용 노드/관계의 description_ko 필드는 **반드시 한국어로 번역 및 요약**하여 저장.  
* **영문 표준 Key 유지**: 노드의 name(식별 키) 속성은 영문 표준 명칭/약어를 사용하여 다국어 혼선 방지 (→ 3.4절 그래프 표준화 정책 참조).

### **3.3. LLM 기반 구조화 컨셉 추출 (Extractor Agent)**

#### **3.3.1. 비용 최적화 모델**

대량의 텍스트 토큰 소비 비용을 절감하기 위해 gemini-2.5-flash 모델을 핵심 LLM으로 채택.

#### **3.3.2. 공식 문서 구조적 패턴 힌트 (Structural Hint)**

공식 문서가 공통적으로 따르는 서술 패턴(배경 ![][image1] 취약점/결함 기전 ![][image1] 영향도 ![][image1] 대응 설정/코드)을 프롬프트 힌트로 제공하여 추출 신뢰도를 높인다.

#### **3.3.3. 컨셉 추출 타겟 (Concept Extraction Target)**

단순 요약이 아닌, 아래 구조화된 컨셉 요소를 명시적으로 타겟팅하여 추출한다. 기성 프론트엔드 파이프라인에서 인입되는 구형 필드 명칭을 유연하게 바인딩하되 내부 물리 규격을 강제한다.

| 컨셉 요소 (물리 노드) | 가공 및 매핑 규칙 (소문자 계약) | 추출 및 예시 데이터 |
| :---- | :---- | :---- |
| **중앙 개념 허브** (:Concept) | 영문 표준 명칭 파스칼케이스 수렴 축 | XSS, SQLi, CSRF, MemoryLeak, ConnPoolExhaustion |
| **완화 메커니즘** (:Mechanism) | 완전 소문자 스네이크케이스 변환 및 강제 가공 | output_encoding, parameterized_query, connection_pooling |
| **제어 속성** (:Property) | unq_key, value, type 구조 분리 (type은 'security' | 'tuning') | unq_key: "secure_browser_xss_filter", value: "True", type: "security" |
| **말단 플레이북** (:CodeExample) | 부모 메커니즘 노드 하위에 1:N으로 귀속되는 실물 소스코드 스니펫 | 언어/버전, 프레임워크/버전 명세, 순수 소스코드 문자열 포함 |

* **Extractor Agent JSON 출력 스키마 명세**:

{  
  "concept_name": "XSS",  
  "concept_type": "vulnerability_root_cause",  
  "cwe_id": "CWE-79",  
  "owasp_category": "A03:2025",  
  "severity": "high",  
  "domains": ["security"],  
  "security_mechanism": [  
    {  
      "mechanism_name": "output_encoding",  
      "code_examples": [  
        {  
          "lang": "python",  
          "lang_version": ">=3.10",  
          "framework": "django",  
          "framework_version": ">=5.0",  
          "code": "html.escape(user_input)",  
          "description": "Django 템플릿 외부에서 사용자 입력을 안전하게 이스케이프"  
        }  
      ]  
    }  
  ],  
  "affected_components": ["template_rendering_layer", "api_response_serialization"],  
  "config_properties": [{"key": "secure_browser_xss_filter", "value": "True", "type": "security"}],  
  "root_cause": "사용자 입력값이 HTML 컨텍스트에서 이스케이프 처리 없이 출력됨",  
  "description_ko": "크로스 사이트 스크립팅은 공격자가 악성 스크립트를 ...",  
  "aliases": ["Cross-Site Scripting", "크로스 사이트 스크립팅"]  
}

#### **3.3.4. 온톨로지 매핑 기준 — 통합 Concept 허브 (Unified Concept Hub)**

* **설계 원칙 (4레이어 직주근접 구조)**: Concept 레이어는 도메인별로 쪼개지 않고 **단일 통합 허브**로 운영한다. 과거의 무거운 상위 유령 노드(OWASPCategory, CWE 등)를 전부 폐기하고 관련 분류 번호는 노드의 내부 속성(owasp_id, cwe_id)으로 통합 흡수한다.  
* **라벨링 규칙**: 도메인 귀속은 노드 복사 분리가 아닌 **물리적 다중 라벨(Multi-Label)** 체인으로 수렴 조인한다.

┌─────────────────┐                                      ┌─────────────────┐  
│  (d1:Domain)    │                                      │  (d2:Domain)    │  
│  name: 'security'                                      │  name: 'performance'  
└─────────────────┘                                      └─────────────────┘  
         │                                                        │  
         └──────────────────────────┬─────────────────────────────┘  
                                    │ [:BELONGS_TO] (인간 제어 재배선)  
                                    ▼  
                         ┌───────────────────────┐  
                         │ (c:Concept)           │   
                         │ :Security :Performance│ ◀── [통합 개념 허브 거점]  
                         │ name: 'MemoryLeak'    │     (owasp_id, cwe_id 속성 내장)  
                         └───────────────────────┘  
                                    │  
         ┌──────────────────────────┼──────────────────────────┐  
         │ [:CAUSED_BY]             │ [:MITIGATED_BY]          │ [:TUNED_BY]  
         ▼                          ▼                          ▼  
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐  
│ (r:RootCause)    │       │ (m:Mechanism)    │       │ (p:Property)     │  
│ name: 'raw_str'  │       │ name: 'p_query'  │       │ unq_key: 'p_max' │  
└──────────────────┘       └──────────────────┘       └──────────────────┘  
                                    │  
                                    │ [:HAS_EXAMPLE]  
                                    ▼  
                           ┌──────────────────┐  
                           │ (code:CodeExample)  
                           │ unq_id: '...'    │ ◀── [레이어 4: 버전별 위성 코드 독립 증분]  
                           └──────────────────┘

* **노드 레이블 설계**:  
  * Domain: 최상위 도메인 명찰 (name 고정: 'security', 'performance')  
  * Concept: 통합 허브 노드. 동적 멀티 라벨(:Security, :Performance) 레이어링 처리  
  * Mechanism: 개념적 완화 기법/치료제 허브 노드 (소문자 스네이크케이스)  
  * Property: 미들웨어/프레임워크 제어 파라미터 노드 (unq_key 식별자 매핑)  
  * CodeExample:![][image2]  
    버전별 소스코드 플레이북 위성 노드 (unq_id 복합 고유키)  
  * Document: 출처 문서 마스터 노드 (해싱 ID 체계 적용)  
* **다중 라벨 부여 규칙**:  
  * ["security"] 유입 ![][image1] (:Concept:Security)  
  * ["performance"] 유입 ![][image1] (:Concept:Performance)  
  * ["security","performance"] 유입 ![][image1] (:Concept:Security:Performance) (교차 도메인 수렴)

### **3.4. 그래프 데이터베이스 표준화 정책 (Neo4j Standardization Policy)**

#### **3.4.1. 영문 표준 명칭 규정**

Domain과 Concept 노드의 name 속성은 영문 표준 약어를 우선 사용한다. (예: XSS, SQLi, CSRF, MemoryLeak). 한국어 설명 및 번역명은 description_ko 및 aliases 배열 속성으로 격리 저장한다.

#### **3.4.2. 동의어/이명 처리 정책 (Alias & Deduplication)**

지식 파편화를 유도하는 SAME_AS 관계(Edge) 체계는 완전 폐기하며, 오직 노드 내부의 **aliases 속성(Property) 배열**로 단일화 통합한다.

* **중복 방지 선처리 레이어 (Deduplication Layer)**: Graph Writer가 작동하기 전, 유입된 개념 명칭이 기존 특정 노드의 aliases 배열에 존재함을 풀텍스트 인덱스(concept_aliases_fulltext_idx) 대조로 발견하면, 신규 노드를 생성하지 않고 해당 마스터 노드의 name으로 강제 수렴(MERGE)시킨다.

### **3.5. 지식 그래프 증분 적재 및 중복 방지 (Graph Writer Agent)**

* **MERGE 기반 증분 업데이트**: Neo4j MERGE 구문 + 개념 고유 식별자 name을 기둥 삼아 데이터 주도형으로 커밋한다. 동일 승인 데이터 이중 처리 시 원자적 데이터 복제 적재 없이 updated_at 타임스탬프만 단조 증가한다.  
* **관계 타입 정의**:

| 관계선 (Edge Type) | 출발 노드 (From) | 도착 노드 (To) | 카디널리티 및 관리 규칙 |
| :---- | :---- | :---- | :---- |
| BELONGS_TO | Concept | Domain | N : M (인간 어드민 수정 시 끊고 재배선) |
| MITIGATED_BY | Concept | Mechanism | N : M (추상 해결책 직결) |
| TUNED_BY | Concept | Property | N : M (정적 제어 속성 조인) |
| CAUSED_BY | Concept | RootCause | N : M (결함 유발 불씨 연결) |
| AFFECTS | Concept | Component | N : M (타격 물리/논리 레이어 지정) |
| HAS_EXAMPLE | Mechanism | CodeExample | 1 : N (개념 해결책 하위 위성 코드 매달기) |
| REFERENCES | Document | Concept | N : M (말단 가변 자산의 출처 역추적선) |

### **3.6. 초기 시드 데이터 구축 정책 (Dual-Domain Seed Data)**

시스템은 **보안(security)** 과 **성능(performance)** 두 도메인을 독립적인 온톨로지 서브트리로 분리하여 적재한다.

* **보안 도메인 시드 (security)**: OWASP Top 10 (2025) 및 핵심 개발 취약점 CWE 매핑 데이터를 초기 시드로 삼으며, 별도의 노드로 분리하지 않고 concepts 테이블 및 :Concept 노드의 owasp_id, cwe_id 속성 필드에 내장 적재한다.  
* **성능 도메인 시드 (performance)**: OWASP 가이드라인을 사용하지 않으며, CWE 자원관리 범주(CWE-400 계열) 및 백엔드 빈출 성능 안티패턴 4종(N+1Query, MissingIndex, ConnPoolExhaustion, MemoryLeak) 데이터를 마스터 속성 체계로 영속화한다.  
* 두 도메인 모두 동일한 Mechanism, Property, CodeExample 노드 레이어를 공유하며, Concept.domains 배열 및 물리 멀티 라벨로 귀속을 표현한다.

### **3.7. 백엔드 비동기 큐 아키텍처 (Asynchronous Pipeline)**

* **비동기 태스크 레이어**: 크롤링 및 LLM 추출 작업은 백그라운드에서 **Celery + Redis** 워커가 비동기로 이벤트를 전담 처리하여 HTTP 요청-응답 병목을 제거한다.  
* **태스크 상태 관리**: 각 태스크의 생명 주기는 PostgreSQL pipeline_logs 테이블에 영구 기록되어 대시보드 실시간 관제 소스로 활용된다.

### **3.8. 실시간 대시보드 및 뷰 (Frontend UI/UX)**

* **5단계 파이프라인 상태 표시**: Input ![][image1] Crawler ![][image1] Extractor ![][image1] Graph Writer ![][image1] Deduplication 단계별 실시간 인디케이터 구성.  
* **Human-in-the-Loop UI**: 메타데이터 추론 결과 확인 및 수동 입력 폼 (추론 신뢰도 배지, 누락 필드 경고).  
* **대화형 토폴로지 뷰**: 노드 타입별 색상 범례 동적 매핑, 클릭 시 인스펙터 패널 연동, 온톨로지 레이어 필터링 지원.

### **3.9. 상태 모델 기반 논리적 트랜잭션 분리 및 최종 승인 게이트**

운영 DB 락(Lock) 경쟁을 방지하기 위해, Extractor 출력을 즉시 운영 환경에 커밋하지 않고 스테이징 상태(DRAFT)로 분리 보관한다. 관리자가 프론트엔드에서 가상 미리보기를 확인하고 최종 승인을 눌러야만 원자적 적재가 실행된다.

#### **3.9.1. 상태(State) 머신 정의 확장**

* DRAFT: Extractor 완료, 스테이징 테이블 대기 (운영 DB 미반영 격리)  
* DOMAIN_PENDING: 레지스트리에 없는 신규 도메인 검출 상태 (파이프라인 정지 후 HITL 게이트 인터락 발동)  
* APPROVED: 관리자 검토 및 수정 승인 완료 (Celery 비동기 이행 대기열 적재)  
* COMMITTED: PostgreSQL 마스터 + Neo4j 실제 영속 반영 완료 (동기화 완전 종료)  
* REJECTED: 관리자 거부 (스테이징 내역 폐기)

#### **3.9.2. 스테이징 테이블 DDL 명세 (staging_concepts v2)**

CREATE TABLE IF NOT EXISTS staging_concepts (  
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),  
  session_id       UUID NOT NULL,  
  doc_id           TEXT REFERENCES documents(doc_id) ON DELETE CASCADE,  
  concept_json     JSONB NOT NULL,  
  state            TEXT NOT NULL DEFAULT 'DRAFT',  
  known_domains    TEXT[] DEFAULT '{}',  
  unknown_domains  TEXT[] DEFAULT '{}',  
  reviewed_at      TIMESTAMPTZ,  
  committed_at     TIMESTAMPTZ,  
  created_at       TIMESTAMPTZ DEFAULT now()  
);

#### **3.9.3. 런타임 신규 도메인 확장 처리 흐름 (HITL API 레이어)**

[Extractor Agent 완료]  
       │  
       ▼ ① 스테이징 적재 (concept_json 저장)  
[staging_concepts] (RDB 격리 보관, 운영 DB 락 없음)  
       │  
       ├─► [검증 연동]: domain_registry 테이블과 domains 배열 교차 대조  
       │      │  
       │      ├── [Case A]: 미등록 도메인 포함 시 (unknown_domains 존재)  
       │      │      │  
       │      │      ▼ state = 'DOMAIN_PENDING' (파이프라인 일시정지 인터락)  
       │      │   [관리자 대시보드 HITL 알림] ──► (매핑 / 신규 등록 / 거부 선택)  
       │      │                                        │ (복구 API 완료 시)  
       │      │                                        ▼  
       │      └── [Case B]: 모든 도메인 정상 등록 상태 (state = 'DRAFT')  
       │  
       ▼ SSE로 세션 ID + 가상 노드 메타데이터 프론트엔드 전송  
[프론트엔드 가상 미리보기]  
       │ * 기존 확정 데이터 + DRAFT(또는 DOMAIN_PENDING) 가상 병합  
       │ * 중복 노드 발견 시 "병합 예정" 가상 하이라이트 시각화  
       │ * 관리자 최종 검토: 노드별 승인(✓) / 거부(✗) 선택  
       ▼ ② POST /api/staging/{session_id}/approve  
[state → APPROVED] (Celery 비동기 큐 적재)  
       ▼ ③ 트랜잭션 경계 진입 (4대 커밋 규칙 원자 실행 - 단일·짧은 락)  
[PostgreSQL UPSERT] ──► concepts 마스터 테이블 반영 (domains TEXT[] 저장)  
[Neo4j MERGE]        ──► 물리 다중 라벨 결합 및 입구 단 중복 방지 적재 동시 만족  
       ▼ SSE로 최종 완료 이벤트 전송  
[프론트엔드 토폴로지 갱신] (가상 점선 노드가 실제 영속 실선 노드로 교체됨)

#### **3.9.4. 프론트엔드 가상 노드 미리보기 (Virtual Node Preview)**

관리자가 최종 승인 전에 실제 그래프에 적용됐을 때의 모습을 미리 확인할 수 있도록, 클라이언트 사이드에서 기존 Neo4j 데이터와 DRAFT 노드를 가상으로 병합하여 시각화한다. 도메인 색상은 domain_registry 오브젝트를 캐시한 후 런타임 동적 스타일 룩업을 수행한다.

* **가상 병합 렌더링 규칙**:  
  * 기존 확정 노드: 캐시 테마 컬러 반영 (실선, 불투명)  
  * 신규 DRAFT 노드: 테마 컬러 오버레이 강조 처리 (점선 테두리, 반투명 opacity: 0.65)  
  * 미등록 도메인 배지: 레지스트리 미등록 시 경고 스타일 뱃지 표출 및 수동 지정 UI 인터락 활성화  
  * 거부된 노드: 빨간 테두리, 블러(Blur) 처리, 클릭 액션 차단

### **4대 마스터 커밋 트랜잭션 규칙 (Core Pipeline Guard)**

#### **규칙 ① — 2단계 크로스 DB 트랜잭션 원자성 (Cross-DB Atomicity)**

RDB 마스터 테이블(concepts)과 NoSQL Graph DB(Neo4j)는 논리적으로 완전 결합된다. PostgreSQL 테이블 백엔드 Upsert 바인딩에 성공하더라도, 뒤이어 실행되는 Neo4j 쿼리가 커넥션 에러 등으로 실패하면 **PostgreSQL 트랜잭션을 강제로 롤백(Rollback)** 처리하고 로그 레이어에 경보를 트리거한다.

#### **규칙 ② — 멱등성 기반 자성 커밋 (Idempotent MERGE Commit)**

네트워크 지연 또는 워커 복구 시 중복 승인 태스크가 인입되어도 마스터 DB 데이터는 불변해야 한다. 최종 concepts 마스터 DDL의 concept_name 고유 인덱스와 Neo4j 내부의 Concept.name MERGE 속성 키를 기둥 삼아 데이터 주도형으로 커밋한다. 동일 승인 데이터 이중 처리 시 원자적 데이터 중복 적재 없이 updated_at 타임스탬프만 단조 증가한다.

* **concepts 마스터 적재 스키마**:

CREATE TABLE IF NOT EXISTS concepts (  
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),  
  concept_name   TEXT NOT NULL UNIQUE,  
  doc_id         TEXT REFERENCES documents(doc_id) ON DELETE SET NULL,  
  domains        TEXT[] NOT NULL,  
  concept_type   TEXT,  
  cwe_id         TEXT,  
  owasp_id       TEXT,  
  severity       TEXT,  
  description_ko TEXT,  
  aliases        TEXT[] NOT NULL DEFAULT '{}',  
  created_at     TIMESTAMPTZ DEFAULT now(),  
  updated_at     TIMESTAMPTZ  
);

#### **규칙 ③ — 후행 정합성 보장 트랜잭션 규칙**

개념 노드가 Neo4j 마스터에 최종 커밋 완료(COMMITTED) 처리되는 절차는, 백엔드 단독 스펙 가공 조건 하에 동적 라벨링 및 관계선(출처 문서 조인 및 Mechanism, Property 연결) 바인딩 연산이 무결하게 종료되어 오류 없이 리턴되는 시점을 완전한 커밋 프로세스의 종료로 간주한다.

#### **규칙 ④ — 소스 문서(Document) 상태 동기화 격리**

개념 바인딩 트랜잭션이 성공하는 즉시 출처 documents 테이블 레코드의 state를 'COMMITTED'로 원자적 일괄 업데이트 처리하여 대시보드 인디케이터 신뢰도를 동기화한다.

async def commit_to_master(session_id: str, approved_concepts: list):  
    async with pg_session.begin() as pg_tx:  
        await pg_tx.execute(upsert_concepts_sql, approved_concepts)  
        await neo4j_merge_concepts(approved_concepts)

        doc_ids = list({c["doc_id"] for c in approved_concepts})  
        await pg_tx.execute(  
            "UPDATE documents SET state='COMMITTED', updated_at=now() "  
            "WHERE doc_id = ANY(:doc_ids)",  
            {"doc_ids": doc_ids}  
        )  
        await pg_tx.execute(  
            "UPDATE staging_concepts SET state='COMMITTED' WHERE session_id=:sid",  
            {"sid": session_id}  
        )


## **5. 초기 마이그레이션 및 시드 스크립트 형상 관리 정책**

### **5.1. 코드 및 정책 격리 원칙**

시스템 초기화 및 데이터셋 구축을 위한 실행용 로우 스크립트(schema.sql, seed_data.sql, seed_data.cypher)는 본 PRD 문서에 직접 기술하여 관리하지 않는다. 대신 프로젝트 루트의 scripts/seed/ 디렉토리 하위에 독립된 물리 파일로 격리하여 Git 형상 관리 시스템을 통해 버전 제어한다.

scripts/  
  seed/  
    security/  
      schema.sql                   # PostgreSQL 테이블 DDL (IF NOT EXISTS)  
      seed_data.sql                # concepts 운영 테이블용 초기 보안 데이터 INSERT (CWE 및 OWASP ID는 속성으로 내장)  
      seed_data.cypher             # Neo4j 통합 :Concept 노드 및 완화 수단(:Mechanism), 도메인(:Domain) 관계 MERGE (독립 CWE/OWASP 노드 없음)  
    performance/  
      perf_antipattern_schema.sql  # 성능 도메인 PostgreSQL 확장 DDL  
      perf_seed_data.sql           # concepts 운영 테이블용 초기 성능 안티패턴 데이터 INSERT  
      perf_seed_data.cypher        # Neo4j 통합 :Concept 노드 및 완화 수단, 성능 도메인 관계 MERGE  
    verify_seed.py                 # 적재 후 정합성 검증 (노드 수, 고아 노드 탐지)

### **5.2. 멱등성(Idempotency) 보장**

모든 데이터베이스 스크립트는 중복 실행되거나 어떤 환경에서 가동되더라도 기존 데이터를 파괴하지 않고 무결성을 유지하도록 아래 멱등성 규격을 필수 준수한다.

| DB | 멱등성 구문 | 적용 대상 |
| :---- | :---- | :---- |
| **PostgreSQL** | CREATE TABLE IF NOT EXISTS | DDL 스크립트 전체 |
| **PostgreSQL** | ON CONFLICT (concept_name) DO NOTHING / DO UPDATE | INSERT 구문 전체 |
| **Neo4j** | MERGE ... ON CREATE SET ... ON MATCH SET | 노드/관계 생성 전체 |

### **5.3. 환경 불가지론적 재사용**

격리된 스크립트 자산은 소스코드 변경 없이 아래 3개 환경에서 동일하게 재사용된다.

| 재사용 환경 | 실행 방법 |
| :---- | :---- |
| **로컬 개발 환경 초기화** | psql $DATABASE_URL -f scripts/seed/security/schema.sql |
| **Phase 1 테스트 자동화** | conftest.py 픽스처에서 동일 파일 경로 참조 |
| **GCP Cloud SQL 이관** | 환경변수 DATABASE_URL만 교체 후 동일 명령 실행 |
