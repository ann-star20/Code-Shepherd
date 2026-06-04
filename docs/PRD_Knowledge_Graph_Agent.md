# 제품 요구사항 정의서 (PRD: Product Requirement Document)

**버전**: v1.2  
**최종 수정일**: 2026-06-04  
**변경 이력**:  
- v0.1 초안  
- v0.2 온톨로지 매핑, Human-in-the-Loop, 컨셉 추출 타겟, 영문 표준화/동의어 정책, 시드 데이터 고도화 추가  
- v0.3 상태(State) 모델 기반 논리적 트랜잭션 분리, 최종 승인 게이트, 프론트엔드 가상 노드 미리보기 추가  
- v0.4 이중 도메인 시드 데이터 정책 고도화: 보안(OWASP+CWE) / 성능(독자 PerfAntipatternCategory + CWE 자원관리) 분리, REF_TO 관계 추가, 4종 성능 안티패턴 시드 명세  
- v0.5 통합 Concept 허브 설계: Concept 레이어 단일화, 다중 라벨(Multi-Label)로 도메인 귀속 표현, 교차 도메인 MERGE Cypher 및 조회 패턴, LLM 출력 스키마 `concept_domain` 필드 추가  
- v0.6 문서 마스터 키(doc_id) 설계: `PREFIX_url_hash8` 체계, EXT/KMS Prefix, SHA-256 앞 8자리 콘텐츠 해시, PostgreSQL ↔ Neo4j 단일 키 매핑, 콘텐츠 변경 추적 및 Idempotency 규칙  
- v0.7 LangSmith 기반 LLM 평가 및 테스트 하네스 정책 추가 (3.10절): Pre-Eval 스키마 이탈률 0% 게이트, 하네스 통합 테스트 시나리오, 프로덕션 트레이싱 및 HITL 피드백 루프. 기술 스택·개발 순서(Phase 4 신설)에 반영  
- v0.8 컨테이너 인프라 정책 추가 (5.2~5.5절): 애플리케이션 3개 서비스만 컨테이너화(Stateless), 외부 인프라 분리, 환경변수 교체만으로 로컬↔GCP 전환, Cloud SQL Auth Proxy `--profile gcp` 설계  
- v0.9 신규 4개 섹션 추가: §9 마이그레이션 스크립트 형상 관리 정책, §10 QA 테스트 하네스 명세(레이어 A~D, T01~T08), §11 최종 승인 게이트 4대 커밋 규칙, §12 Git Conventional Commits 규칙, §13 Definition of Done  
- v1.0 §14 시스템 아키텍처 및 표준 폴더 레이아웃 추가: 고수준 컴포넌트 통신 다이어그램, 클린 아키텍처 레이어-테스트 경계 매핑, 백엔드 전체 디렉토리 명세, 프론트엔드 아토믹 디자인 레이아웃, 루트 모노레포 구조  
- v1.1 §15 시스템 다이어그램 명세 추가: 전체 아키텍처·액션 플로우(스윔레인)·스토리보드 6화면·PostgreSQL ERD 5테이블 전체 컬럼·GraphDB 온톨로지 구조·Cypher 명세(인덱스/시드/MERGE/관계/조회 패턴)  
- v1.2 §16 LLM 인프라 추상화 및 Mock 메커니즘 추가: ILLMClient DIP 인터페이스, GeminiClient(PROD)/MockClient(DEV) 구현체 코드 명세, factory APP_MODE 주입, 4종 Mock 고정 스펙, T09~T11 AAA 테스트 3종 추가 (총 11 passed)

---

## 1. 프로젝트 개요 (Project Overview)

- **프로젝트 명**: 에이전트 기반 보안·기술 지식 그래프 자동화 파이프라인 및 웹뷰  
  *(Knowledge Graph Extraction Agent Pipeline — Tech Issue & Solution KG)*
- **목적**: 외부 프레임워크/언어의 공식 문서(URL)를 입력받아 보안 이슈 및 핵심 기술 개념을 자동으로 추출·구조화하고, 이를 PostgreSQL 및 Neo4j Graph DB에 실시간 적재하여 관리자에게 토폴로지 뷰와 인스펙터 형태로 시각화하는 에이전트 기반 자동화 파이프라인 구축.
- **주요 가치**:
  - 신규 프레임워크 버전 및 보안 명세 업데이트 시 수동 분석 공수 제거.
  - LLM 기반 지식 추출을 통해 비정형 공식 문서로부터 표준화된 CWE 및 보안·기술 지식 그래프(Knowledge Graph) 형성.
  - 비동기 처리를 통한 안정적인 대량 문서 파싱 및 시각적 영향도 분석.
  - **확장 목표**: 보안(Security KG)에 국한하지 않고, 기술 이슈 & 솔루션 지식 그래프(Tech Issue & Solution KG)로 도메인 확장 가능한 구조 설계.

---

## 2. 타겟 유저 및 유즈케이스 (Target Users & Use Cases)

- **타겟 유저**: 시니어 백엔드 엔지니어, 보안 검수 담당자, AI 서비스 아키텍트, 신입 사원 코드 검수 대응 부서.
- **주요 유즈케이스**:
  1. 관리자가 확장성 메타데이터(언어, 버전, 프레임워크 등)와 함께 공식 문서 URL들을 입력.
  2. 시스템이 URL을 선행 스캔하여 메타데이터를 자동 추론 → 관리자가 검증/보완(Human-in-the-Loop).
  3. 비동기 파이프라인이 트리거되어 백그라운드에서 크롤링 및 LLM 분석 수행.
  4. 추출된 보안 개념을 기구축된 OWASP Top 10 / CWE 시드 데이터와 매핑 및 증분 업데이트(Merge).
  5. 프론트엔드 대시보드를 통해 실시간 파이프라인 상태, 로그 콘솔, Neo4j 기반 토폴로지 관계도 확인.

---

## 3. 핵심 기능 요구사항 (Functional Requirements)

### 3.1. 메타데이터 수집 반자동화 — Human-in-the-Loop (Input Agent)

URL 입력 직후, 파이프라인 본 실행 전에 **선행 파싱 레이어(Pre-scan Layer)**를 수행하여 관리자의 메타데이터 입력 부담을 최소화한다.

#### 3.1.1. 선행 파싱 레이어 (Auto-Inference)

시스템이 입력된 URL을 경량 스캔하여 메타데이터를 자동으로 추론한다.

| 추론 소스 | 추론 대상 | 예시 |
|-----------|-----------|------|
| URL 경로 패턴 | 언어, 버전, 프레임워크 | `en/6.0/topics/security/` → `{ lang: EN, version: 6.0, framework: Django }` |
| HTML `<meta>` 태그 | 문서 제목, 언어 | `<meta name="description">`, `<html lang="en">` |
| `<title>` / `<h1>` | 프레임워크명 키워드 매칭 | "Spring Security Reference" → framework: Spring |
| Sitemap / robots.txt | 버전 경로 구조 파악 | — |

#### 3.1.2. 휴먼 인 루프 검증 및 인터락 (Interlock Policy)

- **자동 추론 성공 시**: 추론된 메타데이터를 입력 폼에 자동 채워넣고(Pre-fill), 관리자가 검토 후 확인(Confirm) 클릭으로 파이프라인 진행.
- **자동 추론 실패 / 데이터 누락 시**: 파이프라인을 `PENDING` 상태로 일시 정지하고, 관리자가 프레임워크 / 버전 / 언어를 **직접 선택 또는 입력**해야만 다음 단계로 진행되는 인터락(Interlock)을 적용.
- **인터락 UI 요소**: 입력 폼에 추론 신뢰도 표시(예: `자동 추론됨 ✓` / `수동 입력 필요 ⚠`), 누락 필드 하이라이팅.

#### 3.1.3. 기타 Input Agent 정책

- **다중 URL 지원**: 1개부터 최대 5개까지 동시 입력 및 대기열 추가.
- **유효성 검증**: URL 형식 검사 및 ETag/변경 이력 분석을 통한 중복 수집 방지(Idempotency).
- **확장성 메타데이터 필드**: SW 관련 개념, 프로그래밍 언어, 버전, 프레임워크 — 노드 속성으로 확장 가능하도록 설계.

#### 3.1.4. 문서 고유 식별자(doc_id) — 마스터 키 설계

PostgreSQL `documents` 테이블과 Neo4j `Document` 노드 간의 **매핑 키**로 사용되는 마스터 키 체계를 정의한다. 동일 URL의 콘텐츠 변경 추적과 해시 충돌 방지를 동시에 달성한다.

**구조**:
```
doc_id = [출처_Prefix]_[정규화된_URL]_[콘텐츠_또는_ETag_SHA-256_앞_8자리]
```

**출처 Prefix 정의**:

| Prefix | 출처 유형 | 예시 대상 |
|--------|-----------|-----------|
| `EXT` | 외부 공식 문서 (인터넷 공개 URL) | Django Docs, Spring Docs, OWASP |
| `KMS` | 사내 지식 관리 시스템 (Internal Wiki 등) | Confluence, Notion, 사내 위키 |

확장 시 `GH`(GitHub), `PDF` 등 추가 Prefix를 등록하여 출처 유형 확장 가능.

**생성 규칙**:

```python
import hashlib, re
from urllib.parse import urlparse, urlunparse

def build_doc_id(prefix: str, url: str, content: str = None, etag: str = None) -> str:
    # 1. URL 정규화 (scheme + netloc + path, 쿼리/앵커 제거)
    parsed = urlparse(url)
    normalized = urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))
    # URL-safe 치환 (슬래시·점·콜론 → 하이픈)
    url_part = re.sub(r"[:/.]", "-", normalized).strip("-")

    # 2. 콘텐츠 해시 (ETag 우선, 없으면 본문 SHA-256)
    raw = etag if etag else (content or "")
    hash8 = hashlib.sha256(raw.encode()).hexdigest()[:8]

    return f"{prefix}_{url_part}_{hash8}"

# 예시
# EXT_https---docs-djangoproject-com-en-6-0-topics-security-_a3f9c21b
# KMS_https---wiki-internal-sec-xss_7e2b04d1
```

**예시**:

| 출처 | URL | doc_id |
|------|-----|--------|
| 외부 문서 | `https://docs.djangoproject.com/en/6.0/topics/security/` | `EXT_https---docs-djangoproject-com-en-6-0-topics-security-_a3f9c21b` |
| 사내 문서 | `https://wiki.internal/sec/xss` | `KMS_https---wiki-internal-sec-xss_7e2b04d1` |
| 동일 URL, 내용 변경 후 | `https://docs.djangoproject.com/en/6.0/topics/security/` | `EXT_https---docs-djangoproject-com-en-6-0-topics-security-_9d1e7fa0` |

**콘텐츠 변경 추적 및 Idempotency 규칙**:

| 조건 | 결과 |
|------|------|
| 동일 URL + 동일 해시 → `doc_id` 동일 | PostgreSQL UPSERT 무시, Neo4j MERGE 무변화 (재처리 방지) |
| 동일 URL + 다른 해시 → `doc_id` 신규 | 신규 버전으로 적재, 이전 Document 노드 보존 (버전 히스토리) |

**PostgreSQL `documents` 테이블 핵심 컬럼**:

```sql
CREATE TABLE documents (
  doc_id         TEXT PRIMARY KEY,          -- 마스터 키: PREFIX_url_hash8
  source_prefix  TEXT NOT NULL,             -- EXT | KMS | ...
  original_url   TEXT NOT NULL,
  content_hash   CHAR(8) NOT NULL,          -- SHA-256 앞 8자리
  etag           TEXT,                      -- HTTP ETag (있을 경우 우선 사용)
  lang           TEXT,                      -- EN | KO
  framework      TEXT,
  version        TEXT,
  state          TEXT DEFAULT 'PENDING',    -- PENDING | CRAWLING | EXTRACTED | COMMITTED | FAILED
  created_at     TIMESTAMPTZ DEFAULT now(),
  updated_at     TIMESTAMPTZ
);
CREATE INDEX ON documents(source_prefix, state);
CREATE INDEX ON documents(original_url, content_hash);
```

**Neo4j `Document` 노드 구조**:

```cypher
MERGE (d:Document {doc_id: "EXT_https---docs-djangoproject-com..._a3f9c21b"})
ON CREATE SET
  d.source_prefix  = "EXT",
  d.original_url   = "https://docs.djangoproject.com/en/6.0/topics/security/",
  d.content_hash   = "a3f9c21b",
  d.framework      = "Django",
  d.version        = "6.0",
  d.created_at     = timestamp()

// Document → Concept 관계 (추출된 개념의 출처 추적)
MERGE (d)-[:SOURCED_FROM]->(c:Concept {name: "XSS"})
```

**PostgreSQL ↔ Neo4j 매핑 원칙**:
- `doc_id`는 양쪽 DB에서 **완전히 동일한 값**을 사용한다. 별도 매핑 테이블 없이 `doc_id` 하나로 직접 조인/탐색 가능.
- Neo4j `Document` 노드는 `doc_id`에 인덱스를 생성하여 `SOURCED_FROM` 역방향 탐색(어떤 문서에서 이 Concept이 추출됐는가)을 빠르게 지원한다.

```cypher
CREATE INDEX document_doc_id FOR (d:Document) ON (d.doc_id)
```

---

### 3.2. 멀티링구얼 지원 및 로컬라이제이션 (Translation & Extraction)

- **다국어 소스 분석**: 영어(EN) 및 한국어(KO) 문서를 모두 파싱하고 LLM 컨텍스트로 주입 가능해야 함.
- **한국어 표준화 저장**: 원문이 영어이더라도, 최종 지식 그래프용 노드/관계의 `description` 및 `summary` 필드는 **반드시 한국어로 번역 및 요약**하여 저장.
- **영문 표준 Key 유지**: 노드의 `name`(식별 키) 속성은 영문 표준 명칭/약어를 사용하여 다국어 혼선 방지 (→ 3.5절 그래프 표준화 정책 참조).

---

### 3.3. LLM 기반 구조화 컨셉 추출 (Extractor Agent)

#### 3.3.1. 비용 최적화 모델

대량의 텍스트 토큰 소비 비용을 절감하기 위해 `gemini-2.5-flash` 모델을 핵심 LLM으로 채택.

#### 3.3.2. 공식 문서 구조적 패턴 힌트 (Structural Hint)

공식 문서가 공통적으로 따르는 서술 패턴을 프롬프트 힌트로 제공하여 추출 신뢰도를 높인다.

```
[공식 문서 범용 서술 패턴]
1. 배경 (Background)       — 개념 정의 및 문맥 소개
2. 취약점 기전 (Mechanism) — 취약점이 발생하는 원인 및 공격 흐름
3. 영향도 (Impact)         — 피해 범위, 영향을 받는 컴포넌트
4. 대응 설정 / 코드 (Mitigation) — 프레임워크별 설정값, 코드 스니펫, 권장 패턴
```

이 패턴을 Few-shot 예시 또는 System Instruction으로 프롬프트에 주입하여, LLM이 임의 요약이 아닌 구조화된 스키마로 응답하도록 유도한다.

#### 3.3.3. 컨셉 추출 타겟 (Concept Extraction Target)

단순 요약이 아닌, 아래 **4가지 구조화된 컨셉 요소**를 명시적으로 타겟팅하여 추출한다.

| 컨셉 요소 | 설명 | 추출 예시 |
|-----------|------|-----------|
| **보안 메커니즘** (Security Mechanism) | 취약점을 방어하는 기술적 수단 | CSRF Token, Content Security Policy, Parameterized Query |
| **취약점 원인** (Vulnerability Root Cause) | 취약점이 발생하는 근본 원인 | 사용자 입력 미검증, 세션 고정, 안전하지 않은 역직렬화 |
| **설정 속성** (Configuration Property) | 프레임워크 설정 키/값 및 옵션 | `SESSION_COOKIE_SECURE=True`, `X-Frame-Options: DENY` |
| **영향 받는 컴포넌트** (Affected Component) | 취약점의 영향 범위 | 인증 모듈, 세션 관리, ORM 레이어, API 엔드포인트 |

