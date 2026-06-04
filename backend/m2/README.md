# m2 — 정적 분석·보안 스캔 스텁

**담당 범위**: ESLint/Pylint 정적 분석, OWASP 보안 스캔.

현재 **스텁** — 계약 엔드포인트만 구현됨.

## 확장 지점

- `POST /analyze/static`: ESLint/Pylint 실행, 순환복잡도 측정, 코드 스멜 감지
- `POST /analyze/security`: SQL Injection, XSS/CSRF, CVE 스캔, OWASP Top 10
- 출력 형식은 `shared/contracts.py`의 `M2AnalyzeResponse` 계약 준수
