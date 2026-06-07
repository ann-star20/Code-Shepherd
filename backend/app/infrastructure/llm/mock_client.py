"""MockClient — 4-레이어 지식 그래프 수렴 설계 사양을 100% 만족하는 DEV/mock 모드 클라이언트.

개편 스펙 준수 사항:
  1. security_mechanism 내부에 code_examples 중첩 계층화 (Layer 3 -> Layer 4 귀속 무결성)
  2. config_properties 내부에 "type": "security" 필드 필수 바인딩
  3. affected_components, root_cause 최적화 소문자 스네이크케이스 선행 정규화
"""

from __future__ import annotations

import logging
from app.domain.models import ConceptExtractionSchema
from app.infrastructure.llm.interface import ILLMClient

logger = logging.getLogger(__name__)

# ── 4-레이어 수렴형 표준 준수 Mock 데이터셋 ──────────────────────────────────
_MOCK_CONCEPTS: list[dict] = [
    {
        "concept_name": "CSRFAttack",
        "domains": ["security"],
        "concept_type": "vulnerability_root_cause",
        "cwe_id": "CWE-352",
        "owasp_id": "A01:2025",
        "severity": "high",
        "description_ko": "크로스 사이트 요청 위조 — 인증된 사용자의 브라우저 세션 권한을 신뢰하는 점을 악용하여, 공격자가 의도치 않은 상태 변경 요청을 강제로 전송하게 만드는 취약점.",
        "aliases": ["CSRF", "XSRF", "Sea Surf", "Cross-Site Request Forgery"],
        "root_cause": "missing_request_origin_verification",
        "affected_components": ["form_submission_handler", "state_changing_api", "session_management"],
        "security_mechanism": [
          {
            "mechanism_name": "csrf_token_protection",
            "code_examples": [
              {
                "lang": "html",
                "lang_version": "*",
                "framework": "django",
                "framework_version": ">=4.0",
                "code": "\n<form action='https://bank.com/transfer' method='post'>\n  <input name='amount' value='1000'>\n</form>",
                "description": "사용자 모르게 백그라운드에서 전송되는 CSRF 공격용 가짜 폼 스니펫"
              }
            ]
          }
        ],
        "config_properties": []
    },
    {
        "concept_name": "CsrfViewMiddleware",
        "domains": ["security"],
        "concept_type": "security_mechanism",
        "cwe_id": "CWE-352",
        "owasp_id": "A01:2025",
        "severity": "high",
        "description_ko": "Django의 CSRF 보호 핵심 미들웨어 — 인입되는 모든 상태 변경 목적의 쓰기(POST, PUT, DELETE) 요청에 대해 토큰 무결성 서명 유효성 검증을 수행합니다.",
        "aliases": ["django.middleware.csrf.CsrfViewMiddleware", "CSRF 미들웨어"],
        "root_cause": "unvalidated_http_request_pipeline",
        "affected_components": ["middleware_configuration", "http_request_pipeline"],
        "security_mechanism": [
          {
            "mechanism_name": "csrf_token_validation",
            "code_examples": [
              {
                "lang": "python",
                "lang_version": ">=3.10",
                "framework": "django",
                "framework_version": ">=4.0",
                "code": "MIDDLEWARE = [\n    ...\n    'django.middleware.csrf.CsrfViewMiddleware',\n    ...\n]",
                "description": "Django settings.py 보안 미들웨어 기본 활성화 레이아웃"
              }
            ]
          }
        ],
        "config_properties": [
            {"key": "csrf_cookie_secure", "value": "True", "type": "security"},
            {"key": "csrf_cookie_httponly", "value": "False", "type": "security"},
            {"key": "csrf_cookie_samesite", "value": "Lax", "type": "security"},
            {"key": "csrf_trusted_origins", "value": "['https://example.com']", "type": "security"}
        ]
    },
    {
        "concept_name": "CsrfTokenTag",
        "domains": ["security"],
        "concept_type": "security_mechanism",
        "cwe_id": "CWE-352",
        "severity": "medium",
        "description_ko": "Django 템플릿 엔진 태그 — 내부 서명 처리된 유효한 난수 토큰값을 HTML 내부에 hidden 타입의 input 필드로 자동 전송 레이어화 처리를 보장합니다.",
        "aliases": ["csrf_token", "{% csrf_token %}", "csrf_token template tag"],
        "root_cause": "missing_hidden_token_in_form_payload",
        "affected_components": ["django_template_engine", "html_form_payload"],
        "security_mechanism": [
          {
            "mechanism_name": "csrf_token_embed",
            "code_examples": [
              {
                "lang": "html",
                "lang_version": "*",
                "framework": "django",
                "framework_version": ">=4.0",
                "code": "<form method='post'>\n  {% csrf_token %}\n  {{ form.as_p }}\n  <button type='submit'>Submit</button>\n</form>",
                "description": "Django 내부 템플릿 폼 제출 시 유효 토큰 바인딩 표준 선언식"
              }
            ]
          }
        ],
        "config_properties": []
    },
    {
        "concept_name": "CsrfExempt",
        "domains": ["security"],
        "concept_type": "vulnerability_root_cause",
        "cwe_id": "CWE-352",
        "severity": "high",
        "description_ko": "특정 뷰 엔드포인트의 CSRF 유효성 검증 레이어를 명시적으로 비활성화하는 데코레이터. API 토큰이나 세션 보호 가드가 부재할 시 심각한 우회 취약점으로 직결됩니다.",
        "aliases": ["@csrf_exempt", "csrf_exempt decorator"],
        "root_cause": "bypass_csrf_verification_without_alternative_auth",
        "affected_components": ["django_view_layer", "rest_api_endpoint"],
        "security_mechanism": [
          {
            "mechanism_name": "alternative_token_auth",
            "code_examples": [
              {
                "lang": "python",
                "lang_version": ">=3.10",
                "framework": "django",
                "framework_version": ">=4.0",
                "code": "from django.views.decorators.csrf import csrf_exempt\n\n@csrf_exempt\ndef my_view(request):\n    # 대체 인증 수단(예: JWT/Bearer Header)이 반드시 사전에 선행되어야 함\n    return HttpResponse('OK')",
                "description": "데코레이터를 통한 미들웨어 검증 강제 우회 설정 명세"
              }
            ]
          }
        ],
        "config_properties": []
    },
    {
        "concept_name": "AjaxCSRFHeader",
        "domains": ["security"],
        "concept_type": "security_mechanism",
        "cwe_id": "CWE-352",
        "severity": "medium",
        "description_ko": "비동기 AJAX(Fetch/Axios) 요청 발생 시, 브라우저 클라이언트 사이드 스크립트 단에서 쿠키에 내장된 토큰값을 읽어 X-CSRFToken HTTP 헤더에 수동으로 탑재하여 가동하는 보안 기전.",
        "aliases": ["X-CSRFToken", "AJAX CSRF", "fetch CSRF"],
        "root_cause": "stateless_ajax_request_missing_cookie_context",
        "affected_components": ["javascript_fetch_api", "axios_client_layer", "xml_http_request"],
        "security_mechanism": [
          {
            "mechanism_name": "csrf_token_header_injection",
            "code_examples": [
              {
                "lang": "javascript",
                "lang_version": "ES6+",
                "framework": "vanilla_js",
                "framework_version": "*",
                "code": "function getCookie(name) {\n  const value = `; ${document.cookie}`;\n  const parts = value.split(`; ${name}=`);\n  if (parts.length === 2) return parts.pop().split(';').shift();\n}\n\nfetch('/api/data/', {\n  method: 'POST',\n  headers: { 'X-CSRFToken': getCookie('csrftoken') },\n  body: JSON.stringify(data)\n});",
                "description": "클라이언트 자바스크립트 단의 쿠키 파싱 후 HTTP 커스텀 헤더 주입 로직"
              }
            ]
          }
        ],
        "config_properties": []
    },
    {
        "concept_name": "SameSiteCookie",
        "domains": ["security"],
        "concept_type": "security_mechanism",
        "cwe_id": "CWE-1275",
        "severity": "medium",
        "description_ko": "브라우저 단의 기본 HTTP 쿠키 전송 가드레일인 SameSite 속성을 활용하여, 제3자 사이트에서 발생하는 모든 크로스 사이트 콘텍스트 내 세션 쿠키 탈취 요청을 엔진 레벨에서 원천 필터링합니다.",
        "aliases": ["SameSite", "SameSite=Lax", "SameSite=Strict"],
        "root_cause": "lax_cookie_cross_origin_transmission",
        "affected_components": ["http_cookie_engine", "session_cookie_layer", "csrf_cookie_layer"],
        "security_mechanism": [
          {
            "mechanism_name": "browser_csrf_defense",
            "code_examples": [
              {
                "lang": "python",
                "lang_version": ">=3.10",
                "framework": "django",
                "framework_version": ">=4.0",
                "code": "# settings.py\nCSRF_COOKIE_SAMESITE = 'Strict'\nSESSION_COOKIE_SAMESITE = 'Lax'",
                "description": "쿠키 배출 제어 및 SameSite 플래그 브라우저 강제 주입 설정"
              }
            ]
          }
        ],
        "config_properties": [
            {"key": "csrf_cookie_samesite", "value": "Strict", "type": "security"},
            {"key": "session_cookie_samesite", "value": "Lax", "type": "security"}
          ]
    }
]


class MockClient(ILLMClient):
    """
    4-레이어 결합 스펙을 완벽하게 만족하는 런타임 가짜 데이터 공급기.
    usecases 단은 의존성 역전(DIP)에 의해 이 객체의 실체를 모른 채 추상 규격으로만 소통합니다.
    """

    async def extract_concepts(
        self, 
        text_chunk: str, 
        doc_id: str, 
        metadata: dict
    ) -> list[ConceptExtractionSchema]:
        
        chunk_preview = text_chunk[:100].replace("\n", " ").strip()
        logger.info(
            "[MOCK_ENGINE] %d 차원 청크 유입 포착 | 미리보기: '%.100s...'", 
            len(text_chunk), 
            chunk_preview
        )
        logger.info("  ➔ Gemini API 호출 우회 수립 (APP_MODE=mock). %d건 가상 컨셉 인스턴스 반환 완료.", len(_MOCK_CONCEPTS))

        # 4대 마스터 규격 필터링 레이어를 타서 완전무결한 Pydantic 인스턴스 배열로 반환
        return [ConceptExtractionSchema(**item) for item in _MOCK_CONCEPTS]

    def is_tracing_enabled(self) -> bool:
        return False