**프롬프트 출력 스키마 (JSON)**:
```json
{
  "concept_name": "XSS",
  "concept_type": "vulnerability_root_cause",
  "cwe_id": "CWE-79",
  "owasp_category": "A03:2021",
  "severity": "HIGH",
  "security_mechanisms": ["Output Encoding", "Content Security Policy"],
  "affected_components": ["템플릿 렌더링 레이어", "API 응답 직렬화"],
  "config_properties": [{"key": "SECURE_BROWSER_XSS_FILTER", "value": "True"}],
  "root_cause": "사용자 입력값이 HTML 컨텍스트에서 이스케이프 처리 없이 출력됨",
  "description_ko": "크로스 사이트 스크립팅은 공격자가 악성 스크립트를 ...",
  "aliases": ["Cross-Site Scripting", "크로스 사이트 스크립팅"]
}
```

#### 3.3.4. 온톨로지 매핑 기준 — 통합 Concept 허브 (Unified Concept Hub)

**설계 원칙**: `Concept` 레이어는 도메인별로 쪼개지 않고 **단일 통합 허브**로 운영한다. 보안 분류(`OWASPCategory`)와 성능 분류(`PerfAntipatternCategory`) 양쪽이 동일한 `Concept` 레이어로 수렴한다. 도메인 귀속은 노드 분리가 아닌 **다중 라벨(Multi-Label)**로 표현한다.

**이유**: `MemoryLeak`처럼 보안 취약점(CWE-401 자원 미해제)이자 성능 안티패턴(GC 부하)이기도 한 개념이 존재한다. 도메인별로 Concept을 분리하면 동일 개념이 중복 노드로 생성되고, 후속 병합(Link Resolver)이 필요해진다. 통합 허브 + 다중 라벨이 근본 해결책이다.

```
[Domain:Security]                    [Domain:Performance]
      │                                      │
      ▼ BELONGS_TO                           ▼ BELONGS_TO
[OWASPCategory]                  [PerfAntipatternCategory]
      │                                      │
      ▼ MAPS_TO                              ▼ REF_TO (선택적)
  [CWE: 보안]                           [CWE: 자원관리]
      │                                      │
      └──────────── INSTANTIATED_BY ─────────┘
                             │
                             ▼
              ┌──────────────────────────┐
              │   Concept (통합 허브)     │
              │  :Concept:Security       │  ← 보안 전용
              │  :Concept:Performance    │  ← 성능 전용
              │  :Concept:Security       │  ← 교차 도메인
              │  :Concept:Performance    │    (예: MemoryLeak)
              └──────────────────────────┘
                    │         │        │
          MITIGATED_BY   CAUSED_BY   AFFECTS ...
```

**노드 레이블 설계**:

| 노드 레이블 | 설명 | 식별 키 |
|-------------|------|---------|
| `Domain` | 최상위 도메인 (`Security`, `Performance`) | `name` (영문) |
| `OWASPCategory` | OWASP Top 10 항목 (보안 도메인 전용) | `owasp_id` (예: A03:2021) |
| `PerfAntipatternCategory` | 독자 성능 안티패턴 분류 (성능 도메인 전용, OWASP 미사용) | `name` |
| `CWE` | CWE 번호 기반 취약점/결함 분류 (양 도메인 참조) | `cwe_id` (예: CWE-79, CWE-400) |
| `Concept` | **통합 허브** — 보안·성능 공용 단일 레이어. 다중 라벨로 도메인 귀속 표현 | `name` (영문 약어) |
| `SecurityMechanism` | 대응 보안 메커니즘 | `name` |
| `RootCause` | 취약점/결함 근본 원인 | `name` |
| `Component` | 영향 받는 소프트웨어 컴포넌트 | `name` |
| `ConfigProperty` | 프레임워크 설정 키 | `key` |
| `Framework` | 수집 대상 프레임워크 (양 도메인 공유) | `name` + `version` |

**다중 라벨 부여 규칙**:

| 추출 도메인 | 부여 라벨 | 예시 |
|-------------|-----------|------|
| 보안 문서에서 추출 | `:Concept:Security` | `XSS`, `SQLi`, `CSRF` |
| 성능 문서에서 추출 | `:Concept:Performance` | `N+1Query`, `MissingIndex` |
| 양쪽 모두 해당 | `:Concept:Security:Performance` | `MemoryLeak`, `ConnPoolExhaustion` |

**교차 도메인 MERGE Cypher** (Tag Node 방식 — APOC 불필요):

```cypher
// 1. Concept 노드 생성 또는 병합
MERGE (c:Concept {name: "MemoryLeak"})
ON CREATE SET
  c.aliases        = ["Memory Leak", "메모리 누수"],
  c.cwe_id         = "CWE-401",
  c.description_ko = "객체 참조 미해제로 인한 GC 부하 및 힙 메모리 소진",
  c.created_at     = timestamp()
ON MATCH SET
  c.updated_at     = timestamp()

// 2. 도메인 Tag 연결 (누적 추가 — 기존 관계 삭제 없음)
WITH c
UNWIND ["Security", "Performance"] AS tag_name
  MERGE (t:Tag {name: tag_name})
  MERGE (c)-[:TAGGED_WITH]->(t)
```

**조회 패턴** (Tag Node 방식):
```cypher
// 보안 도메인 Concept만 조회
MATCH (c:Concept)-[:TAGGED_WITH]->(:Tag {name: "Security"}) RETURN c

// 성능 도메인 Concept만 조회
MATCH (c:Concept)-[:TAGGED_WITH]->(:Tag {name: "Performance"}) RETURN c

// 교차 도메인 Concept ("보안이면서 성능이기도 한" 노드)
MATCH (c:Concept)-[:TAGGED_WITH]->(:Tag {name: "Security"})
WHERE (c)-[:TAGGED_WITH]->(:Tag {name: "Performance"})
RETURN c

// "MemoryLeak" + 보안 컨텍스트
MATCH (c:Concept {name: "MemoryLeak"})-[:TAGGED_WITH]->(:Tag {name: "Security"}) RETURN c

// aliases 포함 전체 검색
MATCH (c:Concept) WHERE "메모리 누수" IN c.aliases RETURN c
```

**Extractor Agent 도메인 태그 결정 로직**:
Extractor가 LLM 결과 JSON에서 `concept_domain` 필드를 반환하면, Graph Writer가 아래 매핑으로 Tag를 연결한다.

```python
DOMAIN_TAG_MAP = {
    "security":     ["Security"],
    "performance":  ["Performance"],
    "both":         ["Security", "Performance"],
}
```

프롬프트 출력 스키마에 `concept_domain` 필드를 추가한다:
```json
{
  "concept_name": "MemoryLeak",
  "concept_domain": "both",          // "security" | "performance" | "both"
  "concept_type": "vulnerability_root_cause",
  ...
}
```

---

### 3.4. 그래프 데이터베이스 표준화 정책 (Neo4j Standardization Policy)

#### 3.4.1. 영문 표준 명칭 규정

`Domain`과 `Concept` 노드의 `name` 속성(MERGE 기준 식별 키)은 **영문 표준 약어**를 우선 사용한다.

| ❌ 비표준 | ✅ 표준 |
|----------|--------|
| Cross-Site Scripting | XSS |
| Cross-Site Request Forgery | CSRF |
| SQL Injection | SQLi |
| Server-Side Request Forgery | SSRF |

- `description_ko`(한국어 설명) 및 `aliases` 배열은 별도 속성으로 저장하여 검색 및 다국어 조회에 활용.

#### 3.4.2. 동의어/이명 처리 정책 (Alias & Deduplication)

동일 개념이 다양한 표현으로 등장할 경우 중복 노드 생성을 원천 차단한다.

- **`aliases` 배열 속성**: 노드 내부에 동의어/이명을 배열로 저장.
  ```cypher
  // 예시
  MERGE (c:Concept {name: "XSS"})
  ON CREATE SET c.aliases = ["Cross-Site Scripting", "크로스 사이트 스크립팅"]
  ON MATCH SET c.aliases = c.aliases + [alias for alias in [...] if alias not in c.aliases]
  ```
- **`SAME_AS` 관계**: 이미 별도 노드로 생성된 동의어 간에는 `SAME_AS` 관계를 형성하고 Link Resolver Agent가 최종 병합 처리.
- **Extractor Agent 사전 체크**: LLM 추출 결과를 Graph Writer에 전달하기 전, 기존 노드의 `aliases` 목록과 대조하여 동의어 여부를 확인하는 전처리 레이어 추가.

---

### 3.5. 지식 그래프 증분 적재 및 중복 방지 (Graph Writer Agent)

- **MERGE 기반 증분 업데이트**: Neo4j `MERGE` 구문 + 고유 키(CWE 번호, 개념 `name`) 기반으로 기존 노드 속성 업데이트 및 신규 관계만 추가 (중복 노드 생성 절대 방지).
- **관계 타입 정의**:

| 관계 | 방향 | 의미 |
|------|------|------|
| `BELONGS_TO` | Concept → OWASPCategory | OWASP 분류 소속 (보안 도메인) |
| `MAPS_TO` | OWASPCategory → CWE | CWE 번호 매핑 (보안 도메인) |
| `REF_TO` | PerfAntipatternCategory → CWE | CWE 자원관리 선택적 참조 (성능 도메인, MAPS_TO와 구분) |
| `MITIGATED_BY` | Concept → SecurityMechanism | 대응 메커니즘 |
| `CAUSED_BY` | Concept → RootCause | 취약점/결함 원인 |
| `AFFECTS` | Concept → Component | 영향 컴포넌트 |
| `CONFIGURED_BY` | Concept → ConfigProperty | 관련 설정 속성 |
| `RELATED_TO` | Concept ↔ Concept | 연관 개념 |
| `SAME_AS` | Concept ↔ Concept | 동의어/이명 |
| `IMPLEMENTS` | Framework → Concept | 프레임워크 구현 관계 (양 도메인 공유) |

---

### 3.6. 초기 시드 데이터 구축 정책 (Dual-Domain Seed Data)

시스템은 **보안(Security)** 과 **성능(Performance)** 두 도메인을 독립적인 온톨로지 서브트리로 분리하여 적재한다. 두 도메인은 `Domain` 루트 노드 아래 격리되며, 온톨로지 혼용 없이 각자의 분류 기준을 따른다.

#### 3.6.1. 보안 도메인 시드 (Security Domain)

웹 애플리케이션 보안 취약점 식별을 위해 **OWASP Top 10 (2021 기준)** 소프트웨어 개발 파트 및 관련 CWE 매핑 데이터를 초기 시드로 사전 적재한다.

전체 CWE 데이터셋 대신 SW 개발 취약점과 직결되는 범위만 선별하여 적재 부하를 최소화한다.

| 시드 데이터 | 출처 | Neo4j 적재 대상 |
|-------------|------|----------------|
| OWASP Top 10 (2021) A01 ~ A10 | OWASP | `OWASPCategory` 노드 10개 |
| CWE SW Development View (CWE-699) | MITRE CWE | SW 개발 결함 패턴 CWE 노드 약 40~60개 |
| CWE Top 25 Most Dangerous (2023) | MITRE CWE | 핵심 취약점 CWE 노드 25개 |
| OWASP ↔ CWE 매핑 관계 | OWASP Mapping | `MAPS_TO` 관계 일괄 적재 |

**온톨로지 계층**: `Domain(Security)` → `OWASPCategory` → `CWE` → `Concept`

**보안 도메인 시드 Concept 예시**:

| name (영문 표준) | owasp_id | cwe_id | severity |
|-----------------|----------|--------|----------|
| XSS | A03:2021 | CWE-79 | HIGH |
| SQLi | A03:2021 | CWE-89 | CRITICAL |
| CSRF | A01:2021 | CWE-352 | HIGH |
| BrokenAccessControl | A01:2021 | CWE-284 | CRITICAL |
| InsecureDeserialization | A08:2021 | CWE-502 | HIGH |

#### 3.6.2. 성능 도메인 시드 (Performance Domain)

성능 결함 식별을 위해 **OWASP 가이드라인을 사용하지 않으며**, CWE의 자원 관리 범주(CWE-400 계열) 및 백엔드 빈출 성능 안티패턴을 정의한 **독자적인 성능 지식 분류 체계(`PerfAntipatternCategory`)**를 시드 데이터로 활용한다.

**온톨로지 계층**: `Domain(Performance)` → `PerfAntipatternCategory` → `CWE(자원관리, 선택적)` → `Concept`

**성능 도메인 4종 핵심 안티패턴 시드**:

| name (영문 표준) | perf_category | 연관 CWE | 설명 (한국어) |
|-----------------|---------------|----------|--------------|
| `N+1Query` | ORM 성능 | CWE-1072 | ORM 관계 조회 시 N번 추가 쿼리 발생으로 인한 DB 과부하 |
| `MissingIndex` | DB 쿼리 | CWE-1052 | 인덱스 미설정으로 인한 Full Table Scan 및 응답 지연 |
| `ConnPoolExhaustion` | 자원 관리 | CWE-400 | 커넥션 반환 실패 또는 풀 설정 미흡으로 인한 커넥션 고갈 |
| `MemoryLeak` | 자원 관리 | CWE-401 | 객체 참조 미해제로 인한 GC 부하 및 힙 메모리 소진 |

**`PerfAntipatternCategory` 노드 설계**:
```json
{
  "name": "PerfAntipatternCategory",
  "label": "PerfAntipatternCategory",
  "domain": "Performance",
  "authority": "internal",
  "description_ko": "OWASP와 무관한 독자 성능 안티패턴 분류 체계. 백엔드 빈출 성능 결함 패턴을 정의한다.",
  "aliases": ["Performance Anti-pattern", "성능 안티패턴"]
}
```

**보안 도메인과의 격리 원칙**:
- `PerfAntipatternCategory` 노드는 `OWASPCategory`와 어떠한 관계도 형성하지 않는다.
- 성능 도메인의 CWE 참조는 `MAPS_TO` 대신 `REF_TO`(선택적 참조) 관계를 사용하여 보안 CWE 매핑과 명확히 구분한다.
- 두 도메인 간 유일하게 허용되는 공유 노드는 `Framework` 노드이다 (`IMPLEMENTS` 관계를 통해 양쪽 Concept에 연결 가능).

#### 3.6.3. 시드 적재 스크립트 구조

```
scripts/
  seed/
    security/
      owasp_top10.json          # OWASP A01~A10 OWASPCategory 노드 정형 데이터
      cwe_sw_dev_view.json      # CWE-699 SW Development View 선별 목록
      cwe_top25.json            # CWE Top 25 (2023)
      security_concepts.json    # 보안 Concept 시드 (XSS, SQLi, CSRF 등)
    performance/
      perf_antipattern_category.json  # PerfAntipatternCategory 노드 정의
      perf_concepts.json              # 성능 Concept 시드 (N+1Query 등 4종+)
      cwe_resource_mgmt.json          # CWE-400 계열 자원관리 참조 목록
    seed_postgres.py            # PostgreSQL concepts + staging_concepts 스키마 초기화
    seed_neo4j.py               # Neo4j MERGE 기반 양 도메인 노드/관계 일괄 적재
    verify_seed.py              # 적재 후 정합성 검증 (노드 수, 관계 수, 고아 노드 탐지)
```

---

### 3.7. 백엔드 비동기 큐 아키텍처 (Asynchronous Pipeline)

- **비동기 태스크 레이어**: 다중 URL 크롤링 및 LLM 추출 작업은 대기 시간이 길어질 수 있으므로 뒷단에 **Celery + Redis**를 도입하여 백그라운드 워커가 이벤트를 처리. HTTP 요청-응답 병목을 제거.
- **태스크 상태 관리**: 각 태스크는 `PENDING → RUNNING → SUCCESS / FAILED` 상태를 PostgreSQL `pipeline_logs` 테이블에 기록하여 프론트엔드 실시간 상태 조회에 활용.

---

### 3.8. 실시간 대시보드 및 뷰 (Frontend UI/UX)

- **5단계 파이프라인 상태 표시**: `Input` → `Crawler` → `Extractor` → `Graph Writer` → `Link Resolver` 단계별 실시간 인디케이터.
- **Human-in-the-Loop UI**: 메타데이터 추론 결과 확인 및 수동 입력 폼 (추론 신뢰도 배지, 누락 필드 경고).
- **실시간 런타임 로그**: WebSocket / SSE 기반 백그라운드 로그 콘솔 출력.
- **대화형 토폴로지 뷰**: 노드 타입별 색상 범례, 클릭 시 인스펙터 연동, 온톨로지 계층 필터링.
- **컨셉 인스펙터 패널**: 등급(CRITICAL, HIGH), 프레임워크, 컨셉 타입(보안 메커니즘/취약점 원인/설정 속성/영향 컴포넌트)별 필터링 및 상세 대응 방안 조회.
- **가상 노드 미리보기 및 최종 승인 UI**: → 3.9절 참조.

