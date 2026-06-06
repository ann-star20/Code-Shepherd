---
source_of_truth:
  - scripts/seed/common/schema.sql
---

## 보안 도메인 시드 데이터 적재 및 검증 명세

### 1. 구조 설계 원칙 (Data-Driven Isolation)
- **런타임 확장성 보장**: OWASP Category 메타데이터는 하드코딩된 열거형(Enum)이 아닌, 동적 테이블 관리를 통해 관리자가 런타임에 유연하게 등록 및 변경할 수 있도록 설계한다.
- **다중 도메인 매핑 유연성**: `cwe_ids` 배열 필드를 지원하기 위해 스키마 v2 계약과 정합성을 100% 매핑한다.
- **멱등성 보장**: 이미 동일 데이터가 적재되어 있는 환경에서 중복 실행되더라도 무결성이 깨지지 않도록 `ON CONFLICT DO NOTHING` 문법을 강제한다.

### 2. TDD (AAA) 검증 명세
- **Arrange**: 데이터베이스 초기화 및 `schema.sql` 테이블 기동 완료 상태.
- **Act**: `psql -f seed_data.sql` 스크립트를 총 2회 연속 트리거.
- **Assert 1**: `domain_registry` 내 'security' 항목의 `color_hex`가 정상 변경/유지됨.
- **Assert 2**: `owasp_categories` 테이블 총 레코드 수가 정확히 **10건**으로 고정됨을 검증.

### 3. COMMIT CONVENTION
```bash
feat(db): seed updated owasp top 10 2025 security data assets
```
---

### 2. PostgreSQL 초기 시드 스크립트 (`scripts/seed/security/seed_data.sql`)

```sql
-- Knowledge Graph Agent Pipeline — Security Domain Seed SQL v2
-- Spec: PRD-schema.md §15.2 / scripts/seed/security/
-- Run: psql -h localhost -p 5433 -U postgres -d postgres -f seed_data.sql

BEGIN;

-- =========================================================================
-- 1. domain_registry 동적 색상 및 레이블 동기화 (멱등성 보장)
-- =========================================================================
INSERT INTO domain_registry (name, label_ko, description, color_hex, is_active)
VALUES (
  'security', 
  '보안', 
  'OWASP Top 10 및 웹 애플리케이션 보안 취약점 원인/메커니즘 도메인', 
  '#1D9E75', 
  true
)
ON CONFLICT (name) DO UPDATE 
SET color_hex = EXCLUDED.color_hex,
    description = EXCLUDED.description,
    updated_at = now();

-- =========================================================================
-- 2. owasp_categories 테이블 구성 및 2025 데이터셋 벌크 적재
-- =========================================================================
CREATE TABLE IF NOT EXISTS owasp_categories (
    owasp_id       TEXT PRIMARY KEY,
    name           TEXT NOT NULL,
    name_ko        TEXT NOT NULL,
    severity       TEXT NOT NULL,
    cwe_ids        TEXT[] DEFAULT '{}',
    description_ko TEXT,
    created_at     TIMESTAMPTZ DEFAULT now(),
    updated_at     TIMESTAMPTZ,
    CONSTRAINT owasp_severity_check CHECK (severity IN ('critical', 'high', 'medium', 'low'))
);

CREATE INDEX IF NOT EXISTS idx_owasp_categories_severity ON owasp_categories(severity);

INSERT INTO owasp_categories (owasp_id, name, name_ko, severity, cwe_ids, description_ko, updated_at) VALUES
('A01:2025', 'Broken Access Control', '취약한 접근 제어', 'critical', ARRAY['CWE-200', 'CWE-201', 'CWE-352'], '인증된 사용자가 수행해서는 안 되는 행위를 수행할 수 있는 취약점. 최소 권한 원칙 위반, IDOR, 디렉터리 탐색 등이 포함된다.', now()),
('A02:2025', 'Cryptographic Failures', '암호화 실패', 'high', ARRAY['CWE-259', 'CWE-327', 'CWE-331'], '민감한 데이터를 암호화하지 않거나 약한 암호화를 사용하여 데이터가 노출되는 취약점. 전송 중 및 저장 중 데이터 모두 해당된다.', now()),
('A03:2025', 'Injection', '인젝션', 'critical', ARRAY['CWE-79', 'CWE-89', 'CWE-73'], '신뢰할 수 없는 데이터가 명령어나 쿼리의 일부로 인터프리터에 전달되는 취약점. SQL, NoSQL, OS 명령어, LDAP 인젝션과 XSS가 포함된다.', now()),
('A04:2025', 'Insecure Design', '안전하지 않은 설계', 'high', ARRAY['CWE-657', 'CWE-840', 'CWE-1176'], '위협 모델링, 보안 설계 패턴 부재로 인한 설계 단계의 결함. 구현 버그가 아닌 근본적인 설계 취약점을 의미한다.', now()),
('A05:2025', 'Security Misconfiguration', '보안 설정 오류', 'high', ARRAY['CWE-16', 'CWE-611', 'CWE-732'], '기본 계정/비밀번호 사용, 불필요한 기능 활성화, 상세 오류 메시지 노출 등 잘못된 보안 설정으로 인한 취약점.', now()),
('A06:2025', 'Vulnerable and Outdated Components', '취약하고 오래된 컴포넌트', 'medium', ARRAY['CWE-1104'], '알려진 취약점이 있는 라이브러리, 프레임워크, 기타 소프트웨어 모듈을 사용할 때 발생하는 위험.', now()),
('A07:2025', 'Identification and Authentication Failures', '인증 및 식별 실패', 'high', ARRAY['CWE-297', 'CWE-287', 'CWE-384'], '세션 관리, 자격증명 관리의 취약점. 브루트포스 허용, 약한 비밀번호 정책, 불안전한 세션 토큰이 포함된다.', now()),
('A08:2025', 'Software and Data Integrity Failures', '소프트웨어 및 데이터 무결성 실패', 'high', ARRAY['CWE-502', 'CWE-829', 'CWE-494'], '무결성 검증 없이 업데이트, 중요 데이터, 플러그인을 신뢰하는 취약점. 안전하지 않은 역직렬화와 CI/CD 파이프라인 취약점 포함.', now()),
('A09:2025', 'Security Logging and Monitoring Failures', '보안 로깅 및 모니터링 실패', 'medium', ARRAY['CWE-778', 'CWE-117', 'CWE-223'], '침해 사고 탐지와 대응에 필수적인 로깅·모니터링 부재. 감사 로그 없음, 의심 활동 미감지 등이 포함된다.', now()),
('A10:2025', 'Server-Side Request Forgery', '서버 측 요청 위조', 'high', ARRAY['CWE-918'], '공격자가 서버로 하여금 의도치 않은 위치로 요청을 보내도록 유도하는 취약점. 내부 서비스, 클라우드 메타데이터 엔드포인트 접근에 주로 악용된다.', now())
ON CONFLICT (owasp_id) DO UPDATE 
SET name = EXCLUDED.name,
    name_ko = EXCLUDED.name_ko,
    severity = EXCLUDED.severity,
    cwe_ids = EXCLUDED.cwe_ids,
    description_ko = EXCLUDED.description_ko,
    updated_at = now();

COMMIT;

```