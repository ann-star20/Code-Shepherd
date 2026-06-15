"""주문·결제 서비스 Django 설정/뷰 — clickjacking 취약 예시.

OWASP A05(보안 설정 미흡) 영역으로, Bandit/Semgrep이 잡지 못하는
"있어야 할 보호가 없는" 설정 결함을 의도적으로 포함한다.
"""

from django.views.decorators.clickjacking import xframe_options_exempt
from django.http import JsonResponse


# ── settings ────────────────────────────────────────────────
# 프레임 차단 미들웨어가 빠져 사이트 전체가 iframe 삽입(clickjacking)에 노출
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
]

# 자사 도메인 내 iframe을 허용 — 민감 서비스는 DENY가 권장됨
X_FRAME_OPTIONS = "SAMEORIGIN"

# 쿠키 교차 사이트 전송 정책이 비어 있어 CSRF·clickjacking 복합 공격 방어가 약함


# ── views ───────────────────────────────────────────────────
@xframe_options_exempt
def payment_confirm(request):
    """결제 확인 뷰 — 프레임 차단 보호를 명시적으로 해제(취약)."""
    return JsonResponse({"status": "confirmed"})