---

### 3.9. 상태 모델 기반 논리적 트랜잭션 분리 및 최종 승인 게이트

DB 커넥션 풀 고갈 및 테이블 락(Lock) 으로 인한 시스템 행(Hang)을 방지하기 위해, Extractor 출력을 즉시 운영 DB에 반영하지 않고 **스테이징 상태(DRAFT)** 로 분리 보관한다. 관리자가 프론트엔드에서 가상 미리보기를 확인하고 **최종 승인**을 눌러야만 운영 DB에 반영된다.

#### 3.9.1. 상태(State) 정의

| 상태 | 의미 | DB 반영 |
|------|------|---------|
| `DRAFT` | Extractor 완료, 스테이징 테이블 대기 | ❌ 운영 DB 미반영 |
| `APPROVED` | 관리자 승인 완료, Celery 큐 적재 | ✅ 반영 예정 |
| `COMMITTED` | PostgreSQL + Neo4j 실제 반영 완료 | ✅ 완료 |
| `REJECTED` | 관리자 거부, 스테이징 레코드 삭제 | ❌ 폐기 |

#### 3.9.2. 스테이징 테이블 설계 (`staging_concepts`)

Extractor 출력은 운영 `concepts` 테이블이 아닌 **별도 스테이징 테이블**에만 적재하여 운영 DB 락과 커넥션 풀 점유를 원천 차단한다.

```sql
CREATE TABLE staging_concepts (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id  UUID NOT NULL,           -- 파이프라인 실행 단위
  concept_json JSONB NOT NULL,         -- Extractor 원본 출력
  state        TEXT NOT NULL DEFAULT 'DRAFT',  -- DRAFT | APPROVED | COMMITTED | REJECTED
  reviewed_at  TIMESTAMPTZ,
  committed_at TIMESTAMPTZ,
  created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON staging_concepts(session_id, state);
```

- 스테이징 테이블은 운영 테이블과 **트랜잭션을 공유하지 않는다.**
- `DRAFT` 상태의 레코드는 운영 DB(concepts, Neo4j)에 일절 접근하지 않으므로 락 경쟁이 발생하지 않는다.

#### 3.9.3. 논리적 트랜잭션 분리 흐름

```
[Extractor 완료]
    │
    ▼  ① 스테이징 적재 (state=DRAFT)
[staging_concepts]  ← 운영 DB 비접촉, 커넥션풀 미사용
    │
    │  SSE로 세션 ID + DRAFT 목록 프론트엔드 전송
    ▼
[프론트엔드 가상 미리보기]
    │  기존 Neo4j 노드 + DRAFT 노드를 클라이언트에서 병합 렌더링
    │  관리자 검토: 노드별 승인 ✓ / 거부 ✗ 선택
    ▼  ② POST /api/staging/{session_id}/approve
[state → APPROVED]
    │  승인된 항목만 Celery 큐에 적재
    ▼  ③ 트랜잭션 경계 진입 (단일·짧은 락)
[PostgreSQL UPSERT]  → concepts 테이블, state=COMMITTED
[Neo4j MERGE]        → 노드/관계 증분 업데이트
    │
    ▼  SSE로 완료 이벤트 전송
[프론트엔드 토폴로지 갱신]  가상 노드 → 실제 노드로 교체
```

**커넥션 풀 보호 원칙**:
- ① 스테이징 적재: 스테이징 테이블 단순 INSERT, 커넥션 즉시 반환.
- ② 상태 전이: 단일 `UPDATE staging_concepts SET state='APPROVED'`, 락 범위 최소.
- ③ 운영 반영: 승인된 노드만 배치 처리, 단일 트랜잭션으로 PostgreSQL UPSERT + Neo4j MERGE 순차 실행. 락 점유 시간을 수초 이내로 제한.

#### 3.9.4. 프론트엔드 가상 노드 미리보기 (Virtual Node Preview)

관리자가 최종 승인 전에 **실제 그래프에 적용됐을 때의 모습**을 미리 확인할 수 있도록, 클라이언트 사이드에서 기존 Neo4j 데이터와 DRAFT 노드를 **가상으로 병합**하여 시각화한다. 실제 DB는 변경되지 않는다.

**가상 병합 렌더링 규칙**:

| 노드 유형 | 시각 처리 |
|-----------|-----------|
| 기존 확정 노드 | 기본 스타일 (실선, 불투명) |
| 신규 DRAFT 노드 | 점선 테두리, 반투명(opacity 0.65), 색상 강조 |
| DRAFT ↔ 기존 중복 (SAME_AS 후보) | 오버레이 배지 "병합 예정" + 연결선 강조 |
| 거부된 노드 | 빨간 테두리, 흐리게, 클릭 불가 |

**인터랙션**:
- 가상 노드 클릭 → 우측 인스펙터 패널에서 컨셉 상세 확인 및 개별 승인/거부 토글.
- 세션 전체 일괄 승인 버튼 `✓ 전체 승인` / `✗ 전체 거부` 제공.
- 승인 전 diff 요약: "신규 노드 N개 / 속성 업데이트 M개 / 병합(SAME_AS) K개".

**데이터 흐름 (클라이언트)**:
```
GET /api/graph/topology          → 기존 확정 노드/엣지 목록
GET /api/staging/{session_id}    → DRAFT 노드 목록
                                 ↓ 클라이언트 병합
react-force-graph 렌더링         → 가상 통합 그래프 표시
POST /api/staging/{session_id}/approve  → 최종 승인 전송
```

#### 3.9.5. 최종 승인 API 명세

| 메서드 | 엔드포인트 | 설명 |
|--------|-----------|------|
| `GET` | `/api/staging/{session_id}` | DRAFT 노드 목록 조회 |
| `PATCH` | `/api/staging/{session_id}/nodes/{node_id}` | 개별 노드 상태 변경 (APPROVED / REJECTED) |
| `POST` | `/api/staging/{session_id}/approve` | 세션 전체 승인 → Celery 큐 적재 |
| `POST` | `/api/staging/{session_id}/reject` | 세션 전체 거부 → 스테이징 레코드 삭제 |
| `GET` | `/api/staging/{session_id}/diff` | 승인 시 예상 변경 diff 요약 반환 |

---

### 3.10. LangSmith 기반 LLM 평가 및 테스트 하네스 정책

LLM 호출 품질을 **개발 전 사전 검증 → 통합 테스트 → 프로덕션 실시간 추적**의 3단계로 관리한다. 프롬프트 자산은 관리자 피드백과 함께 지속적으로 환류(Feedback Loop)되어 시스템이 스스로 개선되는 구조를 목표로 한다.

#### 3.10.1. 선행 프롬프트 평가 (Pre-Eval)

파이프라인 코드 작성 전, LangSmith 데이터셋을 활용하여 `gemini-2.5-flash` 모델의 프롬프트를 사전 검증한다. **스키마 이탈률 0%를 달성한 프롬프트만 프로덕션 코드에 반영**한다.

**평가 대상 및 기준**:

| 평가 항목 | 측정 지표 | 합격 기준 |
|-----------|-----------|-----------|
| JSON 스키마 준수율 | 필수 필드 누락률, 타입 불일치율 | 이탈률 0% |
| `concept_domain` 정확도 | `security` / `performance` / `both` 분류 정확도 | ≥ 95% |
| 한국어 번역 정합성 | 원문 의미 보존율 (사람 검토 + LLM-as-Judge) | ≥ 90% |
| 4종 컨셉 타겟 추출율 | 보안메커니즘·취약점원인·설정속성·영향컴포넌트 추출 누락 여부 | 누락 0% |

**LangSmith 데이터셋 구성**:

```
langsmith_datasets/
  extractor_schema_eval/
    golden_inputs/       # 대표 공식 문서 청크 (영문 15개 + 한국어 5개)
    expected_outputs/    # 기대 JSON 스키마 출력 (정답 레이블)
  translation_eval/
    en_ko_pairs/         # 영문 원문 ↔ 한국어 정답 번역 쌍
```

**평가 실행 흐름**:

```
[프롬프트 후보 작성]
    │
    ▼
[LangSmith Eval 실행]
    │  langsmith_datasets/extractor_schema_eval 로드
    │  gemini-2.5-flash 호출 → 실제 출력 생성
    │  JSON Schema Validator → 스키마 이탈 여부 판정
    │  LLM-as-Judge → 번역 정합성 점수 산출
    ▼
[결과 리포트]
    │  이탈률 0% + 번역 ≥ 90% → 프로덕션 반영 승인
    │  기준 미달 → 프롬프트 수정 후 재평가 (반복)
    ▼
[승인된 프롬프트 → prompts/ 디렉토리에 버전 태그로 저장]
```

#### 3.10.2. 하네스 기반 통합 테스트 (Test Harness)

Celery 비동기 태스크 및 하이브리드 DB 적재 로직은 **독립된 테스트 하네스 환경**에서 구동하여 레이스 컨디션 및 DB 락 유무를 물리적으로 검증한다. 프로덕션 DB를 사용하지 않아 데이터 오염 위험 없이 실제 I/O 흐름을 재현한다.

**하네스 환경 구성**:

```
tests/
  harness/
    docker-compose.test.yml  # 격리된 PostgreSQL + Neo4j + Redis 컨테이너
    conftest.py              # 하네스 픽스처 (DB 초기화, 시드 데이터 주입)
    test_celery_pipeline.py  # 비동기 태스크 레이스 컨디션 검증
    test_db_write_gate.py    # 트랜잭션 경계 및 락 타임아웃 검증
    test_neo4j_merge.py      # MERGE 멱등성 및 다중 라벨 누적 검증
```

**핵심 검증 시나리오**:

| 시나리오 | 검증 목표 | 판정 기준 |
|----------|-----------|-----------|
| 동일 `doc_id` 병렬 제출 | UPSERT 충돌 없이 단일 레코드 유지 | 레코드 중복 0건 |
| DRAFT 상태에서 운영 DB 미접촉 | `staging_concepts` 외 테이블 쓰기 발생 여부 | 쓰기 이벤트 0건 |
| Neo4j `MERGE` 반복 실행 | 동일 `Concept` 노드 중복 생성 방지 | 노드 수 불변 |
| 다중 라벨 누적 부여 | 기존 라벨 제거 없이 신규 라벨 추가 확인 | 라벨 집합 단조 증가 |
| Celery Worker 2개 동시 실행 | 동일 `staging_concepts` 레코드 이중 처리 방지 | 최종 COMMITTED 1건 |

#### 3.10.3. 프로덕션 실시간 추적 및 피드백 루프 (Production Tracing & Feedback Loop)

배포 후 **모든 에이전트의 LLM API 호출을 LangSmith에 실시간 트레이싱**하며, Human-in-the-Loop 단계에서 관리자가 수정한 피드백 데이터를 프롬프트 자산으로 환류한다.

**트레이싱 범위**:

| 에이전트 | 추적 데이터 | LangSmith 태그 |
|----------|-------------|----------------|
| Extractor Agent | 프롬프트 입력·출력, 토큰 수, 지연시간 | `extractor`, `doc_id`, `framework` |
| Link Resolver Agent | 유사도 판단 입력·출력 | `resolver`, `concept_name` |
| Human-in-the-Loop | 관리자 수정 전·후 diff | `hitl`, `session_id`, `reviewer` |

**피드백 루프 흐름**:

```
[프로덕션 Extractor 호출]
    │  LangSmith Run 자동 기록 (langchain 콜백 또는 SDK wrap)
    ▼
[Human-in-the-Loop 승인/수정 단계]
    │  관리자가 DRAFT 노드를 수정한 경우:
    │  수정 전 JSON ↔ 수정 후 JSON diff → LangSmith Feedback으로 기록
    ▼
[피드백 누적 → 데이터셋 환류]
    │  수정 빈도 높은 패턴 → extractor_schema_eval 데이터셋에 추가
    │  번역 오류 수정 사례 → translation_eval 데이터셋에 추가
    ▼
[Pre-Eval 재실행 → 프롬프트 개선 사이클]
```

**LangSmith 연동 구현 지침**:

```python
from langsmith import traceable
from langsmith.wrappers import wrap_openai  # Gemini는 OpenAI 호환 엔드포인트 사용

@traceable(name="extractor_agent", tags=["extractor"])
async def extract_concepts(doc_id: str, text_chunk: str) -> dict:
    # gemini-2.5-flash 호출 — Run이 LangSmith에 자동 기록됨
    response = await llm.ainvoke(prompt)
    return response

# Human-in-the-Loop 수정 피드백 기록
from langsmith import Client
client = Client()
client.create_feedback(
    run_id=run_id,
    key="hitl_correction",
    score=0,           # 0 = 수정 필요했던 출력
    comment=f"before: {before_json}, after: {after_json}"
)
```

**모니터링 알림 기준**:

| 지표 | 경보 임계값 | 조치 |
|------|-------------|------|
| 스키마 이탈 Run 발생 | 1건 이상 / 1시간 | Slack 알림 + 해당 Run LangSmith 링크 첨부 |
| HITL 수정률 | ≥ 20% / 세션 | 프롬프트 재평가 트리거 |
| 평균 토큰 수 | ≥ 기준치 150% | 청크 분할 전략 재검토 알림 |

---

## 4. 비기능 요구사항 (Non-Functional Requirements)

- **확장성(Scalability)**: 보안 도메인에 국한하지 않고 Tech Issue & Solution KG로 확장 가능하도록 `Domain` 노드 기반 다도메인 구조 설계.
- **성능(Performance)**: Neo4j Indexing (`name`, `cwe_id`, `aliases`) 및 PostgreSQL 관계 최적화.
- **멱등성(Idempotency)**: 동일 URL 반복 요청 시 LLM 토큰 중복 소모 방지를 위한 캐싱 레이어 확보.
- **감사 추적(Auditability)**: 파이프라인 각 단계의 입/출력 스냅샷을 PostgreSQL에 기록하여 추출 결과 검증 가능.
- **DB 안전성(DB Safety)**: 스테이징 테이블 분리로 운영 DB 커넥션 풀 고갈 및 테이블 락 위험 원천 차단. 최종 승인 게이트(Commit Gate) 이전에는 운영 DB 쓰기 트랜잭션 미발생을 시스템 설계 원칙으로 강제.
- **LLM 품질 보증(LLM Quality Gate)**: 프롬프트는 LangSmith Pre-Eval을 통해 스키마 이탈률 0% 기준을 통과한 버전만 프로덕션에 반영. 프로덕션 HITL 수정률 ≥ 20% 발생 시 프롬프트 재평가 사이클 자동 트리거 (→ 3.10절 참조).

---

## 5. 기술 스택 및 인프라 정책 (Technical Stacks & Infrastructure)

### 5.1. 기술 스택

| 영역 | 기술 |
|------|------|
| **Backend** | Python 3.11+, FastAPI, Celery, Redis |
| **Databases** | PostgreSQL (정형 메타데이터 및 상태 관리), Neo4j (지식 그래프 모델링) |
| **AI/LLM** | Google Gemini API (`gemini-2.5-flash`) |
| **LLM 평가/추적** | LangSmith (Pre-Eval 데이터셋, 프로덕션 트레이싱, HITL 피드백 루프) |
| **Frontend** | React, TypeScript, Vite, Tailwind CSS |
| **Graph 시각화** | `react-force-graph` 또는 `cytoscape.js` |
| **실시간 통신** | WebSocket / SSE (FastAPI 내장) |
| **컨테이너** | Docker, Docker Compose (애플리케이션 서비스 레이어 전용) |

### 5.2. 컨테이너 구성 원칙 — 애플리케이션 서비스 레이어만 컨테이너화

`docker-compose.yml`은 **순수 애플리케이션 서비스 3개만** 관리한다. PostgreSQL·Neo4j·Redis는 외부 독립 인프라로 격리하며, `docker-compose.yml`이 직접 기동하지 않는다.

