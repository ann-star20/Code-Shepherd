// =========================================================================
// Knowledge Graph Agent Pipeline — security Domain Ontology Seed Cypher
// Spec: PRD-schema.md §15.3 / scripts/seed/security/
// =========================================================================

// ── 0. 전제 조건 및 인덱스 빌드 ───────────────────────────────────────────
CREATE INDEX domain_name_idx IF NOT EXISTS FOR (d:Domain) ON (d.name);
CREATE INDEX owasp_id_idx IF NOT EXISTS FOR (o:OWASPCategory) ON (o.owasp_id);
CREATE INDEX cwe_id_idx IF NOT EXISTS FOR (c:CWE) ON (c.cwe_id);

// ── 1. 핵심 Root Domain 노드 선언 ────────────────────────────────────────
MERGE (d:Domain {name: 'security'})
ON CREATE SET d.description_ko = '웹 애플리케이션 보안 취약점 식별 및 대응 도메인',
              d.created_at = timestamp()
ON MATCH SET  d.updated_at = timestamp();

// ── 2. OWASP Top 10 2025 카테고리 벌크 적재 ─────────────────────────────
UNWIND [
  {owasp_id: "A01:2025", name: "Broken Access Control", name_ko: "취약한 접근 제어", severity: "critical", description_ko: "인증된 사용자가 수행해서는 안 되는 행위를 수행할 수 있는 취약점. IDOR, 최소 권한 원칙 위반 포함."},
  {owasp_id: "A02:2025", name: "Cryptographic Failures", name_ko: "암호화 실패", severity: "high", description_ko: "민감한 데이터를 암호화하지 않거나 약한 암호화를 사용하여 데이터가 노출되는 취약점."},
  {owasp_id: "A03:2025", name: "Injection", name_ko: "인젝션", severity: "critical", description_ko: "신뢰할 수 없는 데이터가 명령어나 쿼리의 일부로 인터프리터에 전달되는 취약점. SQL·XSS·OS 명령 인젝션 포함."},
  {owasp_id: "A04:2025", name: "Insecure Design", name_ko: "안전하지 않은 설계", severity: "high", description_ko: "위협 모델링, 보안 설계 패턴 부재로 인한 설계 단계의 결함."},
  {owasp_id: "A05:2025", name: "Security Misconfiguration", name_ko: "보안 설정 오류", severity: "high", description_ko: "기본 계정/비밀번호 사용, 불필요한 기능 활성화, 상세 오류 메시지 노출 등 잘못된 보안 설정."},
  {owasp_id: "A06:2025", name: "Vulnerable and Outdated Components", name_ko: "취약하고 오래된 컴포넌트", severity: "medium", description_ko: "알려진 취약점이 있는 구버전 라이브러리·프레임워크·OS 사용."},
  {owasp_id: "A07:2025", name: "Identification and Authentication Failures", name_ko: "식별 및 인증 실패", severity: "high", description_ko: "인증 메커니즘이 잘못 구현되어 공격자가 다른 사용자 계정을 탈취하거나 권한 있는 접근을 획득."},
  {owasp_id: "A08:2025", name: "Software and Data Integrity Failures", name_ko: "소프트웨어 및 데이터 무결성 실패", severity: "high", description_ko: "무결성 검증 없이 소프트웨어 업데이트, 중요 데이터, CI/CD 파이프라인을 처리하는 취약점."},
  {owasp_id: "A09:2025", name: "Security Logging and Monitoring Failures", name_ko: "보안 로깅 및 모니터링 실패", severity: "medium", description_ko: "공격 탐지·대응에 필요한 로깅 및 모니터링 부재로 공격자의 지속적 공격을 허용."},
  {owasp_id: "A10:2025", name: "Server-Side Request Forgery", name_ko: "서버 사이드 요청 위조", severity: "high", description_ko: "서버가 공격자가 제공한 URL로 요청을 전송하여 내부 서비스·클라우드 메타데이터에 접근."}
] AS cat
MERGE (o:OWASPCategory {owasp_id: cat.owasp_id})
ON CREATE SET o.name = cat.name,
              o.name_ko = cat.name_ko,
              o.severity = cat.severity,
              o.description_ko = cat.description_ko,
              o.created_at = timestamp()
ON MATCH SET  o.updated_at = timestamp();

// ── 3. Domain ──▶ OWASPCategory 계층 관계 선언 ──────────────────────────
MATCH (d:Domain {name: 'security'})
MATCH (o:OWASPCategory)
MERGE (d)-[:BELONGS_TO]->(o);

