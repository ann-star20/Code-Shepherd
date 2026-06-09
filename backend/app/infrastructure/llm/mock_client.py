"""MockClient — 4-레이어 지식 그래프 수렴 설계 사양을 100% 만족하는 DEV/mock 모드 클라이언트.

개편 스펙 준수 사항:
  1. mechanism 내부에 code_examples 중첩 계층화 (Layer 3 -> Layer 4 귀속 무결성)
  2. config_properties 내부에 "type": "security" 필드 필수 바인딩
  3. affected_components, root_cause 최적화 소문자 스네이크케이스 선행 정규화
"""

from __future__ import annotations

import json
import logging
import pathlib
from app.domain.models import ConceptExtractionSchema
from app.infrastructure.llm.interface import ILLMClient

# backend/llm_response.json → Docker 마운트 시 /app/llm_response.json
_JSON_PATH = pathlib.Path(__file__).parents[3] / "llm_response.json"

logger = logging.getLogger(__name__)

# ── 하이브리드 리졸버 TDD 3-시나리오 창(槍) Mock 데이터셋 ─────────────────────
#
# 시나리오 A (MERGE):  CrossSiteRequestForgery → CSRF 시드에 흡수되어야 함
#   - aliases에 "Cross-Site Request Forgery" 정확 일치 → JW = 1.0
#   - 동일 키워드 풀(csrf, cross, site, request, forgery) → CosineName > 0.85
#   - 유사 한국어 설명 → CosineDesc 높음 → 총점 > 0.88 (MERGE 분기)
#
# 시나리오 B (RELATED_TO):  SSRF — "Request Forgery" 문맥 공유, 다른 기전
#   - "Server-Side Request Forgery" 철자 유사 → JW 보통
#   - 프로덕션 환경(실제 임베딩 모델)에서는 0.72~0.88 범위로 RELATED_TO 분기
#   - 개발/테스트: 점수 제어는 test_hybrid_resolver.py의 FakePgPool 픽스처로 검증
#
# 시나리오 C (NEW):  Clickjacking — 완전히 독립된 도메인, 기존 노드와 무관
#   - "UI Redressing" / "click" / "jacking" → CSRF/XSS와 공유 토큰 없음 → 총점 < 0.72 (NEW)
_MOCK_CONCEPTS: list[dict] = [
    # ── 시나리오 A: MERGE 대상 ─────────────────────────────────────────────────
    # 이름은 파스칼케이스 풀네임이지만, aliases에 "Cross-Site Request Forgery" 정확 일치가 있어
    # JaroWinkler = 1.0, CosineName > 0.85 → 총점 > 0.88 → 기존 CSRF 마스터 노드에 MERGE.
    # 검증 포인트: CSRF 시드 노드의 aliases에 "CSRF Attack"(신규 동의어)이 추가되어야 함.
    {
        "concept_name": "CrossSiteRequestForgery",
        "concept_type": "vulnerability_root_cause",
        "cwe_id": "CWE-352",
        "owasp_id": "A01:2025",
        "severity": "high",
        "domains": ["security"],
        "description_ko": "크로스 사이트 요청 위조 — 인증된 사용자의 브라우저 세션 권한을 신뢰하는 점을 악용하여, 공격자가 의도치 않은 상태 변경 요청을 강제로 전송하게 만드는 취약점.",
        "aliases": ["CSRF", "Cross-Site Request Forgery", "XSRF", "CSRF Attack"],
        "root_cause": "missing_request_origin_verification",
        "affected_components": ["form_submission_handler", "state_changing_api"],
        "mechanism": [
            {
                "mechanism_name": "double_submit_cookie",
                "code_examples": [
                    {
                        "lang": "python",
                        "lang_version": ">=3.10",
                        "framework": "fastapi",
                        "framework_version": ">=0.100",
                        "code": "# Double Submit Cookie 패턴\nfrom fastapi import Cookie, Header, HTTPException\n\ndef verify_csrf(csrf_token: str = Cookie(...), x_csrf_token: str = Header(...)):\n    if csrf_token != x_csrf_token:\n        raise HTTPException(status_code=403, detail='CSRF 토큰 불일치')",
                        "description": "쿠키와 커스텀 헤더의 동일한 토큰값 검증으로 CSRF 방어"
                    }
                ]
            },
            {
                "mechanism_name": "requires_csrf_token_decorator",
                "code_examples": [
                    {
                        "lang": "python",
                        "lang_version": "2.7",
                        "framework": "Django",
                        "framework_version": "1.11",
                        "code": "from django.shortcuts import render\nfrom django.views.decorators.csrf import requires_csrf_token\n\n@requires_csrf_token\ndef my_view(request):\n    # Django 1.11 / Python 2.7 환경\n    context = {'data': 'secure_content'}\n    return render(request, 'template.html', context)",
                        "description": "Django 1.11에서 데코레이터를 사용하여 CSRF 토큰 처리를 보장하는 방식"
                    },
                    {
                        "lang": "javascript",
                        "lang_version": "ES6",
                        "framework": "Express",
                        "framework_version": "4.17",
                        "code": "const express = require('express');\nconst csrf = require('csurf');\nconst cookieParser = require('cookie-parser');\n\nconst app = express();\nconst csrfProtection = csrf({ cookie: true });\n\napp.use(cookieParser());\n\napp.get('/protected', csrfProtection, (req, res) => {\n    // CSRF 토큰을 템플릿에 주입\n    res.render('template', { csrfToken: req.csrfToken() });\n});",
                        "description": "Express에서 csurf 미들웨어를 사용하여 토큰 기반의 CSRF 보호를 적용하는 방식"
                    }
                ]
            }

        ],
        
        "config_properties": []
    },

    # ── 시나리오 B: RELATED_TO 대상 ──────────────────────────────────────────────
    # "Server-Side Request Forgery" — CSRF와 "Request Forgery" 문맥을 공유하나
    # 공격 벡터/방어 기전이 다름. 실제 임베딩 모델 사용 시 총점 0.72~0.88 범위.
    # 테스트에서는 FakePgPool로 벡터를 제어해 정확한 RELATED_TO 분기를 검증한다.
    {
        "concept_name": "SSRF",
        "concept_type": "vulnerability_root_cause",
        "cwe_id": "CWE-918",
        "owasp_id": "A10:2025",
        "severity": "high",
        "domains": ["security"],
        "description_ko": "서버 사이드 요청 위조(SSRF)는 서버가 공격자가 지정한 내부 또는 외부 리소스로 HTTP 요청을 보내도록 유도하는 취약점. 내부망 스캔, 클라우드 메타데이터 탈취에 악용된다.",
        "aliases": ["Server-Side Request Forgery", "ServerSideRequestForgery", "SSRFAttack"],
        "root_cause": "unvalidated_user_supplied_url_in_server_request",
        "affected_components": ["http_client_layer", "webhook_handler", "url_fetch_service"],
        "mechanism": [
            {
                "mechanism_name": "allowlist_url_validation",
                "code_examples": [
                    {
                        "lang": "python",
                        "lang_version": ">=3.10",
                        "framework": "fastapi",
                        "framework_version": ">=0.100",
                        "code": "from urllib.parse import urlparse\n\nALLOWED_HOSTS = {'api.example.com', 'cdn.example.com'}\n\ndef safe_fetch(url: str) -> bytes:\n    host = urlparse(url).hostname\n    if host not in ALLOWED_HOSTS:\n        raise ValueError(f'Blocked: {host}')\n    import httpx\n    return httpx.get(url, timeout=5).content",
                        "description": "허용 도메인 목록(allowlist) 검증으로 임의 URL 요청 차단"
                    }
                ]
            }
        ],
        "config_properties": []
    },

    # ── 시나리오 C: NEW 신규 마스터 노드 ─────────────────────────────────────────
    # "Clickjacking / UI Redressing" — click, jacking, ui, redressing 토큰은
    # CSRF/XSS/SQLi 등 기존 시드와 완전히 다름. 총점 < 0.72 → 독립 신규 노드 생성.
    {
        "concept_name": "Clickjacking",
        "concept_type": "vulnerability_root_cause",
        "cwe_id": "CWE-451",
        "owasp_id": "A05:2025",
        "severity": "medium",
        "domains": ["security"],
        "description_ko": "투명한 iframe을 웹 페이지 위에 덮어씌워 사용자가 의도치 않은 버튼이나 링크를 클릭하도록 속이는 UI 교정 공격. 계정 설정 변경, 소셜 미디어 공유 등 원하지 않는 행위를 유발한다.",
        "aliases": ["UI Redressing", "UIRedressing", "ClickjackingAttack", "클릭재킹"],
        "root_cause": "transparent_iframe_overlay_without_frame_protection",
        "affected_components": ["browser_rendering_layer", "iframe_sandbox_policy"],
        "mechanism": [
            {
                "mechanism_name": "x_frame_options_header",
                "code_examples": [
                    {
                        "lang": "python",
                        "lang_version": ">=3.10",
                        "framework": "django",
                        "framework_version": ">=4.0",
                        "code": "# settings.py\nX_FRAME_OPTIONS = 'DENY'  # 또는 'SAMEORIGIN'",
                        "description": "X-Frame-Options 헤더로 iframe 내 페이지 로드를 전면 차단"
                    }
                ]
            },
            {
                "mechanism_name": "csp_frame_ancestors",
                "code_examples": [
                    {
                        "lang": "python",
                        "lang_version": ">=3.10",
                        "framework": "fastapi",
                        "framework_version": ">=0.100",
                        "code": "from fastapi.responses import Response\n\n@app.middleware('http')\nasync def add_csp(request, call_next):\n    response = await call_next(request)\n    response.headers['Content-Security-Policy'] = \"frame-ancestors 'none'\"\n    return response",
                        "description": "CSP frame-ancestors 지시어로 iframe 삽입 출처를 정밀 제어"
                    }
                ]
            }
        ],
        "config_properties": [
            {"key": "x_frame_options", "value": "DENY", "type": "security"}
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

        if _JSON_PATH.exists():
            raw = json.loads(_JSON_PATH.read_text(encoding="utf-8"))
            logger.info("  ➔ llm_response.json 로드 (APP_MODE=mock). %d건 컨셉 반환.", len(raw))
            return [ConceptExtractionSchema(**item) for item in raw]

        logger.info("  ➔ Gemini API 호출 우회 (APP_MODE=mock). %d건 내장 mock 반환.", len(_MOCK_CONCEPTS))
        return [ConceptExtractionSchema(**item) for item in _MOCK_CONCEPTS]

    def is_tracing_enabled(self) -> bool:
        return False