```
┌─────────────────────────────────────────────────────┐
│              docker-compose.yml 관리 범위             │
│                                                     │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  │
│  │ backend  │  │celery_worker │  │  frontend    │  │
│  │ FastAPI  │  │  Celery      │  │  React/Vite  │  │
│  │ :8000    │  │  Worker      │  │  :3000       │  │
│  └────┬─────┘  └──────┬───────┘  └──────────────┘  │
│       │               │                             │
│  (GCP profile only)   │                             │
│  ┌────┴───────────┐   │                             │
│  │cloud-sql-proxy │   │                             │
│  │127.0.0.1:5432  │   │                             │
│  └────────────────┘   │                             │
└───────────────────────┼─────────────────────────────┘
                        │  환경변수만 교체
        ┌───────────────┼─────────────────┐
        ▼               ▼                 ▼
  PostgreSQL        Neo4j             Redis
  (외부 인프라)    bolt://...        redis://...
  로컬 컨테이너     로컬 컨테이너     로컬 컨테이너
  → Cloud SQL Auth  → Neo4j Aura     → Memorystore
    Proxy (GCP)       (운영)           (GCP)
```

**서비스별 역할**:

| 서비스 | 이미지 | 역할 |
|--------|--------|------|
| `backend` | `./backend/Dockerfile` | FastAPI 앱 서버. REST API, SSE, 승인 게이트 |
| `celery_worker` | `./backend/Dockerfile` (공용) | 비동기 파이프라인 실행 (Crawler→Extractor→Graph Writer→Link Resolver) |
| `frontend` | `./frontend/Dockerfile` | React/Vite 정적 서빙 또는 개발 서버 |
| `cloud-sql-proxy` | `gcr.io/cloud-sql-connectors/cloud-sql-proxy` | GCP 운영 시 Cloud SQL IAM 중계. `--profile gcp` 전용 |

### 5.3. 완전 무상태(Stateless) 컨테이너 및 인프라 분리 정책

**컨테이너 무상태화**: 애플리케이션 서비스 레이어(`backend`, `frontend`, `celery_worker`)는 내부 데이터 영속성 결합을 100% 제거한 무상태(Stateless) 아키텍처로 구현한다. 컨테이너가 재시작·교체·스케일 아웃되어도 데이터 일관성에 영향을 주지 않는다.

**인프라 불가지론적 전환성**: RDB(PostgreSQL), GraphDB(Neo4j), 캐시/브로커(Redis) 등 모든 데이터 플랫폼은 외부 독립 인프라로 격리한다. 개발 환경의 로컬 외부 컨테이너망과 운영 환경의 Cloud SQL 및 관리형 인프라 간의 스위칭을 백엔드 코드 수정 없이 **인프라 런타임 환경변수(`DATABASE_URL`, `NEO4J_URI`, `REDIS_URL`) 교체만으로** 완벽하게 수용한다.

### 5.4. 환경별 전환 방법 (Environment Switching)

환경 전환은 `.env` 심볼릭 링크 교체 한 줄로 완료된다. 애플리케이션 코드를 건드리지 않는다.

**로컬 개발 환경** (외부 로컬 컨테이너 `bolt://`, `redis://`, `postgresql://` 직접 연결):

```bash
ln -sf .env.local .env
docker compose --profile local up -d
```

**GCP 운영 환경** (Cloud SQL Auth Proxy + Memorystore + Neo4j Aura):

```bash
ln -sf .env.prod .env
docker compose --profile gcp up -d   # cloud-sql-proxy 컨테이너 추가 기동
```

**핵심 환경변수 — 인프라 주소만 다르고 키 이름은 동일**:

| 환경변수 | 로컬 값 예시 | GCP 운영 값 예시 |
|----------|-------------|-----------------|
| `DATABASE_URL` | `postgresql+asyncpg://...@host.docker.internal:5432/kg_db` | `postgresql+asyncpg://...@127.0.0.1:5432/kg_db` (Proxy 경유) |
| `NEO4J_URI` | `bolt://host.docker.internal:7687` | `neo4j+s://xxxx.databases.neo4j.io` (Aura) |
| `REDIS_URL` | `redis://host.docker.internal:6379/0` | `redis://10.x.x.x:6379/0` (Memorystore) |
| `CELERY_BROKER_URL` | `redis://host.docker.internal:6379/0` | `redis://10.x.x.x:6379/0` |

### 5.5. GCP Cloud SQL Auth Proxy 보안 연결 구조

퍼블릭 IP를 열지 않고 IAM 서비스 계정 인증을 통해 Cloud SQL에 안전하게 접속한다.

```
backend 컨테이너
  │  DATABASE_URL=postgresql://...@127.0.0.1:5432/...
  ▼
cloud-sql-proxy 컨테이너 (--profile gcp 전용)
  │  127.0.0.1:5432 수신
  │  GOOGLE_APPLICATION_CREDENTIALS=/secrets/sa-key.json
  ▼
Cloud SQL (asia-northeast3)
  IAM 인증 + TLS — 퍼블릭 IP 불필요
```

**docker-compose.yml 프록시 서비스 핵심 설정**:

```yaml
cloud-sql-proxy:
  image: gcr.io/cloud-sql-connectors/cloud-sql-proxy:latest
  profiles: [gcp]                           # --profile gcp 없이는 기동 안 됨
  command: >
    --address 0.0.0.0 --port 5432
    ${CLOUD_SQL_INSTANCE}                   # my-project:region:instance-name
  volumes:
    - ${GCP_SERVICE_ACCOUNT_KEY_PATH}:/secrets/sa-key.json:ro
  environment:
    GOOGLE_APPLICATION_CREDENTIALS: /secrets/sa-key.json
  ports:
    - "127.0.0.1:5432:5432"                 # 호스트 외부 노출 없음
```

**각 서비스를 개별 컨테이너로 분리하는 이유**:

| 관점 | 이유 |
|------|------|
| 독립 스케일 아웃 | `celery_worker`만 인스턴스 수를 늘려도 `backend`에 영향 없음 |
| 독립 배포 | 프론트엔드 변경 시 백엔드 재시작 불필요 |
| 장애 격리 | Worker 크래시가 API 서버 가용성에 영향 없음 |
| CI/CD 분리 | 서비스별 독립 이미지 빌드·푸시 파이프라인 구성 가능 |
| 무상태 보장 | 컨테이너가 영속 데이터를 갖지 않아 언제든 교체 가능 |

---

## 6. 에이전트 파이프라인 상세 아키텍처 흐름

```
[사용자 입력]
    │  URL 1~5개
    ▼
[선행 파싱 레이어 — Pre-scan]
    │  URL 경로 패턴 + HTML 메타 스캔 → 메타데이터 자동 추론
    ▼
[Human-in-the-Loop 검증]
    │  추론 성공 → Pre-fill + Confirm
    │  추론 실패 → PENDING + 관리자 수동 입력 (Interlock)
    ▼
[1단계] Input Agent
    │  유효성 검사, ETag 중복 체크, 대기열 추가
    ▼
[2단계] Crawler Agent
    │  DOM 파싱 → 불필요 태그 제거 → 텍스트 블록 분류
    ▼
[3단계] Extractor Agent
    │  gemini-2.5-flash 호출
    │  힌트: 배경→기전→영향도→대응코드 패턴
    │  타겟: 보안메커니즘 / 취약점원인 / 설정속성 / 영향컴포넌트
    │  출력: 구조화 JSON + 한국어 번역
    ▼
[4단계] Graph Writer Agent
    │  aliases 동의어 중복 체크 → PostgreSQL 적재
    │  Neo4j MERGE 증분 업데이트 (온톨로지 매핑 기준)
    ▼
[5단계] Link Resolver Agent
    │  SAME_AS 관계 탐색 → 벡터 유사도 병합 → 노드 최종 확정
    ▼
[결과]
    대시보드: 토폴로지 뷰 + 컨셉 인스펙터 + 실시간 로그
```

### 단계별 상세

| 단계 | 에이전트 | 주요 처리 내용 |
|------|----------|---------------|
| Pre-scan | — | URL 메타데이터 자동 추론, Human-in-the-Loop 인터락 |
| 1 | Input Agent | URL 유효성 검증, 중복 방지, 메타데이터 확정 |
| 2 | Crawler Agent | DOM 파싱, 텍스트 정제, 청크 분류 |
| 3 | Extractor Agent | LLM 추출, 4종 컨셉 타겟팅, 한국어 번역, JSON 스키마화 |
| 4 | Graph Writer Agent | aliases 중복 체크, PostgreSQL 적재, Neo4j MERGE |
| 5 | Link Resolver Agent | SAME_AS 탐색, 유사도 병합, 관계 최종 확정 |

---

## 7. 데이터 모델 개요 (Data Model Overview)

### PostgreSQL 주요 테이블

| 테이블명 | PK / 주요 컬럼 | 설명 |
|----------|---------------|------|
| `documents` | `doc_id TEXT PK` (`PREFIX_url_hash8`) | 수집 대상 URL 메타데이터. 마스터 키로 Neo4j `Document` 노드와 1:1 매핑. `source_prefix`, `original_url`, `content_hash`, `etag`, `framework`, `version`, `state` |
| `pipeline_logs` | `id UUID PK` | 단계별 처리 로그. `doc_id FK`, agent, level, message, timestamp |
| `staging_concepts` | `id UUID PK` | Extractor 출력 임시 보관. `doc_id FK`, `concept_json`, state(DRAFT→APPROVED→COMMITTED\|REJECTED) |
| `concepts` | `id UUID PK` | 관리자 최종 승인 후 반영된 개념 정형 데이터. `doc_id FK`, `concept_name`, `cwe_id`, severity, aliases, `description_ko` |
| `concept_snapshots` | `id UUID PK` | Extractor 출력 원본 JSON 스냅샷 (감사 추적). `doc_id FK` |

**`doc_id` 매핑 원칙**: `documents.doc_id` = Neo4j `Document.doc_id`. 별도 매핑 테이블 없이 동일 값으로 양방향 직접 참조. `pipeline_logs`, `staging_concepts`, `concepts` 모두 `doc_id`를 FK로 보유하여 특정 문서의 전체 처리 이력을 단일 키로 추적 가능.

**상태 전이 원칙**: `staging_concepts`의 레코드가 `COMMITTED` 되기 전까지 운영 `concepts` 테이블과 Neo4j에는 어떠한 쓰기도 발생하지 않는다. DB 커넥션 풀과 테이블 락을 Staging 단계에서 완전히 격리한다.

### Neo4j 노드/관계 모델 — 통합 Concept 허브

| 구분 | 내용 |
|------|------|
| **노드 레이블** | `Domain`, `OWASPCategory`, `PerfAntipatternCategory`, `CWE`, `Concept`(통합 허브), `SecurityMechanism`, `RootCause`, `Component`, `ConfigProperty`, `Framework` |
| **Concept 다중 라벨** | `:Concept:Security` / `:Concept:Performance` / `:Concept:Security:Performance` (교차 도메인) |
| **관계 타입** | `BELONGS_TO`, `MAPS_TO`, `REF_TO`, `INSTANTIATED_BY`, `MITIGATED_BY`, `CAUSED_BY`, `AFFECTS`, `CONFIGURED_BY`, `RELATED_TO`, `SAME_AS`, `IMPLEMENTS` |
| **MERGE 식별 키** | `Concept.name` (영문 약어, 도메인 무관 단일 키), `CWE.cwe_id`, `OWASPCategory.owasp_id` |
| **Neo4j Index** | `CREATE INDEX concept_name FOR (c:Concept) ON (c.name)` · `CREATE INDEX concept_aliases FOR (c:Concept) ON (c.aliases)` |

**교차 도메인 Concept 예시**:

| name | 라벨 | 비고 |
|------|------|------|
| `XSS` | `:Concept:Security` | 보안 전용 |
| `N+1Query` | `:Concept:Performance` | 성능 전용 |
| `MemoryLeak` | `:Concept:Security:Performance` | CWE-401 — 보안 + 성능 교차 |
| `ConnPoolExhaustion` | `:Concept:Security:Performance` | 자원 고갈 — 보안 + 성능 교차 |

---

## 8. 개발 순서 (Development Phases)

### Phase 1 — Backend Core
1. PostgreSQL + Neo4j 스키마 설계 및 마이그레이션 (`staging_concepts` 포함)
2. OWASP Top 10 / CWE SW Dev View / CWE Top 25 시드 데이터 적재 스크립트
3. FastAPI 라우터 구성 (URL 입력 API, Pre-scan API, 파이프라인 트리거 API)
4. Celery + Redis 비동기 태스크 구성 및 상태 관리
5. **[LangSmith]** 테스트 하네스 환경 구성 (`docker-compose.test.yml`, DB 픽스처)

### Phase 2 — Agent Pipeline
6. Pre-scan Layer: URL 패턴 파싱 + HTML 메타 추론 + Human-in-the-Loop API
7. Crawler Agent: 웹 크롤링 및 텍스트 정제
8. **[LangSmith]** Pre-Eval 실행: `extractor_schema_eval` 데이터셋 구성 → `gemini-2.5-flash` 프롬프트 후보 평가 → 스키마 이탈률 0% 달성 프롬프트 확정
9. Extractor Agent: 확정 프롬프트 적용, 4종 컨셉 타겟, `concept_domain` 필드 포함 JSON 추출 → `staging_concepts` DRAFT 적재. LangSmith `@traceable` 래핑
10. 최종 승인 게이트 API (`/approve`, `/reject`, `/diff`) 구현
11. Graph Writer Agent: APPROVED 항목 → `concept_domain` 기반 다중 라벨 결정 → `MERGE` 단일 노드 → `apoc.create.addLabels` 라벨 누적 → state = COMMITTED
12. Link Resolver Agent: SAME_AS 탐색, 유사도 기반 노드 병합. LangSmith 트레이싱 적용
13. **[LangSmith]** 하네스 통합 테스트 실행: 레이스 컨디션, DB 락, MERGE 멱등성, 다중 라벨 누적 검증

### Phase 3 — Frontend
14. React + TypeScript + Vite 프로젝트 셋업
15. Human-in-the-Loop 메타데이터 검증 UI (추론 신뢰도 배지, 인터락 폼)
16. 파이프라인 5단계 상태 인디케이터 컴포넌트
17. WebSocket/SSE 기반 실시간 로그 콘솔
18. 가상 노드 미리보기: `GET /api/graph/topology` + `GET /api/staging/{session_id}` 클라이언트 병합 렌더링
19. 승인 UI: DRAFT 노드 점선/반투명 스타일, 개별 승인/거부 토글, diff 요약, 최종 승인 버튼
20. react-force-graph 토폴로지 뷰 (온톨로지 계층 필터, 색상 범례, COMMITTED 후 가상→실제 노드 전환)
21. 컨셉 인스펙터 패널 (4종 컨셉 타입 필터 + 상세 대응 방안)

### Phase 4 — 프로덕션 모니터링 (LangSmith)
22. **[LangSmith]** HITL 수정 피드백 기록: 관리자 수정 diff → `client.create_feedback()` 연동
23. **[LangSmith]** 피드백 환류: 수정 빈도 높은 패턴 → `extractor_schema_eval` 데이터셋 추가 → Pre-Eval 재실행
24. **[LangSmith]** 모니터링 알림 설정: 스키마 이탈 1건/시간 → Slack, HITL 수정률 ≥ 20% → 프롬프트 재평가 트리거

---

## 9. 초기 마이그레이션 및 시드 스크립트 형상 관리 정책

### 9.1. 코드 및 정책 격리 원칙

시스템 초기화 및 데이터셋 구축을 위한 실행용 로우 스크립트(`schema.sql`, `seed_data.sql`, `seed_data.cypher`)는 본 PRD 문서에 직접 기술하여 관리하지 않는다. 대신 프로젝트 루트의 `scripts/seed/` 디렉토리 하위에 독립된 물리 파일로 격리하여 Git 형상 관리 시스템을 통해 버전 제어한다.

```
scripts/
  seed/
    security/
      schema.sql                   # PostgreSQL 테이블 DDL (IF NOT EXISTS)
      seed_data.sql                # OWASP Top 10 / CWE 정형 데이터 INSERT
      seed_data.cypher             # Neo4j 보안 도메인 노드/관계 MERGE
    performance/
      perf_antipattern_schema.sql  # 성능 도메인 PostgreSQL 확장 DDL
      perf_seed_data.sql           # PerfAntipatternCategory 정형 데이터
      perf_seed_data.cypher        # Neo4j 성능 도메인 노드/관계 MERGE
    verify_seed.py                 # 적재 후 정합성 검증 (노드 수, 고아 노드 탐지)
```

### 9.2. 멱등성(Idempotency) 보장

