-- Migration 004: categories 테이블 추가
-- VALID_CATEGORIES 코드 상수를 DB화해 런타임 카테고리 확장을 가능하게 한다.

CREATE TABLE IF NOT EXISTS categories (
    id          SERIAL       PRIMARY KEY,
    name        VARCHAR(100) NOT NULL UNIQUE,
    description TEXT         NOT NULL DEFAULT '',
    active      BOOLEAN      NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

-- 기존 6개 카테고리 seed
INSERT INTO categories (name, description) VALUES
    ('코딩컨벤션', '코딩 스타일, 네이밍 규칙, 코드 품질 가이드, 개발 표준'),
    ('아키텍처',   'SW 설계, 시스템 구조, 아키텍처 패턴, NCS SW아키텍처 수행관리'),
    ('온보딩',     '신입 교육, 입문 가이드, 개발 환경 설정, 팀 규칙 안내'),
    ('보안',       '보안 취약점, 인증·인가, 데이터 보호, 보안 정책'),
    ('배포',       'CI/CD, 배포 프로세스, Docker, Kubernetes, 인프라 운영'),
    ('기타',       '위 카테고리에 명확히 해당하지 않는 경우 (마지막 수단)')
ON CONFLICT (name) DO NOTHING;