// ── 4. 연관 CWE 상세 노드 벌크 적재 ──────────────────────────────────────
UNWIND [
  {cwe_id: "CWE-79", name: "Cross-site Scripting", description_ko: "사용자 입력이 이스케이프 없이 HTML에 출력됨"},
  {cwe_id: "CWE-89", name: "SQL Injection", description_ko: "SQL 쿼리에 사용자 입력이 비위생화된 채 삽입됨"},
  {cwe_id: "CWE-352", name: "Cross-Site Request Forgery", description_ko: "인증된 사용자의 브라우저를 통한 의도치 않은 요청 실행"},
  {cwe_id: "CWE-284", name: "Improper Access Control", description_ko: "권한 검사 누락 또는 잘못된 구현"},
  {cwe_id: "CWE-502", name: "Deserialization of Untrusted Data", description_ko: "신뢰할 수 없는 데이터를 역직렬화하여 원격 코드 실행 가능"},
  {cwe_id: "CWE-918", name: "Server-Side Request Forgery", description_ko: "서버가 공격자 제어 URL로 요청 전송"},
  {cwe_id: "CWE-287", name: "Improper Authentication", description_ko: "신원 확인 메커니즘 결함"},
  {cwe_id: "CWE-384", name: "Session Fixation", description_ko: "로그인 후 세션 ID 미갱신으로 인한 세션 고정 공격"},
  {cwe_id: "CWE-200", name: "Exposure of Sensitive Information", description_ko: "민감 정보가 권한 없는 주체에 노출"},
  {cwe_id: "CWE-327", name: "Use of Broken Crypto Algorithm", description_ko: "취약하거나 deprecated된 암호화 알고리즘 사용"},
  {cwe_id: "CWE-259", name: "Use of Hard-coded Password", description_ko: "하드코딩된 자격증명"},
  {cwe_id: "CWE-16", name: "Configuration", description_ko: "잘못된 보안 설정으로 인한 취약점"},
  {cwe_id: "CWE-611", name: "XXE", description_ko: "XML 외부 엔티티 처리로 인한 정보 노출"},
  {cwe_id: "CWE-521", name: "Weak Password Requirements", description_ko: "너무 단순한 비밀번호 정책 허용"},
  {cwe_id: "CWE-829", name: "Inclusion of Functionality from Untrusted Control Sphere", description_ko: "신뢰할 수 없는 소스에서 기능 포함"},
  {cwe_id: "CWE-778", name: "Insufficient Logging", description_ko: "보안 이벤트 로깅 미흡"},
  {cwe_id: "CWE-1104", name: "Use of Unmaintained Third Party", description_ko: "유지보수 중단 서드파티 컴포넌트 사용"},
  {cwe_id: "CWE-73", name: "External Control of File Name", description_ko: "경로 조작을 통한 파일 접근"},
  {cwe_id: "CWE-657", name: "Violation of Secure Design Principles", description_ko: "보안 설계 원칙 위반"},
  {cwe_id: "CWE-732", name: "Incorrect Permission Assignment", description_ko: "잘못된 권한 부여"},
  {cwe_id: "CWE-331", name: "Insufficient Entropy", description_ko: "예측 가능한 난수 사용"},
  {cwe_id: "CWE-201", name: "Exposure via Error Message", description_ko: "오류 메시지를 통한 민감 정보 노출"},
  {cwe_id: "CWE-223", name: "Omission of Security Info in Log", description_ko: "로그에서 보안 관련 정보 누락"}
] AS cwe
MERGE (c:CWE {cwe_id: cwe.cwe_id})
ON CREATE SET c.name = cwe.name,
              c.description_ko = cwe.description_ko,
              c.created_at = timestamp()
ON MATCH SET  c.updated_at = timestamp();

// ── 5. OWASPCategory ──▶ CWE 매핑 관계 구축 (MAPS_TO 멱등 관계) ─────────
UNWIND [
  {owasp_id: "A01:2025", cwe_ids: ["CWE-200", "CWE-201", "CWE-284", "CWE-352"]},
  {owasp_id: "A02:2025", cwe_ids: ["CWE-259", "CWE-327", "CWE-331"]},
  {owasp_id: "A03:2025", cwe_ids: ["CWE-79", "CWE-89", "CWE-73"]},
  {owasp_id: "A04:2025", cwe_ids: ["CWE-657", "CWE-840", "CWE-1176"]},
  {owasp_id: "A05:2025", cwe_ids: ["CWE-16", "CWE-611", "CWE-732"]},
  {owasp_id: "A06:2025", cwe_ids: ["CWE-1104"]},
  {owasp_id: "A07:2025", cwe_ids: ["CWE-287", "CWE-384", "CWE-521"]},
  {owasp_id: "A08:2025", cwe_ids: ["CWE-502", "CWE-829"]},
  {owasp_id: "A09:2025", cwe_ids: ["CWE-778", "CWE-223"]},
  {owasp_id: "A10:2025", cwe_ids: ["CWE-918"]}
] AS mapping
MATCH (o:OWASPCategory {owasp_id: mapping.owasp_id})
UNWIND mapping.cwe_ids AS target_cwe
MATCH (c:CWE {cwe_id: target_cwe})
MERGE (o)-[:MAPS_TO]->(c);