모든 데이터베이스 스크립트는 중복 실행되거나 어떤 환경에서 가동되더라도 기존 데이터를 파괴하지 않고 무결성을 유지하도록 아래 멱등성 규격을 필수 준수한다.

| DB | 멱등성 구문 | 적용 대상 |
|----|------------|-----------|
| PostgreSQL | `CREATE TABLE IF NOT EXISTS` | DDL 스크립트 전체 |
| PostgreSQL | `ON CONFLICT (doc_id) DO NOTHING` / `DO UPDATE` | INSERT 구문 전체 |
| Neo4j | `MERGE ... ON CREATE SET ... ON MATCH SET` | 노드/관계 생성 전체 |

### 9.3. 환경 불가지론적 재사용

격리된 스크립트 자산은 소스코드 변경 없이 아래 3개 환경에서 동일하게 재사용된다.

| 재사용 환경 | 실행 방법 |
|-------------|-----------|
| 로컬 개발 환경 초기화 | `psql $DATABASE_URL -f scripts/seed/security/schema.sql` |
| Phase 1 테스트 하네스 자동화 | `conftest.py` 픽스처에서 동일 파일 경로 참조 |
| Phase 4 GCP Cloud SQL 이관 | 환경변수 `DATABASE_URL`만 교체 후 동일 명령 실행 |

---

## 10. QA 및 테스트 코드 명세 (Test Harness Specification)

LangSmith 테스트 하네스 정책을 기반으로, 백엔드 프로젝트에서 반드시 격리 구현해야 하는 PyTest 테스트 코드의 구체적 범위와 Assert 명세를 정의한다. 레이스 컨디션·DB 락·LLM 비정형 출력을 완벽히 통제하기 위해 테스트는 4개 레이어로 분리 구축한다.

### 10.1. 테스트 하네스 격리 및 환경 선언 (conftest.py)

실제 운영 DB 및 로컬 외부 도커를 건드려 데이터를 오염시키지 않도록, `tests/harness/conftest.py`에 PyTest 전용 격리 픽스처를 선언한다.

```python
# tests/harness/conftest.py  (구조 명세)

@pytest.fixture(scope="function")
def db_session():
    """테스트 시작: schema.sql + seed_data.sql 주입 / 종료: ROLLBACK or TRUNCATE"""

@pytest.fixture(scope="function")
def neo4j_session():
    """테스트 시작: seed_data.cypher 실행 / 종료: MATCH (n) DETACH DELETE n"""

@pytest.fixture(scope="session")
def celery_app():
    """CELERY_TASK_ALWAYS_EAGER=True — 비동기 태스크를 동기 실행으로 강제 전환
    한 프로세스 내에서 디버깅 및 Assert 검증 가능"""
```

**픽스처 격리 원칙**:
- `db_session`: 테스트 함수 단위(`scope="function"`) 롤백. 테스트 간 데이터 간섭 없음.
- `neo4j_session`: 종료 시 `MATCH (n) DETACH DELETE n` 전체 정리. 고아 노드 잔류 방지.
- `celery_app`: `CELERY_TASK_ALWAYS_EAGER=True` 설정으로 Celery 브로커 없이 동기 실행. 인프라 의존성 없는 순수 로직 검증.

### 10.2. 레이어 A — 결정론적 유틸 및 마스터 키 검증 (`test_utils.py`)

LLM 통신 전 백엔드 단에서 수행되는 알고리즘의 무결성을 검증한다.

**T01. `doc_id` 발급 멱등성 테스트**

| 항목 | 내용 |
|------|------|
| 시나리오 | 동일한 URL과 동일한 본문 텍스트를 파라미터로 `build_doc_id()`를 3회 호출 |
| Assert | 반환된 `doc_id` 문자열이 3회 모두 완벽히 일치 |

```python
def test_doc_id_idempotency():
    url = "https://docs.djangoproject.com/en/6.0/topics/security/"
    content = "sample content"
    ids = [build_doc_id("EXT", url, content) for _ in range(3)]
    assert ids[0] == ids[1] == ids[2]
```

**T02. 동일 URL 내 콘텐츠 업데이트 변동 테스트**

| 항목 | 내용 |
|------|------|
| 시나리오 | URL은 `https://noru-sh.tistory.com/25`로 동일, 버전 1 텍스트와 버전 2 텍스트를 다르게 주입 |
| Assert | 두 `doc_id` 뒤쪽 8자리 해시가 서로 달라 독립 레코드로 격리됨을 검증 |

```python
def test_doc_id_content_change():
    url = "https://noru-sh.tistory.com/25"
    id_v1 = build_doc_id("EXT", url, "version 1 content")
    id_v2 = build_doc_id("EXT", url, "version 2 content — updated")
    assert id_v1[-8:] != id_v2[-8:]      # 해시 8자리가 달라야 함
    assert id_v1.split("_")[1] == id_v2.split("_")[1]  # URL 파트는 동일
```

### 10.3. 레이어 B — 데이터베이스 멱등성 및 제약 조건 검증 (`test_db_migration.py`)

인프라 스크립트가 다중 환경(로컬/운영/하네스)에서 충돌 없이 자원을 구성하는지 검증한다.

**T03. PostgreSQL `documents` UPSERT 및 타임스탬프 트리거 테스트**

| 항목 | 내용 |
|------|------|
| 시나리오 | 동일 `doc_id` 레코드를 `state='PENDING'`으로 INSERT 후 `state='CRAWLING'`으로 `ON CONFLICT DO UPDATE` 수행 |
| Assert 1 | 중복 에러 없이 `state`가 `'CRAWLING'`으로 변경됨 |
| Assert 2 | `updated_at`이 `created_at`보다 미래 시간으로 자동 갱신됨 |

**T04. Neo4j Tag Node 방식 도메인 태깅 + MERGE 멱등성 테스트**

| 항목 | 내용 |
|------|------|
| 시나리오 | `MemoryLeak` 개념 노드 생성 Cypher를 2회 실행 후 Tag Node(`Security`, `Performance`) 관계를 순차 부여 |
| Assert 1 | 전체 `:Concept` 노드 수 = 1 (Deduplication 보장) |
| Assert 2 | `(MemoryLeak)-[:TAGGED_WITH]->(Security)` 및 `(MemoryLeak)-[:TAGGED_WITH]->(Performance)` 관계 각 1개씩만 존재 |

```python
def test_neo4j_tag_node_deduplication(neo4j_session):
    # Arrange — 2회 MERGE 실행 (멱등성 확인)
    for _ in range(2):
        neo4j_session.run("""
            MERGE (c:Concept {name: 'MemoryLeak'})
            WITH c
            UNWIND ['Security', 'Performance'] AS tag_name
              MERGE (t:Tag {name: tag_name})
              MERGE (c)-[:TAGGED_WITH]->(t)
        """)

    # Assert 1 — Concept 노드 중복 없음
    cnt = neo4j_session.run(
        "MATCH (c:Concept {name:'MemoryLeak'}) RETURN count(c) AS cnt"
    ).single()["cnt"]
    assert cnt == 1

    # Assert 2 — Tag 관계 중복 없음 (각 1개)
    tags = neo4j_session.run("""
        MATCH (c:Concept {name:'MemoryLeak'})-[:TAGGED_WITH]->(t:Tag)
        RETURN collect(t.name) AS tags
    """).single()["tags"]
    assert set(tags) == {"Security", "Performance"}
```

### 10.4. 레이어 C — 비동기 파이프라인 및 스테이징 격리 검증 (`test_pipeline_gate.py`)

"승인 게이트 전 운영 DB 쓰기 차단" 정책을 물리적으로 검증하는 핵심 레이어.

**T05. Extractor 완료 시점 운영 DB 격리 테스트**

| 항목 | 내용 |
|------|------|
| 시나리오 | Extractor Task가 성공적으로 구조화 JSON을 도출한 직후 DB 상태 스캔 |
| Assert 1 | `concepts` 테이블과 Neo4j Graph DB에 어떠한 데이터도 추가/변경되지 않음 |
| Assert 2 | `staging_concepts` 테이블에만 `state='DRAFT'` 레코드 1건 존재 |

```python
def test_extractor_does_not_touch_master_db(db_session, neo4j_session, celery_app):
    run_extractor_task(doc_id="EXT_test_abc12345")  # ALWAYS_EAGER로 동기 실행

    master_count = db_session.execute("SELECT COUNT(*) FROM concepts").scalar()
    assert master_count == 0                         # 운영 테이블 미접촉

    neo4j_count = neo4j_session.run(
        "MATCH (c:Concept) RETURN count(c) AS cnt"
    ).single()["cnt"]
    assert neo4j_count == 0                          # 그래프 미접촉

    draft_count = db_session.execute(
        "SELECT COUNT(*) FROM staging_concepts WHERE state='DRAFT'"
    ).scalar()
    assert draft_count == 1                          # 스테이징에만 존재
```

**T06. 병렬 제출 레이스 컨디션 방어 테스트**

| 항목 | 내용 |
|------|------|
| 시나리오 | 동일 `session_id`·`doc_id`로 승인 요청을 Celery Worker 2개에 동시 투입 |
| Assert 1 | 먼저 진입한 Worker만 `state='COMMITTED'` 전환 성공 |
| Assert 2 | 늦게 온 Worker는 `ObjectDeletedError` 또는 커스텀 예외로 Fail-safe 처리됨 |

```python
def test_parallel_approve_race_condition(db_session, celery_app):
    session_id = "test-session-001"
    create_draft_staging(session_id=session_id)  # DRAFT 레코드 사전 생성

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [
            executor.submit(call_approve_api, session_id),
            executor.submit(call_approve_api, session_id),
        ]
        results = [f.result() for f in futures]

    committed = db_session.execute(
        "SELECT COUNT(*) FROM staging_concepts WHERE state='COMMITTED'"
    ).scalar()
    assert committed == 1                            # 단 1건만 COMMITTED

    statuses = [r["status"] for r in results]
    assert statuses.count("success") == 1
    assert statuses.count("conflict") == 1           # 나머지는 예외 처리
```

### 10.5. 레이어 D — LLM 품질 및 LangSmith 연동 검증 (`test_llm_eval.py`)

Gemini 출력 규격과 LangSmith 피드백 추적망이 정상 작동하는지 검증한다.

**T07. Extractor 출력 JSON 스키마 유효성 테스트**

| 항목 | 내용 |
|------|------|
| 시나리오 | Gemini가 반환한 Mock JSON을 Pydantic 모델 `ConceptExtractionSchema`로 파싱 |
| Assert 1 | `ValidationError` 없이 객체화 성공 |
| Assert 2 | `concept_domain` 값이 `['security', 'performance', 'both']` 범위 내에 존재 |

```python
def test_extractor_schema_validation():
    mock_output = {
        "concept_name": "XSS",
        "concept_domain": "security",
        "concept_type": "vulnerability_root_cause",
        "cwe_id": "CWE-79",
        "severity": "HIGH",
        "description_ko": "크로스 사이트 스크립팅 취약점",
        "aliases": ["Cross-Site Scripting", "크로스 사이트 스크립팅"],
    }
    schema = ConceptExtractionSchema(**mock_output)   # ValidationError 없어야 함
    assert schema.concept_domain in {"security", "performance", "both"}
```

**T08. LangSmith 피드백 루프 API 트리거 테스트**

| 항목 | 내용 |
|------|------|
| 시나리오 | HITL 수정 가상 API 호출 시 `langsmith.Client().create_feedback()` 정상 호출 여부 Mocking 검증 |
| Assert | 페이로드에 `score=0`, `run_id`, 수정 전/후 diff 메시지가 누락 없이 매핑됨 |

```python
def test_langsmith_feedback_trigger():
    with patch("langsmith.Client.create_feedback") as mock_feedback:
        call_hitl_correction_api(
            run_id="run-abc-123",
            before_json={"concept_domain": "security"},
            after_json={"concept_domain": "both"},
        )
        mock_feedback.assert_called_once()
        kwargs = mock_feedback.call_args.kwargs
        assert kwargs["score"] == 0
        assert kwargs["run_id"] == "run-abc-123"
        assert "before" in kwargs["comment"] and "after" in kwargs["comment"]
```

### 10.6. QA 완료 판단 기준 (Definition of Done — QA)

`pytest tests/`를 실행했을 때 아래 조건을 모두 충족해야 QA 통과로 판정한다.

```
tests/harness/test_utils.py          PASSED [ 25%]   # T01, T02
tests/harness/test_db_migration.py   PASSED [ 50%]   # T03, T04
tests/harness/test_pipeline_gate.py  PASSED [ 75%]   # T05, T06
tests/harness/test_llm_eval.py       PASSED [100%]   # T07, T08

==================== 8 passed in 2.34s ====================
```

| 판정 기준 | 목표값 |
|-----------|--------|
| 전체 테스트 통과율 | 8 / 8 PASSED |
| 테스트 커버리지 | ≥ 85% |
| DB 잔류 레코드 | 테스트 종료 후 마스터 테이블 및 그래프 고아 노드 0건 |
| 실행 시간 | ≤ 30초 (하네스 컨테이너 기준) |

---

## 11. 최종 승인 게이트 — 4대 핵심 커밋 규칙

FastAPI BackgroundTasks(PipelineTask), PostgreSQL 스테이징 테이블, Neo4j 지식 그래프가 3중으로 얽힌 하이브리드 아키텍처에서, 관리자 승인 후 운영 DB에 데이터를 최종 반영(`state='COMMITTED'`)할 때 백엔드 엔진이 강제 준수해야 하는 원자적 커밋 규칙이다. (v1 기준 3대 규칙; 규칙 ③ Link Resolver는 v2 대상)

### 규칙 ① — 2단계 크로스 DB 트랜잭션 보장 (Two-Phase Commit Pattern)

**규칙**: PostgreSQL `concepts` 테이블 쓰기와 Neo4j `MERGE`는 하나의 논리적 단위로 묶인다.

**예외 처리**: Neo4j 적재 중 에러(커넥션 타임아웃, 문법 오류 등) 발생 시 이미 성공한 PostgreSQL `INSERT/UPSERT`를 즉시 롤백하고, `staging_concepts.state`를 `COMMITTED`로 변경하지 않는다.

```python
async def commit_to_master(session_id: str, approved_concepts: list):
    async with pg_session.begin() as pg_tx:       # PostgreSQL 트랜잭션 열기
        try:
            await pg_tx.execute(upsert_concepts_sql, approved_concepts)
            await neo4j_merge_concepts(approved_concepts)  # Neo4j 적재
            await pg_tx.execute(
                "UPDATE staging_concepts SET state='COMMITTED' WHERE session_id=:sid",
                {"sid": session_id}
            )
            # PostgreSQL commit은 with 블록 정상 종료 시 자동 실행
        except Neo4jError:
            await pg_tx.rollback()               # Neo4j 실패 시 PG도 롤백
            raise
```

### 규칙 ② — 멱등성 기반 자성 커밋 (Idempotent MERGE Commit)

**규칙**: 네트워크 지연으로 동일 승인 태스크가 Celery 큐에서 이중 실행되어도 마스터 DB는 안전해야 한다.

**구현 제약**: Neo4j 적재 시 반드시 `Concept.name`을 유니크 식별 키로 `MERGE ... ON CREATE SET ... ON MATCH SET` 구문을 사용한다. 동일 데이터 재입력 시 노드 중복 생성 없이 `updated_at` 타임스탬프만 갱신된다.

```cypher
// Tag Node 방식 — APOC 불필요, 순수 Cypher (v1)
MERGE (c:Concept {name: $name})
ON CREATE SET
  c.cwe_id         = $cwe_id,
  c.description_ko = $description_ko,
  c.aliases        = $aliases,
  c.created_at     = timestamp()
ON MATCH SET
  c.updated_at     = timestamp()
WITH c
UNWIND $domain_tags AS tag_name          // ["Security"], ["Performance"], or ["Security","Performance"]
  MERGE (t:Tag {name: tag_name})
  MERGE (c)-[:TAGGED_WITH]->(t)
```

> **설계 이유**: `apoc.create.addLabels()`는 APOC 플러그인 필수. Neo4j Aura Free 미지원.
> Tag Node(`-[:TAGGED_WITH]->`) 방식은 순수 Cypher로 동일 교차도메인 필터링을 달성한다.
> `MATCH (c:Concept)-[:TAGGED_WITH]->(:Tag {name:'Security'})` = 기존 `MATCH (c:Concept:Security)`

### 규칙 ③ — Link Resolver 트리거 (v2 대상 — v1 미구현)

