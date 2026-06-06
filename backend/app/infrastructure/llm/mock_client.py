"""MockClient — DEV/mock 모드 고정 스펙 반환.

샘플 데이터: https://docs.djangoproject.com/en/6.0/ref/csrf/
APP_MODE=mock 시 Gemini 호출 없이 이 데이터를 반환한다.
"""

from app.domain.models import ConceptExtractionSchema
from app.infrastructure.llm.interface import ILLMClient

_MOCK_CONCEPTS: list[dict] = [
    {
        "concept_name": "CSRFAttack",
        "domains": ["security"],
        "concept_type": "vulnerability_root_cause",
        "cwe_id": "CWE-352",
        "owasp_id": "A01:2021",
        "severity": "high",
        "description_ko": "크로스 사이트 요청 위조 — 인증된 사용자의 브라우저를 통해 악의적 요청을 서버에 전송하는 공격",
        "aliases": ["CSRF", "XSRF", "Sea Surf", "Cross-Site Request Forgery"],
        "security_mechanism": ["CSRFToken", "SameSiteCookie", "OriginCheck"],
        "affected_components": ["폼 제출 처리", "상태 변경 API", "세션 관리"],
        "root_cause": "서버가 요청 출처를 검증하지 않고 브라우저 쿠키 기반 인증만 의존",
        "code_examples": [
            {
                "lang": "html",
                "framework": "Django",
                "code": (
                    "<!-- 악의적 사이트의 자동 제출 폼 -->\n"
                    "<form action='https://bank.com/transfer' method='post'>\n"
                    "  <input name='amount' value='1000'>\n"
                    "</form>"
                ),
            }
        ],
    },
    {
        "concept_name": "CsrfViewMiddleware",
        "domains": ["security"],
        "concept_type": "security_mechanism",
        "cwe_id": "CWE-352",
        "owasp_id": "A01:2021",
        "severity": "high",
        "description_ko": "Django의 CSRF 보호 미들웨어 — POST/PUT/DELETE 요청마다 토큰 검증 수행",
        "aliases": ["django.middleware.csrf.CsrfViewMiddleware", "CSRF Middleware"],
        "security_mechanism": ["CSRFTokenValidation", "OriginCheck", "RefererCheck"],
        "affected_components": ["MIDDLEWARE 설정", "HTTP 요청 처리 파이프라인"],
        "config_properties": [
            {"key": "CSRF_COOKIE_SECURE", "value": "True"},
            {"key": "CSRF_COOKIE_HTTPONLY", "value": "False"},
            {"key": "CSRF_COOKIE_SAMESITE", "value": "'Lax'"},
            {"key": "CSRF_TRUSTED_ORIGINS", "value": "['https://example.com']"},
        ],
        "code_examples": [
            {
                "lang": "python",
                "framework": "Django",
                "code": (
                    "MIDDLEWARE = [\n"
                    "    ...\n"
                    "    'django.middleware.csrf.CsrfViewMiddleware',\n"
                    "    ...\n"
                    "]"
                ),
            }
        ],
    },
    {
        "concept_name": "CsrfTokenTag",
        "domains": ["security"],
        "concept_type": "security_mechanism",
        "cwe_id": "CWE-352",
        "severity": "medium",
        "description_ko": "Django 템플릿 태그 — POST 폼에 CSRF 토큰 hidden input 자동 삽입",
        "aliases": ["csrf_token", "{% csrf_token %}", "csrf_token template tag"],
        "security_mechanism": ["CSRFTokenEmbed"],
        "affected_components": ["Django 템플릿 엔진", "HTML 폼"],
        "code_examples": [
            {
                "lang": "html",
                "framework": "Django",
                "code": (
                    "<form method='post'>\n"
                    "  {% csrf_token %}\n"
                    "  {{ form.as_p }}\n"
                    "  <button type='submit'>Submit</button>\n"
                    "</form>"
                ),
            }
        ],
    },
    {
        "concept_name": "CsrfExempt",
        "domains": ["security"],
        "concept_type": "vulnerability_root_cause",
        "cwe_id": "CWE-352",
        "severity": "high",
        "description_ko": "@csrf_exempt — 특정 뷰의 CSRF 검증 비활성화. 대체 인증 없이 사용 시 취약점 노출",
        "aliases": ["@csrf_exempt", "csrf_exempt decorator"],
        "security_mechanism": [],
        "affected_components": ["Django 뷰", "REST API 엔드포인트"],
        "root_cause": "CSRF 검증 우회 — 토큰 기반 API 인증 없이 적용 시 취약",
        "code_examples": [
            {
                "lang": "python",
                "framework": "Django",
                "code": (
                    "from django.views.decorators.csrf import csrf_exempt\n\n"
                    "@csrf_exempt\n"
                    "def my_view(request):\n"
                    "    return HttpResponse('OK')"
                ),
            }
        ],
    },
    {
        "concept_name": "AjaxCSRFHeader",
        "domains": ["security"],
        "concept_type": "security_mechanism",
        "cwe_id": "CWE-352",
        "severity": "medium",
        "description_ko": "AJAX 요청 시 X-CSRFToken HTTP 헤더로 토큰 전달 — JS에서 쿠키 읽어 헤더 주입",
        "aliases": ["X-CSRFToken", "AJAX CSRF", "fetch CSRF"],
        "security_mechanism": ["CSRFTokenHeader", "CookieRead"],
        "affected_components": ["JavaScript fetch API", "axios", "XMLHttpRequest"],
        "code_examples": [
            {
                "lang": "javascript",
                "framework": "Django",
                "code": (
                    "function getCookie(name) {\n"
                    "  const value = `; ${document.cookie}`;\n"
                    "  const parts = value.split(`; ${name}=`);\n"
                    "  if (parts.length === 2) return parts.pop().split(';').shift();\n"
                    "}\n\n"
                    "fetch('/api/data/', {\n"
                    "  method: 'POST',\n"
                    "  headers: { 'X-CSRFToken': getCookie('csrftoken') },\n"
                    "  body: JSON.stringify(data)\n"
                    "});"
                ),
            }
        ],
    },
    {
        "concept_name": "SameSiteCookie",
        "domains": ["security"],
        "concept_type": "security_mechanism",
        "cwe_id": "CWE-1275",
        "severity": "medium",
        "description_ko": "SameSite 쿠키 속성 — 크로스 사이트 요청 시 쿠키 전송 제한으로 CSRF 방어",
        "aliases": ["SameSite", "SameSite=Lax", "SameSite=Strict"],
        "security_mechanism": ["BrowserCSRFDefense"],
        "affected_components": ["HTTP 쿠키", "세션 쿠키", "CSRF 토큰 쿠키"],
        "config_properties": [
            {"key": "CSRF_COOKIE_SAMESITE", "value": "'Lax'"},
            {"key": "SESSION_COOKIE_SAMESITE", "value": "'Lax'"},
        ],
        "code_examples": [
            {
                "lang": "python",
                "framework": "Django",
                "code": (
                    "# settings.py\n"
                    "CSRF_COOKIE_SAMESITE = 'Strict'\n"
                    "SESSION_COOKIE_SAMESITE = 'Lax'"
                ),
            }
        ],
    },
]


class MockClient(ILLMClient):
    async def extract_concepts(self, text_chunk: str, doc_id: str, metadata: dict) -> list[ConceptExtractionSchema]:
        import logging
        from app.infrastructure.llm.gemini_client import _build_prompt, DEFAULT_DOMAINS

        logger = logging.getLogger(__name__)
        allowed_domains = metadata.get("allowed_domains")
        _build_prompt(text_chunk, metadata, allowed_domains)  # 프롬프트 구조 검증용 빌드

        chunk_preview = text_chunk[:120].replace("\n", " ").strip()
        domains_used = allowed_domains or DEFAULT_DOMAINS
        logger.info(
            "[PROMPT/mock] framework=%s lang=%s domains=%s chunk_len=%d | %.120s...",
            metadata.get("framework", "Unknown"),
            metadata.get("lang", "EN"),
            domains_used,
            len(text_chunk),
            chunk_preview,
        )
        logger.info("[MOCK] 고정 데이터 반환 — %d개 컨셉", len(_MOCK_CONCEPTS))

        return [ConceptExtractionSchema(**item) for item in _MOCK_CONCEPTS]

    def is_tracing_enabled(self) -> bool:
        return False
