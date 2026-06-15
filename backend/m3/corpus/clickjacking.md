# [CONV-SEC-010] 클릭재킹 방지 헤더 미설정 금지
- severity: Major
- 배경(사고 이력): 2024-09 보안감사 — 결제 뷰에 XFrameOptionsMiddleware가 제거된 상태로 배포되어, 공격자가 결제 화면을 투명 iframe으로 삽입해 사용자 클릭을 가로채는 클릭재킹 공격 경로가 노출됐다.

## §1 규칙
Django 애플리케이션은 반드시 `django.middleware.clickjacking.XFrameOptionsMiddleware`를 MIDDLEWARE에 등록해야 한다.
`settings.py`에 `X_FRAME_OPTIONS = 'DENY'` 또는 `'SAMEORIGIN'`을 명시한다.
결제·주문·인증 관련 뷰에는 `@xframe_options_exempt` 데코레이터를 절대 적용하지 않는다.

## §2 올바른 예시
```python
# settings.py
MIDDLEWARE = [
    ...
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    ...
]
X_FRAME_OPTIONS = 'DENY'
```

## §3 잘못된 예시
```python
# settings.py — XFrameOptionsMiddleware 누락 (2024-09 사고 패턴)
MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    # XFrameOptionsMiddleware 가 없음
]

# views.py — 결제 뷰에 exempt 적용
from django.views.decorators.clickjacking import xframe_options_exempt

@xframe_options_exempt
def payment_view(request):   # 클릭재킹 공격에 무방비
    ...
```

## §4 예외 조항
예외 없음. 마이그레이션·관리자 뷰·내부 도구 페이지도 동일하게 적용한다.
`SAMEORIGIN`이 필요한 내부 iframe 사용 사례는 보안팀 검토 후 `settings.py`에 서비스 단위로만 허용한다.
