---
description: 작업 중 변경사항을 pull → add → commit으로 중간 저장하는 커맨드
allowed_tools: ["Bash", "Read", "Glob", "Grep"]
---

# /save

작업 중 변경사항을 빠르게 중간 저장합니다. push나 PR은 하지 않습니다.

사용법:
- `/save` — 변경사항 확인 후 커밋 메시지 제안
- `/save feat: 피드 서비스 로직 추가 중` — 커밋 메시지 직접 지정

## 실행 순서

### Step 1: 최신 코드 동기화 (pull)

```bash
git branch --show-current
```

- 현재 브랜치명을 확인한 뒤 사용자에게 보여준다
- pull은 항상 `dev` 브랜치에서 받는다

```bash
git pull origin dev
```

- 충돌(conflict)이 발생하면 사용자에게 알리고 중단한다
- 충돌 없이 성공하면 다음 단계로 진행한다

### Step 2: 현재 상태 파악

```bash
git status
git diff --stat
```

- 변경된 파일 목록을 확인한다
- 민감한 파일(.env, 시크릿 포함 파일)이 있으면 사용자에게 알리고 제외한다

### Step 3: git add

관련 파일만 스테이징한다.

```bash
git add <관련 파일들>
# git add -A 는 사용하지 않음 — 민감 파일 방지
```

### Step 4: git commit

ARGUMENTS에 커밋 메시지가 있으면 그대로 사용한다.
없으면 변경 내용을 분석해서 적절한 커밋 메시지를 제안하고 확인 후 커밋한다.

커밋 메시지 규칙 (Conventional Commits):
- `feat:` 새 기능
- `fix:` 버그 수정
- `test:` 테스트 추가·수정
- `docs:` 문서
- `refactor:` 리팩터링
- `chore:` 빌드·설정
- `wip:` 작업 중 (Work In Progress)

```bash
git commit -m "<커밋 메시지>"
```

## 완료 메시지

```
💾 중간 저장 완료
브랜치: <브랜치명>
커밋:   <커밋 메시지>
(push는 /push 커맨드로 별도 실행)
```