> **v1 상태 전이**: `APPROVED → COMMITTED` (직결).
> `COMMITTED_PENDING_RESOLVE` 상태는 v1에 존재하지 않는다.

**v2 계획**: 개념 노드가 Neo4j에 커밋된 직후 Link Resolver Agent가 `aliases` 기반 벡터 유사도 탐색으로 `SAME_AS` / `RELATED_TO` 관계를 자동 생성. v2에서 Celery 도입 시 함께 구현.

**v1 세션 상태 전이** (단순화):

```
APPROVED → COMMITTED
```

**v2 세션 상태 전이** (예정):

```
APPROVED → COMMITTED → COMMITTED_PENDING_RESOLVE → FULLY_RESOLVED
```

### 규칙 ④ — 소스 문서(`Document`) 상태 동기화 격리

**규칙**: `concepts` 테이블에 데이터가 바인딩되는 순간, 해당 개념들의 출처 `documents` 테이블 레코드 `state`도 즉시 `'COMMITTED'`로 동기화 변경한다.

**이유**: 프론트엔드 대시보드 파이프라인 상태 인디케이터가 "어떤 URL 문서가 완전히 파이프라인에 안착했는지"를 오차 없이 초록불로 전환하기 위함이다.

```python
async def commit_to_master(session_id: str, approved_concepts: list):
    async with pg_session.begin() as pg_tx:
        await pg_tx.execute(upsert_concepts_sql, approved_concepts)
        await neo4j_merge_concepts(approved_concepts)

        # ④ 소스 Document 상태 동기화 — concepts와 동일 트랜잭션 내 실행
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
```

**4대 규칙 요약**:

| 규칙 | 핵심 보장 | 실패 시 동작 | v1 여부 |
|------|-----------|-------------|---------|
| ① 크로스 DB 일관성 | PG 소스오브트루스 + 시작 시 Neo4j 재조정 | 재시작 시 COMMITTED 행 재처리 | ✅ v1 |
| ② 멱등성 MERGE Commit | 이중 실행 안전 | 노드 중복 없이 타임스탬프만 갱신 | ✅ v1 |
| ③ Link Resolver 자동 트리거 | 고립 노드 방지 | — | ⏳ v2 |
| ④ Document 상태 동기화 | 대시보드 정합성 | 동일 트랜잭션 내 즉시 반영 | ✅ v1 |

---

## 12. 형상 관리 및 Git 커밋 규칙 (Git Commit Convention)

모든 개발자 및 AI 협업 도구는 소스코드 변경 이력을 명확히 추적하고 코드 리뷰 효율을 높이기 위해 **Conventional Commits 1.0.0** 규격을 준수한다.

### 12.1. 커밋 메시지 구조

```
<type>(<scope>): <subject>          ← Header (필수)

[body]                              ← Body (선택, 변경 이유 및 상세 설명)

[footer]                            ← Footer (선택, 이슈 번호, Breaking Change)
```

- **Header**: 소문자, 50자 이내, 명령형 현재 시제
- **Body**: 72자 줄바꿈, "무엇을 왜" 설명
- **Footer**: `Closes #123`, `BREAKING CHANGE: ...`

### 12.2. 필수 커밋 타입 (Type)

| 타입 | 설명 | 예시 |
|------|------|------|
| `feat` | 새로운 기능 추가 | 에이전트 로직 구현, API 엔드포인트 신설 |
| `fix` | 버그 수정 | 파이프라인 락 에러 해결, JSON 파싱 예외 처리 |
| `docs` | 문서 수정 | PRD 업데이트, README.md 수정 |
| `style` | 코드 포맷팅, 세미콜론 누락 등 | 비즈니스 로직 변경 없음 |
| `refactor` | 코드 리팩토링 | 기능 추가나 버그 수정 없는 구조 개선 |
| `test` | 테스트 코드 추가 및 수정 | 테스트 하네스, PyTest 스크립트 추가 |
| `chore` | 빌드, 패키지 매니저, 도커파일 수정 | 프로덕션 코드 변경 없음 |

### 12.3. 프로젝트 전용 Scope 규정

제목의 `()` 안에 들어갈 Scope는 아래 항목으로 강제한다.

| Scope | 변경 모듈 |
|-------|-----------|
| `input` | Input Agent 및 URL Pre-scan 관련 |
| `crawler` | Crawler Agent 및 DOM 정제 관련 |
| `extractor` | Extractor Agent 및 Gemini 프롬프트/JSON 스키마 관련 |
| `writer` | Graph Writer Agent 및 PostgreSQL/Neo4j 적재 관련 |
| `resolver` | Link Resolver Agent 및 벡터 유사도 병합 관련 |
| `db` | 마이그레이션 스크립트, 시드 데이터(`schema.sql`, `seed_data.cypher` 등) 관련 |
| `infra` | Docker, Docker Compose, Cloud SQL Proxy 설정 관련 |
| `frontend` | UI 컴포넌트, 상태 관리, react-force-graph 관련 |

### 12.4. 커밋 예시

```bash
# 기능 추가
feat(extractor): add concept_domain field to gemini extraction schema

# 버그 수정
fix(writer): rollback postgresql on neo4j connection timeout

# 테스트
test(writer): add T04 neo4j multilabel dedup harness test

# 인프라
chore(infra): add cloud-sql-proxy service with gcp profile

# DB 스키마
feat(db): add staging_concepts table with state machine columns

# 리팩터
refactor(resolver): extract alias similarity into shared util

# BREAKING CHANGE 포함
feat(writer): enforce two-phase commit for cross-db atomicity

BREAKING CHANGE: graph_writer_task now raises CrossDbCommitError
on neo4j failure instead of silently continuing
```

---

## 13. 프로젝트 완료 조건 (Definition of Done)

각 Phase별 개발 완료 판정 및 최종 릴리즈 승인은 아래의 정량적·정성적 기준을 모두 충족할 때에만 승인된다.

### 13.1. 기능적 완료 조건

| 번호 | 조건 | 판정 방법 |
|------|------|-----------|
| F-01 | 1~5개 URL 입력 → 파이프라인 완전 실행 → Neo4j Concept 노드 생성까지 End-to-End 동작 | 실제 Django Docs URL 투입 후 토폴로지 뷰 확인 |
| F-02 | Human-in-the-Loop: 메타데이터 자동 추론 성공률 ≥ 80% (Django·Spring·FastAPI URL 기준) | Pre-scan 20건 테스트 결과 |
| F-03 | 최종 승인 게이트: DRAFT→APPROVED→COMMITTED 상태 전이 및 4대 커밋 규칙 모두 동작 | T05·T06 하네스 통과 확인 |
| F-04 | 프론트엔드 가상 노드 미리보기: DRAFT 노드 점선 렌더링 및 승인 후 실선 전환 정상 동작 | Chrome 브라우저 스모크 테스트 |
| F-05 | 성능 도메인 4종 안티패턴(N+1Query 등) 및 보안 도메인 OWASP 시드 데이터 정상 적재 | `verify_seed.py` 실행 결과 0 오류 |

### 13.2. 비기능적 성능 및 품질 지표

| 번호 | 지표 | 목표값 |
|------|------|--------|
| Q-01 | LangSmith Pre-Eval 스키마 이탈률 | **0%** |
| Q-02 | `pytest tests/` 전체 통과율 | **8 / 8 PASSED** |
| Q-03 | 테스트 커버리지 | **≥ 85%** |
| Q-04 | 단일 URL End-to-End 처리 시간 (크롤링 + LLM 추출 + DB 적재) | **≤ 60초** |
| Q-05 | 동일 URL 재처리 시 LLM 재호출 없이 캐시 응답 처리 | 토큰 소모 **0** |
| Q-06 | 프로덕션 HITL 수정률 (초기 배포 2주 기준) | **< 20%** |

### 13.3. 산출물 완료 조건

| 번호 | 산출물 | 위치 |
|------|--------|------|
| A-01 | PRD 최신 버전 (v0.9+) | `docs/PRD_Knowledge_Graph_Agent.md` |
| A-02 | `docker-compose.yml` + `.env.local` + `.env.prod` | `infra/` |
| A-03 | 시드 스크립트 (`schema.sql`, `seed_data.sql`, `seed_data.cypher`) | `scripts/seed/` |
| A-04 | LangSmith 평가 데이터셋 (`extractor_schema_eval/`) | `langsmith_datasets/` |
| A-05 | 테스트 하네스 4개 파일 (`test_utils.py` ~ `test_llm_eval.py`) | `tests/harness/` |
| A-06 | `verify_seed.py` 정합성 검증 스크립트 | `scripts/seed/` |

---

## 14. 시스템 아키텍처 및 표준 폴더 레이아웃

### 14.1. 아키텍처 설계 원칙 — PRD에 포함하는 3가지 이유

| 이유 | 설명 |
|------|------|
| 테스트 경계 시각화 | 어떤 레이어가 어느 테스트 파일로 커버되는지 레이어-테스트 매핑이 명확해야 TDD가 가능하다 |
| SDD 스펙 도출 근거 | 폴더 구조는 곧 유즈케이스 목록이다. `usecases/run_pipeline.py`, `usecases/approve_staging.py`가 PRD 요구사항과 1:1 대응됨을 보장한다 |
| 비동기 흐름 복잡성 통제 | FastAPI → BackgroundTask(PipelineTask) → dual-DB commit까지 이어지는 흐름에서 "어떤 레이어가 어느 경계를 넘는가"를 구조로 강제하면 레이스 컨디션 원인 파악이 즉각 가능하다 |

### 14.2. 고수준 컴포넌트 통신 흐름

> **v1 아키텍처**: Celery/Redis 미사용. `FastAPI BackgroundTasks` + `PipelineTask` 프로토콜로 비동기 처리.
> v2에서 처리량이 10개/세션을 초과하면 Celery+Redis로 교체 가능하도록 `PipelineTask` 인터페이스로 추상화.

```
[React :3000] ──REST/SSE──▶ [FastAPI :8000]
                                    │
                          BackgroundTasks.add_task()
                          (PipelineTask 프로토콜 구현체)
                                    │
                    ┌───────────────┼────────────────┐
                    ▼               ▼                 ▼
             HITL 승인 게이트  [pipeline_jobs]   asyncio.gather()
             (SELECT FOR        PostgreSQL        Semaphore(RPM)
              UPDATE SKIP       상태 기록              │
              LOCKED)                          ──LLM API──▶ [Gemini 2.5 Flash]
                    │                          ──@traceable─▶ [LangSmith]
                    ▼
           [PostgreSQL UPSERT]
                    │  커밋 성공 후
                    ▼
            [Neo4j MERGE]       ← 실패 시 startup reconciliation 재처리
```

**컴포넌트별 통신 방식** (v1):

| 송신 | 수신 | 방식 | 방향 |
|------|------|------|------|
| React | FastAPI | REST (JSON) + SSE (실시간 로그) | 양방향 |
| FastAPI | PipelineTask | `BackgroundTasks.add_task()` | 단방향 |
| PipelineTask | PostgreSQL | SQLAlchemy AsyncSession | 양방향 |
| PipelineTask | Neo4j | Neo4j Driver (MERGE Cypher) | 양방향 |
| PipelineTask | Gemini API | `asyncio.gather()` + Semaphore(RPM) | 단방향 |
| PipelineTask | LangSmith | `@traceable` SDK 래핑 | 단방향 (트레이싱) |
| FastAPI | LangSmith | `client.create_feedback()` (HITL 수정 시) | 단방향 |
| FastAPI (startup) | PostgreSQL | RUNNING 고아 잡 → FAILED 전환 (10분 초과) | 양방향 |

> **v2 마이그레이션 경로**: `PipelineTask` 프로토콜 구현체를 `CeleryPipelineTask`로 교환하면 Celery+Redis 전환 완료.
> `FastAPI → task.delay() → Celery Worker → Redis pub/sub → SSE` 패턴은 v2 스펙.

### 14.3. 백엔드 — 클린 아키텍처 기반 폴더 레이아웃

**의존성 규칙**: 의존성은 외부(`infrastructure`)에서 내부(`domain`)로만 향한다. 비즈니스 로직(에이전트 파이프라인 흐름, 승인 상태 전이)은 특정 DB 기술이나 프레임워크에 종속되지 않는다.

```
backend/
├── app/
│   ├── domain/                        # 레이어 1: 핵심 비즈니스 엔티티 (프레임워크 무관)
│   │   ├── models.py                  # 도메인 개념 모델 (순수 Python/Pydantic)
│   │   │                              #   Concept, Document, StagingRecord, PipelineState
│   │   └── pipeline.py                # 파이프라인 상태 전이 규칙
│   │                                  #   PENDING→CRAWLING→EXTRACTED→COMMITTED
│   │
│   ├── usecases/                      # 레이어 2: 애플리케이션 흐름 (도메인↔인프라 중계)
│   │   ├── run_pipeline.py            # 에이전트 5단계 파이프라인 구동 유즈케이스
│   │   ├── approve_staging.py         # 스테이징 DRAFT→APPROVED→COMMITTED 유즈케이스
│   │   │                              #   4대 커밋 규칙 (§11) 실행 주체
│   │   └── interfaces/                # 의존성 역전 추상 인터페이스 (DIP)
│   │       ├── repository.py          #   PostgreSQL 접근 추상 (구현은 infra에서)
│   │       └── graph_service.py       #   Neo4j 접근 추상 (구현은 infra에서)
│   │
│   ├── infrastructure/                # 레이어 3: 외부 저수준 인프라 구현체
│   │   ├── database/
│   │   │   ├── pg_repository.py       # SQLAlchemy AsyncSession 구현체
│   │   │   └── migrations/            # Alembic 마이그레이션 파일
│   │   ├── graph/
│   │   │   ├── neo4j_service.py       # Neo4j Driver + Cypher 쿼리 구현체
│   │   │   └── cypher/                # .cypher 쿼리 파일 (MERGE 템플릿)
│   │   ├── queue/
│   │   │   ├── celery_app.py          # Celery 앱 인스턴스 및 설정
│   │   │   └── tasks/                 # 에이전트별 비동기 태스크
│   │   │       ├── crawler_task.py
│   │   │       ├── extractor_task.py
│   │   │       ├── writer_task.py
│   │   │       └── resolver_task.py
│   │   └── llm/
│   │       ├── interface.py           # LLM 추상 인터페이스 (ILLMClient) — DIP 기반
│   │       ├── gemini_client.py       # PROD 모드: Gemini 2.5 Flash + LangSmith 활성화
│   │       ├── mock_client.py         # DEV 모드: PRD §3.3.3 고정 스펙 Mock JSON 반환
│   │       └── factory.py             # APP_MODE 플래그 기반 클라이언트 선택 팩토리
│   │
│   └── interfaces/                    # 레이어 4: HTTP 진입점 (컨트롤러)
│       ├── api/
│       │   ├── pipeline.py            # POST /api/pipeline/trigger
│       │   ├── staging.py             # GET·PATCH·POST /api/staging/{session_id}
│       │   └── graph.py               # GET /api/graph/topology
│       └── schemas/
│           ├── request.py             # HTTP Request DTO (Pydantic)
│           └── response.py            # HTTP Response DTO (Pydantic)
│
├── config/
│   ├── settings.py                    # pydantic-settings 환경변수 바인딩
│   └── logging.py                     # 구조화 로깅 설정
│
├── scripts/
│   └── seed/                          # § 9 형상 관리 정책 대상 스크립트 디렉토리
│       ├── security/
│       │   ├── schema.sql
│       │   ├── seed_data.sql
│       │   └── seed_data.cypher
│       ├── performance/
│       │   ├── perf_antipattern_schema.sql
│       │   ├── perf_seed_data.sql
│       │   └── perf_seed_data.cypher
│       └── verify_seed.py
│
├── tests/
│   └── harness/                       # § 10 QA 테스트 하네스 (레이어 A~D)
│       ├── conftest.py                #   픽스처: db_session · neo4j_session · celery_app
│       ├── test_utils.py              #   레이어 A: T01·T02 (doc_id 멱등성)
│       ├── test_db_migration.py       #   레이어 B: T03·T04 (DB 멱등성)
│       ├── test_pipeline_gate.py      #   레이어 C: T05·T06 (비동기 격리)
│       └── test_llm_eval.py           #   레이어 D: T07·T08 (LLM 품질)
│
├── langsmith_datasets/
│   ├── extractor_schema_eval/         # Pre-Eval 골든 데이터셋
│   │   ├── golden_inputs/
│   │   └── expected_outputs/
│   └── translation_eval/
│       └── en_ko_pairs/
│
├── Dockerfile
├── requirements.txt
└── .env.example
```

