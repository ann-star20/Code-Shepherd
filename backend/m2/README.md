# m2 — 정적 분석·보안 스캔

**담당 범위**: Pylint/Radon/ESLint 정적 분석, Bandit/Semgrep(OWASP Top 10) 보안 스캔.

## 엔드포인트

- `POST /analyze/static`: Pylint(코드 품질) + Radon(순환복잡도) + ESLint(JS/TS)
- `POST /analyze/security`: Bandit(Python 보안) + Semgrep(OWASP Top 10)

입출력은 `shared/contracts.py`의 `M2AnalyzeRequest` / `M2AnalyzeResponse` 계약을 따른다.

## 동작 방식

오케스트레이터(m1)는 unified diff(`pr_diff`)만 전달한다(원본 clone 없음).
`app/analyzer.py`가 diff의 post-image를 임시 파일로 복원한 뒤 도구를 실행하고,
결과를 `IssueItem`(severity/line/file/message/rule_id/suggestion)으로 매핑한다.

## 도구 설치 (선택)

분석 도구는 **선택 의존성**이다. 미설치 환경에서는 해당 도구를 건너뛰고
빈 결과를 반환한다(파이프라인을 막지 않음).

```bash
uv sync --extra analysis      # pylint / radon / bandit / semgrep 설치
```

- Semgrep은 Windows 네이티브에서 실행 불가 → 자동 skip.
- ESLint는 PATH의 `eslint` 실행파일을 사용. 없으면 skip.

## 테스트

```bash
uv run pytest                 # 계약 + analyzer 단위 테스트 (도구 설치 불필요, subprocess Mock)
```
