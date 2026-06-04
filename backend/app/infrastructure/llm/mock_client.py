"""MockClient — DEV 모드 고정 스펙 반환 (네트워크 I/O 없음). PRD §16.5."""

from app.domain.models import ConceptExtractionSchema, ConceptDomain
from app.infrastructure.llm.interface import ILLMClient

# OWASP 2025 ID 기준 (A03:2025 = Injection, A01:2025 = Broken Access Control)
_MOCK_CONCEPTS: list[dict] = [
    {
        "concept_name": "XSS",
        "concept_domain": ConceptDomain.SECURITY,
        "concept_type": "vulnerability_root_cause",
        "cwe_id": "CWE-79",
        "owasp_id": "A03:2025",
        "severity": "HIGH",
        "description_ko": "크로스 사이트 스크립팅 — 사용자 입력이 HTML 컨텍스트에서 이스케이프 없이 출력됨",
        "aliases": ["Cross-Site Scripting", "크로스 사이트 스크립팅"],
        "security_mechanisms": ["OutputEncoding", "ContentSecurityPolicy"],
        "affected_components": ["템플릿 렌더링 레이어", "API 응답 직렬화"],
        "config_properties": [{"key": "SECURE_BROWSER_XSS_FILTER", "value": "True"}],
        "root_cause": "사용자 입력값 HTML 이스케이프 미처리",
    },
    {
        "concept_name": "N+1Query",
        "concept_domain": ConceptDomain.PERFORMANCE,
        "concept_type": "vulnerability_root_cause",
        "cwe_id": "CWE-1072",
        "severity": "HIGH",
        "description_ko": "ORM 관계 조회 시 N번 추가 쿼리 발생으로 DB 과부하",
        "aliases": ["N+1 Query", "N+1 쿼리"],
        "security_mechanisms": ["select_related", "prefetch_related"],
        "affected_components": ["ORM 레이어", "DB 커넥션 풀"],
    },
    {
        "concept_name": "MemoryLeak",
        "concept_domain": ConceptDomain.BOTH,
        "concept_type": "vulnerability_root_cause",
        "cwe_id": "CWE-401",
        "severity": "HIGH",
        "description_ko": "객체 참조 미해제로 인한 GC 부하 및 힙 메모리 소진",
        "aliases": ["Memory Leak", "메모리 누수"],
        "security_mechanisms": ["명시적 리소스 해제", "컨텍스트 매니저 사용"],
        "affected_components": ["힙 메모리", "GC"],
    },
    {
        "concept_name": "CSRFProtection",
        "concept_domain": ConceptDomain.SECURITY,
        "concept_type": "security_mechanism",
        "cwe_id": "CWE-352",
        "owasp_id": "A01:2025",
        "severity": "HIGH",
        "description_ko": "크로스 사이트 요청 위조 방어 — CSRF 토큰 기반 상태 변경 요청 검증",
        "aliases": ["CSRF Token", "CSRF 방어"],
        "security_mechanisms": ["SameSiteCookie", "CSRFToken"],
        "affected_components": ["세션 관리", "인증 모듈"],
        "config_properties": [{"key": "CSRF_COOKIE_SECURE", "value": "True"}],
    },
]


class MockClient(ILLMClient):
    """DEV/TEST 전용 클라이언트. 네트워크 호출 없이 즉시 고정값 반환."""

    async def extract_concepts(
        self,
        text_chunk: str,
        doc_id: str,
        metadata: dict,
    ) -> list[ConceptExtractionSchema]:
        return [ConceptExtractionSchema(**item) for item in _MOCK_CONCEPTS]

    def is_tracing_enabled(self) -> bool:
        return False
