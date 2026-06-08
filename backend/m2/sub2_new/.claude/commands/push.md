---
description: git add → commit → push → PR 생성 → 코드 리뷰까지 한 번에 처리하는 커맨드
allowed_tools: ["Bash", "Read", "Glob", "Grep"]
---

# /push

변경된 코드를 커밋하고 PR을 생성한 뒤 코드 리뷰까지 한 번에 처리합니다.

사용법:
- `/push` — 변경사항 확인 후 커밋 메시지 제안
- `/push feat: 피드 검색 API 추가` — 커밋 메시지 직접 지정

## 실행 순서

### Step 1: 최신 코드 동기화 (pull)

```bash
git branch --show-current
```

- 현재 브랜치명을 확인한 뒤 사용자에게 보여준다
- 어떤 브랜치에서 pull할지 확인을 받고 진행한다

```bash
git pull origin <확인된 브랜치명>
```

- 충돌(conflict)이 발생하면 사용자에게 알리고 중단한다
- 충돌 없이 성공하면 다음 단계로 진행한다

### Step 2: 현재 상태 파악

```bash
git status
git diff --stat
git log --oneline -5
```

- 변경된 파일 목록과 diff를 확인한다
- 현재 브랜치명을 확인한다
- dev 또는 main 브랜치라면 작업 브랜치 생성 여부를 사용자에게 물어본다

### Step 3: 브랜치 전략 (git-workflow 기준)

브랜치명 규칙:
- `feat/<기능명>` — 새 기능
- `fix/<버그명>` — 버그 수정
- `refactor/<대상>` — 리팩터링
- `docs/<대상>` — 문서

현재 브랜치가 dev 또는 main이면:
```bash
git checkout -b feat/<기능명>
```

### Step 4: 중간 평가 및 보고서 작성

git add 전에 변경 내용을 검토하고 `docs/reports/YYYY-MM-DD-<브랜치명>.md` 에 보고서를 저장한다.

**보고서 필수 항목:**

```markdown
# 중간 보고서 — <날짜> <브랜치명>

## 변경 요약
- 변경된 파일 목록과 각 파일의 변경 목적

## 중간 평가
| 항목 | 상태 | 비고 |
|------|------|------|
| 기능 구현 완성도 | 🟢 완료 / 🟡 부분 / 🔴 미완 | |
| 테스트 작성 여부 | 🟢 / 🟡 / 🔴 | |
| 문서 업데이트 여부 | 🟢 / 🟡 / 🔴 | |
| 보안 이슈 없음 | 🟢 / 🔴 | |

## 잘 된 점
- (이번 작업에서 잘 구현된 부분)

## 개선 필요 사항
- (다음 커밋 또는 Sprint에서 보완할 점)

## 다음 작업
- (이어서 해야 할 Task)
```

보고서 저장 후 사용자에게 내용을 요약 출력하고 계속 진행 여부를 확인한다.

### Step 5: git add

변경 파일을 확인하고 관련 파일만 스테이징한다.
민감한 파일(.env, 시크릿 포함 파일)은 절대 포함하지 않는다.

```bash
git add <관련 파일들>
# git add -A 는 사용하지 않음 — 민감 파일 방지
```

### Step 6: git commit

커밋 메시지 규칙 (Conventional Commits):
- `feat:` 새 기능
- `fix:` 버그 수정
- `test:` 테스트 추가·수정
- `docs:` 문서
- `refactor:` 리팩터링
- `chore:` 빌드·설정

ARGUMENTS에 커밋 메시지가 있으면 그대로 사용한다.
없으면 변경 내용을 분석해서 적절한 커밋 메시지를 제안하고 확인 후 커밋한다.

```bash
git commit -m "<커밋 메시지>"
```

### Step 7: git push

```bash
git push -u origin <현재 브랜치명>
```

### Step 8: PR 생성 (github-ops 기준)

docs/는 backend/sub2/.gitignore에 등록되어 있어 자동으로 merge 제외된다.

```bash
gh pr create \
  --base dev \
  --title "<커밋 메시지 기반 PR 제목>" \
  --body "<변경 내용 요약, 테스트 방법, 체크리스트>"
```

PR body 필수 포함 항목:
- ## Summary: 변경 내용 bullet 3줄 이내
- ## Test plan: 테스트 방법 체크리스트
- ## 관련 Task: 플랜 문서 Task 번호 (있으면)

### Step 9: PR 코드 리뷰

생성된 PR 번호를 확인한 뒤 review 스킬 방식으로 코드를 검토한다.

```bash
gh pr view <PR번호> --json files,additions,deletions
```

변경 파일을 읽고 아래 기준으로 리뷰:
- **CRITICAL** — 보안 취약점, 데이터 손실 위험
- **HIGH** — 버그, 잘못된 로직
- **MEDIUM** — 성능, 가독성
- **LOW** — 스타일, 네이밍

리뷰 결과를 출력하고 CRITICAL/HIGH 이슈가 있으면 수정을 권고한다.

## 완료 메시지

```
✅ Push 완료
브랜치: feat/xxx
커밋:   feat: xxx
PR:     https://github.com/.../pull/N
리뷰:   CRITICAL 0 / HIGH 0 / MEDIUM N / LOW N
```