**레이어-테스트 경계 매핑**:

| 레이어 | 테스트 파일 | 검증 방식 | 인프라 의존 |
|--------|------------|-----------|-------------|
| `domain` | `test_utils.py` (레이어 A) | 순수 함수 단위 테스트 | 없음 |
| `usecases` + `infrastructure` (DB) | `test_db_migration.py` (레이어 B) | 격리 컨테이너 실물 DB | PostgreSQL, Neo4j |
| `usecases` + `infrastructure` (queue) | `test_pipeline_gate.py` (레이어 C) | `ALWAYS_EAGER` 동기화 | PostgreSQL, Neo4j, Redis |
| `infrastructure/llm` | `test_llm_eval.py` (레이어 D) | Pydantic 검증 + SDK Mock | LangSmith Mock |

### 14.4. 프론트엔드 — 아토믹 디자인 패턴 기반 폴더 레이아웃

**설계 원칙**: Vite 빌드의 빠른 HMR을 살리면서, UI 컴포넌트는 원자 단위로 분리하고 비즈니스 로직과 API 통신은 `hooks` 레이어로 격리한다.

```
frontend/
├── src/
│   ├── assets/
│   │   ├── styles/
│   │   │   └── globals.css            # Tailwind 기본 설정 (@tailwind base/components/utilities)
│   │   └── fonts/
│   │
│   ├── components/                    # 아토믹 디자인 격리 레이어
│   │   ├── atoms/                     # [원자] 최소 단위 — 상태·로직 없음
│   │   │   ├── Badge.tsx              #   도메인 라벨 배지 (Security · Performance · 교차)
│   │   │   ├── Button.tsx             #   범용 버튼 (승인·거부·제출)
│   │   │   ├── Spinner.tsx            #   로딩 인디케이터
│   │   │   └── StatusDot.tsx          #   파이프라인 단계 상태 점 (PENDING/RUNNING/DONE)
│   │   │
│   │   ├── molecules/                 # [분자] 원자 2개 이상 조합 — 단일 책임
│   │   │   ├── PipelineStepIndicator.tsx   # StatusDot + 단계명 텍스트 조합
│   │   │   ├── MetadataForm.tsx            # 입력 필드 + 추론 신뢰도 배지 조합
│   │   │   └── DiffSummaryCard.tsx         # 승인 전 diff 요약 (신규 N개·업데이트 M개)
│   │   │
│   │   ├── organisms/                 # [유기체] 독립 가동 UI 블록 — 훅 결합 허용
│   │   │   ├── TopologyViewer.tsx     #   react-force-graph 래퍼
│   │   │   │                          #   가상 노드 미리보기: DRAFT=점선, COMMITTED=실선
│   │   │   ├── ConceptInspector.tsx   #   우측 사이드 패널 — 노드 상세·승인/거부 토글
│   │   │   ├── LogConsole.tsx         #   SSE 실시간 로그 스트림 출력 콘솔
│   │   │   └── ApprovalPanel.tsx      #   전체 승인·거부·diff 요약 패널
│   │   │
│   │   └── templates/                 # [템플릿] 레이아웃 골격 — 빈 슬롯 구조
│   │       └── DashboardLayout.tsx    #   사이드바 + 메인뷰 + 인스펙터 3-panel 레이아웃
│   │
│   ├── pages/                         # 라우팅 페이지 — 훅·유기체 결합점
│   │   └── MainPage.tsx               #   단일 SPA 페이지 (파이프라인 대시보드)
│   │
│   ├── hooks/                         # 비즈니스 로직·전역 상태 격리
│   │   ├── usePipelineSSE.ts          #   SSE 스트림 구독 → 파이프라인 단계 상태 업데이트
│   │   ├── useGraphMerge.ts           #   기존 Neo4j 노드 + DRAFT 노드 클라이언트 병합
│   │   │                              #   가상 토폴로지 데이터 생성 (DB 미접촉)
│   │   ├── useStagingApproval.ts      #   DRAFT 노드 목록 조회·개별 승인/거부·최종 승인 API
│   │   └── useDocumentInput.ts        #   URL 입력·메타데이터 Pre-scan 자동 추론 연동
│   │
│   ├── services/                      # Axios 기반 API 통신 추상화
│   │   ├── api.ts                     #   Axios 인스턴스·baseURL·인터셉터 설정
│   │   ├── pipelineService.ts         #   파이프라인 트리거·상태 조회 API
│   │   ├── stagingService.ts          #   스테이징 CRUD·승인·diff API
│   │   └── graphService.ts            #   토폴로지 조회 API
│   │
│   ├── types/                         # TypeScript 인터페이스·도메인 타입
│   │   ├── concept.ts                 #   ConceptNode, ConceptDomain, NodeLabel
│   │   ├── pipeline.ts                #   PipelineState, AgentStep, StagingRecord
│   │   └── graph.ts                   #   GraphNode, GraphEdge, VirtualNodeStyle
│   │
│   └── utils/                         # 순수 함수·데이터 파싱
│       ├── docId.ts                   #   build_doc_id 클라이언트 사이드 구현 (표시용)
│       └── nodeStyler.ts             #   노드 상태별 시각 스타일 결정 함수
│                                      #   (DRAFT=점선, COMMITTED=실선, REJECTED=빨간 테두리)
│
├── nginx.conf                         # 프로덕션 Nginx 설정 (SPA fallback, gzip, cache)
├── Dockerfile                         # Multi-stage: node build → nginx serve
├── package.json
└── vite.config.ts                     # 빌드 도구 설정 (path alias, proxy dev server)
```

**아토믹 레이어별 책임 구분**:

| 레이어 | 상태 보유 | 훅 사용 | API 호출 | 범위 |
|--------|-----------|---------|----------|------|
| atoms | 불가 | 불가 | 불가 | 스타일·렌더링만 |
| molecules | 로컬 UI 상태만 | 불가 | 불가 | 원자 조합 |
| organisms | 가능 | 가능 | hooks 통해서만 | 독립 UI 블록 |
| templates | 불가 | 불가 | 불가 | 레이아웃 슬롯 |
| pages | 가능 | 가능 | services 통해서만 | 라우팅 조합점 |

**`useGraphMerge.ts` 핵심 동작** (SDD 스펙):

```typescript
// Arrange: 두 데이터 소스 로드
const confirmedNodes = await graphService.getTopology()     // GET /api/graph/topology
const draftNodes = await stagingService.getDraft(sessionId) // GET /api/staging/{id}

// Act: 클라이언트 사이드 가상 병합 (DB 미접촉)
const merged = mergeVirtualGraph(confirmedNodes, draftNodes)
// merged 내 DRAFT 노드: strokeDasharray=true, opacity=0.65
// merged 내 SAME_AS 후보: badge="병합 예정"

// Assert (렌더 결과 테스트): 
// - DRAFT 노드 count === draftNodes.length
// - COMMITTED 노드 style.opacity === 1
```

### 14.5. 루트 모노레포 레이아웃

```
project-root/
├── backend/                   # §14.3 백엔드 클린 아키텍처 루트
├── frontend/                  # §14.4 프론트엔드 아토믹 디자인 루트
├── infra/
│   ├── docker-compose.yml     # §5.2 애플리케이션 3-서비스 컴포즈
│   ├── .env.local             # 로컬 외부 컨테이너 환경변수
│   └── .env.prod              # GCP Cloud SQL Auth Proxy 환경변수
├── docs/
│   └── PRD_Knowledge_Graph_Agent.md   # 본 문서
└── .github/
    └── workflows/             # CI: pytest → LangSmith Pre-Eval → Docker build
```

---

## 15. 시스템 다이어그램 명세 (Diagram Specifications)

### 15.1. 고수준 시스템 아키텍처 — 레이어 경계 요약

```
┌─────────────────────────────────────────────────────────────┐
│  프론트엔드 레이어 (React · Vite · Atomic Design)            │
│  atoms/molecules → organisms → hooks/services → pages       │
└────────────────────────┬────────────────────────────────────┘
                         │ REST / SSE
┌────────────────────────▼────────────────────────────────────┐
│  백엔드 레이어 (FastAPI · Clean Architecture)                │
│  interfaces → usecases → domain  ◀── 의존성 역전(DIP)       │
│  └── infrastructure (database · graph · queue · llm)        │
└──────────────────┬──────────────────────────────────────────┘
                   │ task.delay()
┌──────────────────▼──────────────────────────────────────────┐
│  Celery Worker 레이어 — 5단계 파이프라인                      │
│  Input → Crawler → Extractor → Graph Writer → Link Resolver │
│                    ↓ 최종 승인 게이트 (HITL)                  │
│                    4대 커밋 규칙 (①②③④) 원자 실행             │
└──────────┬──────────────────────┬───────────────────────────┘
           │                      │
  ┌────────▼──────────┐  ┌────────▼──────────────────────────┐
  │  외부 인프라       │  │  외부 서비스                       │
  │  PostgreSQL       │  │  Gemini 2.5 Flash (LLM API)       │
  │  Neo4j            │  │  LangSmith (@traceable · Pre-Eval) │
  │  Redis            │  └───────────────────────────────────┘
  └───────────────────┘
  env 교체만으로 로컬↔GCP 전환
```

### 15.2. PostgreSQL 스키마 DDL

```sql
-- ① documents: 수집 대상 URL 메타데이터
CREATE TABLE IF NOT EXISTS documents (
  doc_id           TEXT PRIMARY KEY,           -- PREFIX_url_hash8 마스터 키
  source_prefix    TEXT NOT NULL,              -- EXT / KMS / ...
  original_url     TEXT NOT NULL,              -- 원본 URL (정규화 전)
  content_hash     CHAR(8) NOT NULL,           -- SHA-256 앞 8자리
  etag             TEXT,                       -- HTTP ETag (우선 사용)
  lang             TEXT,                       -- EN / KO
  framework        TEXT,                       -- Pre-scan 추론값
  version          TEXT,                       -- Pre-scan 추론값
  infer_confidence REAL DEFAULT 0,             -- 추론 신뢰도 0.0~1.0
  state            TEXT NOT NULL DEFAULT 'PENDING',  -- 파이프라인 상태
  created_at       TIMESTAMPTZ DEFAULT now(),
  updated_at       TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_documents_prefix_state ON documents(source_prefix, state);
CREATE INDEX IF NOT EXISTS idx_documents_url_hash     ON documents(original_url, content_hash);

-- ② staging_concepts: Extractor 출력 임시 보관 (운영 DB 격리)
CREATE TABLE IF NOT EXISTS staging_concepts (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id   UUID NOT NULL,                  -- 파이프라인 실행 세션
  doc_id       TEXT REFERENCES documents(doc_id) ON DELETE CASCADE,
  concept_json JSONB NOT NULL,                 -- Extractor 원본 출력
  state        TEXT NOT NULL DEFAULT 'DRAFT',  -- DRAFT→APPROVED→COMMITTED|REJECTED
  reviewed_at  TIMESTAMPTZ,
  committed_at TIMESTAMPTZ,
  created_at   TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_staging_session_state ON staging_concepts(session_id, state);

-- ③ concepts: 최종 승인 후 반영된 개념 정형 데이터
CREATE TABLE IF NOT EXISTS concepts (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  concept_name   TEXT NOT NULL UNIQUE,         -- Neo4j Concept.name과 동일 (MERGE 키)
  doc_id         TEXT REFERENCES documents(doc_id) ON DELETE SET NULL,
  concept_domain TEXT NOT NULL,                -- security / performance / both
  concept_type   TEXT,                         -- 4종 컨셉 타입
  cwe_id         TEXT,
  owasp_id       TEXT,
  severity       TEXT,                         -- CRITICAL / HIGH / MEDIUM / LOW
  description_ko TEXT,
  aliases        TEXT[] DEFAULT '{}',
  created_at     TIMESTAMPTZ DEFAULT now(),
  updated_at     TIMESTAMPTZ
);
CREATE INDEX IF NOT EXISTS idx_concepts_domain   ON concepts(concept_domain);
CREATE INDEX IF NOT EXISTS idx_concepts_cwe_id   ON concepts(cwe_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_concepts_name ON concepts(concept_name);

-- ④ pipeline_logs: 에이전트 단계별 로그 (SSE 원본)
CREATE TABLE IF NOT EXISTS pipeline_logs (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_id     TEXT REFERENCES documents(doc_id) ON DELETE CASCADE,
  session_id UUID,
  agent      TEXT NOT NULL,   -- Input/Crawler/Extractor/Writer/Resolver
  level      TEXT NOT NULL,   -- INFO / WARNING / ERROR
  message    TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_logs_doc_session ON pipeline_logs(doc_id, session_id);

-- ⑤ concept_snapshots: Extractor 원본 JSON (감사 추적·LangSmith 피드백)
CREATE TABLE IF NOT EXISTS concept_snapshots (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  doc_id           TEXT REFERENCES documents(doc_id) ON DELETE CASCADE,
  session_id       UUID NOT NULL,
  langsmith_run_id TEXT,          -- @traceable 자동 기록값
  raw_output_json  JSONB NOT NULL, -- Gemini 원본 출력 (수정 전)
  approved_json    JSONB,          -- 관리자 확정 JSON (HITL diff 소스)
  created_at       TIMESTAMPTZ DEFAULT now()
);
```

### 15.3. Neo4j 노드 및 관계 전체 명세

#### 노드 레이블 및 주요 속성

| 레이블 | MERGE 키 | 핵심 속성 | 도메인 |
|--------|----------|-----------|--------|
| `Domain` | `name` | `description_ko` | 공통 |
| `OWASPCategory` | `owasp_id` | `name`, `description_ko` | Security |
| `PerfAntipatternCategory` | `name` | `authority`, `description_ko` | Performance |
| `CWE` | `cwe_id` | `name`, `description_ko` | 공통 |
| `Concept` | `name` | `aliases[]`, `description_ko`, `severity`, `cwe_id` + 다중 라벨 | 공통 허브 |
| `SecurityMechanism` | `name` | `description_ko` | Security |
| `RootCause` | `name` | `description_ko` | 공통 |
| `Component` | `name` | `description_ko` | 공통 |
| `ConfigProperty` | `key` | `value`, `framework` | 공통 |
| `Framework` | `name` + `version` | `lang` | 공통 |
| `Document` | `doc_id` | `source_prefix`, `original_url`, `content_hash`, `framework`, `version` | 공통 |

#### 관계 타입 전체 목록

| 관계 타입 | 방향 | 의미 |
|-----------|------|------|
| `BELONGS_TO` | Domain → OWASPCategory / PerfAntipatternCategory | 도메인 분류 소속 |
| `MAPS_TO` | OWASPCategory → CWE | OWASP ↔ CWE 공식 매핑 (보안 도메인) |
| `REF_TO` | PerfAntipatternCategory → CWE | CWE 자원관리 선택적 참조 (성능 도메인) |
| `INSTANTIATED_BY` | CWE → Concept | CWE가 Concept으로 구체화됨 |
| `MITIGATED_BY` | Concept → SecurityMechanism | 대응 보안 메커니즘 |
| `CAUSED_BY` | Concept → RootCause | 취약점·결함 근본 원인 |
| `AFFECTS` | Concept → Component | 영향 받는 소프트웨어 컴포넌트 |
| `CONFIGURED_BY` | Concept → ConfigProperty | 관련 프레임워크 설정 속성 |
| `IMPLEMENTS` | Framework → Concept | 프레임워크가 해당 개념 구현·대응 |
| `RELATED_TO` | Concept ↔ Concept | 의미적 연관 개념 |
| `SAME_AS` | Concept ↔ Concept | 동의어·이명 관계 (Link Resolver 생성) |
| `SOURCED_FROM` | Document → Concept | 문서 출처 역추적 |

#### Concept 다중 라벨 규칙

| `concept_domain` 값 | 부여 라벨 | 예시 |
|---------------------|-----------|------|
| `"security"` | `:Concept:Security` | XSS, SQLi, CSRF |
| `"performance"` | `:Concept:Performance` | N+1Query, MissingIndex |
| `"both"` | `:Concept:Security:Performance` | MemoryLeak, ConnPoolExhaustion |

---

