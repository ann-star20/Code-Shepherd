
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

**교차 도메인 MERGE Cypher**:

```cypher
// 1. 노드 생성 또는 병합 (name 기준 단일 노드 보장)
MERGE (c:Concept {name: "MemoryLeak"})
ON CREATE SET
  c.aliases      = ["Memory Leak", "메모리 누수"],
  c.cwe_id       = "CWE-401",
  c.description_ko = "객체 참조 미해제로 인한 GC 부하 및 힙 메모리 소진",
  c.created_at   = timestamp()
ON MATCH SET
  c.updated_at   = timestamp()

// 2. 도메인 라벨 누적 부여 (기존 라벨 제거 없이 추가만)
WITH c
CALL apoc.create.addLabels(c, ["Security", "Performance"]) YIELD node
RETURN node
```

**조회 패턴**:
```cypher
// 보안 도메인 Concept만 조회
MATCH (c:Concept:Security) RETURN c

// 성능 도메인 Concept만 조회
MATCH (c:Concept:Performance) RETURN c

// 교차 도메인 Concept 조회 ("보안이면서 성능이기도 한" 노드)
MATCH (c:Concept:Security:Performance) RETURN c

// "MemoryLeak" 키워드 + 보안 컨텍스트 조회
MATCH (c:Concept:Security {name: "MemoryLeak"}) RETURN c

// aliases 포함 전체 검색 (키워드 "메모리 누수")
MATCH (c:Concept) WHERE "메모리 누수" IN c.aliases RETURN c
```

**Extractor Agent 라벨 결정 로직**:
Extractor가 LLM 추출 결과 JSON에서 `concept_domain` 필드를 반환하면, Graph Writer가 아래 매핑으로 라벨을 결정한다.

```python
DOMAIN_LABEL_MAP = {
    "security":     ["Security"],
    "performance":  ["Performance"],
    "both":         ["Security", "Performance"],
}
# LLM이 모호하게 판단한 경우 Link Resolver가 사후 라벨 추가
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
---

### 규칙 ② — 멱등성 기반 자성 커밋 (Idempotent MERGE Commit)

**규칙**: 네트워크 지연으로 동일 승인 태스크가 Celery 큐에서 이중 실행되어도 마스터 DB는 안전해야 한다.

**구현 제약**: Neo4j 적재 시 반드시 `Concept.name`을 유니크 식별 키로 `MERGE ... ON CREATE SET ... ON MATCH SET` 구문을 사용한다. 동일 데이터 재입력 시 노드 중복 생성 없이 `updated_at` 타임스탬프만 갱신된다.

```cypher
MERGE (c:Concept {name: $name})
ON CREATE SET
  c.cwe_id        = $cwe_id,
  c.description_ko = $description_ko,
  c.aliases       = $aliases,
  c.created_at    = timestamp()
ON MATCH SET
  c.updated_at    = timestamp()
WITH c
CALL apoc.create.addLabels(c, $domain_labels) YIELD node
RETURN node
```

### 규칙 ③ — 후행 Link Resolver 트리거 연동

**규칙**: 개념 노드가 Neo4j 마스터에 최종 커밋(`COMMITTED`)된 직후, 백엔드는 5단계 Link Resolver Agent 태스크를 자동 트리거해야 한다.

**동작**: 새로 커밋된 `Concept` 노드의 `aliases` 배열과 기존 그래프 내 노드들의 유사도를 즉시 계산하여 `SAME_AS` 또는 `RELATED_TO` 관계를 맺는 후속 커밋까지 완료되어야 한 세션의 커밋 프로세스가 완전히 종료된 것으로 간주한다.

```python
async def commit_to_master(session_id: str, approved_concepts: list):
    # ... (규칙 ① 코드) ...
    # 커밋 완료 후 Link Resolver 자동 트리거
    for concept in approved_concepts:
        resolve_links_task.delay(concept_name=concept["name"])
    # resolve_links_task 완료 시점까지 세션 상태는 COMMITTED_PENDING_RESOLVE
    # 관계 맺기 완료 후 COMMITTED로 최종 전환
```

**세션 상태 전이 확장**:

```
APPROVED → COMMITTING → COMMITTED_PENDING_RESOLVE → COMMITTED(완전 종료)
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

| 규칙 | 핵심 보장 | 실패 시 동작 |
|------|-----------|-------------|
| ① 2단계 크로스 DB 트랜잭션 | PG + Neo4j 원자성 | Neo4j 실패 → PG 롤백 |
| ② 멱등성 MERGE Commit | 이중 실행 안전 | 노드 중복 없이 타임스탬프만 갱신 |
| ③ Link Resolver 자동 트리거 | 고립 노드 방지 | 관계 미연결 시 COMMITTED 미전환 |
| ④ Document 상태 동기화 | 대시보드 정합성 | 동일 트랜잭션 내 즉시 반영 |
