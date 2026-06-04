# m4 — 커리큘럼·판정 스텁

**담당 범위**: M2/M3 결과 취합 → 3-Way 판정(LGTM/재작업/에스컬레이션), 개인화 피드백, 학습 커리큘럼, 성장 추적.

현재 **스텁** — 계약 엔드포인트만 구현됨.

## 확장 지점

- `POST /evaluate`: M2+M3 결과 기반 판정 (Critical≥1→escalate, Major≥3→rework, 나머지→lgtm)
- `POST /curriculum`: 기술스택 기반 주차별 학습 로드맵 생성
- 3-Way 판정 후 GitHub PR 코멘트 자동 작성
- Slack 에스컬레이션 알림