## 16. LLM 인프라 추상화 및 Mock 메커니즘 (의존성 역전 기반)

### 16.1. 설계 목표

비즈니스 유즈케이스(`usecases/`)는 외부 인프라(Gemini API, LangSmith)의 실체에 의존하지 않는다. `infrastructure/llm/interface.py`에 추상 인터페이스를 두고 `.env`의 `APP_MODE` 플래그에 따라 `MockClient` 또는 `GeminiClient`를 주입한다. **애플리케이션 코드 변경 없이** DEV ↔ PROD 전환이 완료된다.

```
┌──────────────────────────────────────────────────────┐
│  usecases/run_pipeline.py                            │
│  → self.llm: ILLMClient  ← 인터페이스만 참조 (DIP)   │
└──────────────┬───────────────────────────────────────┘
               │ APP_MODE 플래그 분기 (factory.py)
        ┌──────┴──────┐
        ▼             ▼
  MockClient    GeminiClient
  (DEV)         (PROD)
  즉시 반환      실제 API 호출
  LangSmith ✗   LangSmith ✓
```

### 16.2. 파일 구조 및 역할

```
backend/app/infrastructure/llm/
├── interface.py        # 추상 인터페이스 ILLMClient — usecases가 참조하는 유일한 계약
├── gemini_client.py    # PROD: 실제 Gemini API + LangSmith @traceable 활성화
├── mock_client.py      # DEV:  PRD §3.3.3 스키마 고정 Mock JSON 즉시 반환
└── factory.py          # APP_MODE 기반 클라이언트 선택 팩토리
```

### 16.3. 추상 인터페이스 명세 (`interface.py`)

유즈케이스가 참조하는 **유일한 계약**. 구현체(Gemini/Mock)는 이 인터페이스를 반드시 구현한다.

```python
# backend/app/infrastructure/llm/interface.py
from abc import ABC, abstractmethod
from app.domain.models import ConceptExtractionSchema

class ILLMClient(ABC):
    """LLM 추출 클라이언트 추상 인터페이스 (DIP 계약).
    usecases 레이어는 이 인터페이스만 참조한다.
    구현체(GeminiClient / MockClient)는 factory.py가 주입한다.
    """

    @abstractmethod
    async def extract_concepts(
        self,
        text_chunk: str,
        doc_id: str,
        metadata: dict,
    ) -> list[ConceptExtractionSchema]:
        """공식 문서 청크에서 구조화 컨셉 스키마 목록을 추출한다.

        Args:
            text_chunk: Crawler Agent가 정제한 텍스트 청크
            doc_id:     마스터 키 (LangSmith Run 태그용)
            metadata:   {framework, version, lang} Pre-scan 추론값

        Returns:
            PRD §3.3.3 ConceptExtractionSchema 목록
            (concept_name, concept_domain, cwe_id, severity,
             description_ko, aliases, security_mechanisms,
             affected_components, config_properties, root_cause)
        """

    @abstractmethod
    def is_tracing_enabled(self) -> bool:
        """LangSmith 트레이싱 활성화 여부 반환.
        MockClient: False / GeminiClient: True (PROD)
        """
```

### 16.4. 상용 모드 구현체 (`gemini_client.py`)

```python
# backend/app/infrastructure/llm/gemini_client.py
from langsmith import traceable
from app.infrastructure.llm.interface import ILLMClient
from app.domain.models import ConceptExtractionSchema

class GeminiClient(ILLMClient):
    """PROD 모드: 실제 Gemini 2.5 Flash API + LangSmith 트레이싱 100% 활성화."""

    def __init__(self, api_key: str, langsmith_project: str):
        import google.generativeai as genai
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel("gemini-2.5-flash")
        self._project = langsmith_project

    @traceable(name="extractor_agent", tags=["extractor"])
    async def extract_concepts(
        self, text_chunk: str, doc_id: str, metadata: dict
    ) -> list[ConceptExtractionSchema]:
        prompt = _build_extraction_prompt(text_chunk, metadata)
        response = await self._model.generate_content_async(prompt)
        raw_json = _parse_json_safely(response.text)
        return [ConceptExtractionSchema(**item) for item in raw_json]

    def is_tracing_enabled(self) -> bool:
        return True
```

### 16.5. 개발 모드 구현체 (`mock_client.py`)

PRD §3.3.3에 정의된 4종 컨셉 타겟을 커버하는 **고정 스펙 Mock 데이터**를 반환한다. 네트워크 I/O 없이 즉시 반환하며 LangSmith를 비활성화한다.

```python
# backend/app/infrastructure/llm/mock_client.py
from app.infrastructure.llm.interface import ILLMClient
from app.domain.models import ConceptExtractionSchema

# PRD §3.3.3 4종 컨셉 타겟을 커버하는 고정 Mock 스펙
_MOCK_CONCEPTS: list[dict] = [
    {
        "concept_name":          "XSS",
        "concept_domain":        "security",
        "concept_type":          "vulnerability_root_cause",
        "cwe_id":                "CWE-79",
        "owasp_id":              "A03:2021",
        "severity":              "HIGH",
        "description_ko":        "크로스 사이트 스크립팅 — 사용자 입력이 HTML 컨텍스트에서 이스케이프 없이 출력됨",
        "aliases":               ["Cross-Site Scripting", "크로스 사이트 스크립팅"],
        "security_mechanisms":   ["OutputEncoding", "ContentSecurityPolicy"],
        "affected_components":   ["템플릿 렌더링 레이어", "API 응답 직렬화"],
        "config_properties":     [{"key": "SECURE_BROWSER_XSS_FILTER", "value": "True"}],
        "root_cause":            "사용자 입력값 HTML 이스케이프 미처리",
    },
    {
        "concept_name":          "N+1Query",
        "concept_domain":        "performance",
        "concept_type":          "vulnerability_root_cause",
        "cwe_id":                "CWE-1072",
        "severity":              "HIGH",
        "description_ko":        "ORM 관계 조회 시 N번 추가 쿼리 발생으로 DB 과부하",
        "aliases":               ["N+1 Query", "N+1 쿼리"],
        "security_mechanisms":   ["select_related", "prefetch_related"],
        "affected_components":   ["ORM 레이어", "DB 커넥션 풀"],
        "config_properties":     [],
        "root_cause":            "ORM Lazy Loading 기본값 미조정",
    },
    {
        "concept_name":          "MemoryLeak",
        "concept_domain":        "both",          # 교차 도메인 — :Security:Performance
        "concept_type":          "vulnerability_root_cause",
        "cwe_id":                "CWE-401",
        "severity":              "HIGH",
        "description_ko":        "객체 참조 미해제로 인한 GC 부하 및 힙 메모리 소진. 보안(자원 고갈) 및 성능 교차 영역",
        "aliases":               ["Memory Leak", "메모리 누수"],
        "security_mechanisms":   ["명시적 리소스 해제", "컨텍스트 매니저 사용"],
        "affected_components":   ["힙 메모리", "GC"],
        "config_properties":     [],
        "root_cause":            "객체 참조 순환 또는 명시적 해제 누락",
    },
    {
        "concept_name":          "CSRFProtection",
        "concept_domain":        "security",
        "concept_type":          "security_mechanism",  # 보안 메커니즘 타겟
        "cwe_id":                "CWE-352",
        "owasp_id":              "A01:2021",
        "severity":              "HIGH",
        "description_ko":        "크로스 사이트 요청 위조 방어 — CSRF 토큰 기반 상태 변경 요청 검증",
        "aliases":               ["CSRF Token", "CSRF 방어"],
        "security_mechanisms":   ["SameSiteCookie", "CSRFToken"],
        "affected_components":   ["세션 관리", "인증 모듈"],
        "config_properties":     [{"key": "CSRF_COOKIE_SECURE", "value": "True"}],
        "root_cause":            "요청 출처 검증 미적용",
    },
]

class MockClient(ILLMClient):
    """DEV 모드: 외부 API 호출 없이 고정 Mock 스펙 즉시 반환.
    - LangSmith 트레이싱 비활성화 (네트워크 I/O 차단)
    - 테스트 하네스 레이어 D (test_llm_eval.py) 의 Pydantic 검증 대상
    """

    async def extract_concepts(
        self, text_chunk: str, doc_id: str, metadata: dict
    ) -> list[ConceptExtractionSchema]:
        # 네트워크 I/O 없음 — 즉시 반환
        return [ConceptExtractionSchema(**item) for item in _MOCK_CONCEPTS]

    def is_tracing_enabled(self) -> bool:
        return False
```

### 16.6. 팩토리 — `APP_MODE` 기반 런타임 주입 (`factory.py`)

```python
# backend/app/infrastructure/llm/factory.py
from app.infrastructure.llm.interface import ILLMClient

def create_llm_client(settings) -> ILLMClient:
    """APP_MODE 환경변수에 따라 LLM 클라이언트를 선택 주입한다.
    애플리케이션 코드(usecases)는 이 팩토리를 직접 호출하지 않는다.
    FastAPI 의존성 주입(Depends) 또는 Celery 태스크 초기화 시 1회 호출된다.
    """
    if settings.APP_MODE == "production":
        from app.infrastructure.llm.gemini_client import GeminiClient
        return GeminiClient(
            api_key=settings.GEMINI_API_KEY,
            langsmith_project=settings.LANGCHAIN_PROJECT,
        )
    else:  # development (기본값)
        from app.infrastructure.llm.mock_client import MockClient
        return MockClient()
```

### 16.7. 인프라 불가지론적 런타임 구동 모드 (`APP_MODE`)

| 항목 | `APP_MODE=development` | `APP_MODE=production` |
|------|------------------------|----------------------|
| LLM 호출 | `MockClient` — 즉시 고정값 반환 | `GeminiClient` — 실제 Gemini 2.5 Flash |
| LangSmith 트레이싱 | `LANGCHAIN_TRACING_V2=false` 강제 | 100% 활성화 (Pre-Eval · 트레이싱 · 피드백 루프) |
| 네트워크 I/O | 없음 (비용·지연 없음) | Gemini API + LangSmith 엔드포인트 |
| 테스트 하네스 연동 | `CELERY_TASK_ALWAYS_EAGER=True`와 조합 | 하네스 환경에서는 사용 안 함 |
| `.env` 설정 | `APP_MODE=development` | `APP_MODE=production` |

**`.env.local` 추가 항목**:
```bash
APP_MODE=development
# LangSmith 강제 비활성화 (MockClient가 자동 처리하지만 명시적 선언 권장)
LANGCHAIN_TRACING_V2=false
```

**`.env.prod` 추가 항목**:
```bash
APP_MODE=production
LANGCHAIN_TRACING_V2=true
```

### 16.8. 유즈케이스에서의 사용 패턴

유즈케이스는 `ILLMClient` 인터페이스만 참조한다. `GeminiClient`인지 `MockClient`인지 알지 못하며 알 필요도 없다.

```python
# backend/app/usecases/run_pipeline.py
from app.infrastructure.llm.interface import ILLMClient

class RunPipelineUsecase:
    def __init__(
        self,
        llm_client: ILLMClient,        # 인터페이스만 참조 — 구현체 무관
        pg_repo,                        # IRepository 구현체
        graph_service,                  # IGraphService 구현체
    ):
        self.llm = llm_client

    async def execute(self, doc_id: str, text_chunks: list[str], metadata: dict):
        all_concepts = []
        for chunk in text_chunks:
            concepts = await self.llm.extract_concepts(
                text_chunk=chunk,
                doc_id=doc_id,
                metadata=metadata,
            )
            all_concepts.extend(concepts)
        # 이하 staging INSERT 로직 — DB 구현체와도 인터페이스로만 통신
        await self.pg_repo.insert_staging_draft(doc_id, all_concepts)
```

### 16.9. SDD & TDD (AAA 패턴) — Mock 레이어 검증 명세

#### T09. MockClient 즉시 반환 및 스키마 검증 (레이어 D 확장)

| 항목 | 내용 |
|------|------|
| Spec (SDD) | `APP_MODE=development`일 때 LLM 호출 없이 4종 컨셉 Mock 데이터 반환 |
| Assert 목표 | 반환값이 `ILLMClient` 계약을 만족하고 Pydantic 검증 통과 |

```python
# tests/harness/test_llm_eval.py — T09 추가

def test_mock_client_returns_spec_schema():
    # Arrange
    mock_client = MockClient()

    # Act
    concepts = asyncio.run(
        mock_client.extract_concepts(
            text_chunk="dummy text",
            doc_id="EXT_test_00000000",
            metadata={"framework": "Django", "version": "5.0", "lang": "EN"},
        )
    )

    # Assert 1: 4종 컨셉 타겟 모두 포함
    domains   = {c.concept_domain for c in concepts}
    types_set = {c.concept_type   for c in concepts}
    assert "security"    in domains
    assert "performance" in domains
    assert "both"        in domains          # 교차 도메인 존재
    assert "vulnerability_root_cause" in types_set
    assert "security_mechanism"       in types_set  # §3.3.3 4종 중 보안 메커니즘

    # Assert 2: Pydantic 스키마 완전성
    for c in concepts:
        assert c.concept_domain in {"security", "performance", "both"}
        assert isinstance(c.aliases, list)
        assert len(c.description_ko) > 0

    # Assert 3: LangSmith 트레이싱 비활성화
    assert mock_client.is_tracing_enabled() is False
```

#### T10. 팩토리 주입 분기 검증

| 항목 | 내용 |
|------|------|
| Spec (SDD) | `APP_MODE` 값에 따라 올바른 클라이언트 타입이 주입됨 |
| Assert | `development` → `MockClient`, `production` → `GeminiClient` 인스턴스 |

```python
def test_factory_injects_correct_client():
    # Arrange / Act / Assert — development
    from unittest.mock import MagicMock
    dev_settings  = MagicMock(APP_MODE="development")
    prod_settings = MagicMock(APP_MODE="production",
                              GEMINI_API_KEY="key", LANGCHAIN_PROJECT="proj")

    dev_client  = create_llm_client(dev_settings)
    assert isinstance(dev_client, MockClient)
    assert dev_client.is_tracing_enabled() is False

    # production 분기는 실제 API 키 없이 클래스 타입만 검증
    with patch("app.infrastructure.llm.gemini_client.GeminiClient.__init__",
               return_value=None):
        prod_client = create_llm_client(prod_settings)
        assert isinstance(prod_client, GeminiClient)
```

#### T11. 유즈케이스 — Mock 주입 후 운영 DB 격리 통합 검증

| 항목 | 내용 |
|------|------|
| Spec (SDD) | MockClient가 주입된 상태에서 파이프라인을 실행하면 staging_concepts에만 DRAFT 레코드가 적재됨 |
| Assert | concepts 테이블과 Neo4j = 0건, staging_concepts DRAFT = 1건 |

```python
def test_pipeline_with_mock_llm_isolates_master_db(
    db_session, neo4j_session, celery_app
):
    # Arrange: MockClient 주입 (Gemini API 호출 없음)
    mock_llm = MockClient()
    usecase  = RunPipelineUsecase(
        llm_client=mock_llm,
        pg_repo=PgRepository(db_session),
        graph_service=Neo4jService(neo4j_session),
    )

    # Act: 파이프라인 실행 (ALWAYS_EAGER = 동기)
    asyncio.run(usecase.execute(
        doc_id="EXT_test_mock_abc12345",
        text_chunks=["dummy chunk"],
        metadata={"framework": "Django", "version": "5.0", "lang": "EN"},
    ))

    # Assert 1: 운영 테이블 미접촉
    assert db_session.execute("SELECT COUNT(*) FROM concepts").scalar() == 0
    assert neo4j_session.run("MATCH (c:Concept) RETURN count(c) AS n").single()["n"] == 0

    # Assert 2: staging에만 DRAFT 적재
    draft_count = db_session.execute(
        "SELECT COUNT(*) FROM staging_concepts WHERE state='DRAFT'"
    ).scalar()
    assert draft_count == len(_MOCK_CONCEPTS)  # 4종 Mock 개념 수
```

**DoD 업데이트 — QA 기준 추가**:

```
tests/harness/test_llm_eval.py       PASSED [100%]
  T07  스키마 유효성 (기존)
  T08  LangSmith 피드백 Mock (기존)
  T09  MockClient 4종 스펙 및 트레이싱 비활성화
  T10  factory APP_MODE 분기 주입
  T11  Mock 주입 + 운영 DB 격리 통합

==================== 11 passed in 3.12s ====================
```