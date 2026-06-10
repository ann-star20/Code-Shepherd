# Pull from dev

`dev` 브랜치에서 현재 브랜치로 최신 변경사항을 가져옵니다.

## 실행 순서

1. **현재 브랜치 확인** — `main`이면 경고 후 진행 여부를 사용자에게 물어보세요.
   ```bash
   git branch --show-current
   ```

2. **로컬 미커밋 변경사항 확인** — 변경사항이 있으면 stash를 권장하고 진행 여부를 물어보세요.
   ```bash
   git status
   git diff
   ```

3. **dev 브랜치 최신화**
   ```bash
   git fetch origin dev
   ```

4. **충돌 가능성 미리 확인** (머지 전)
   ```bash
   git diff HEAD origin/dev
   git merge-tree HEAD HEAD origin/dev
   ```

5. 충돌이 예상되면 충돌 파일 목록을 보여주고 진행 여부를 사용자에게 물어보세요. 충돌이 없으면 바로 머지합니다.
   ```bash
   git merge origin/dev
   ```

6. **머지 후 충돌 발생 시** 충돌 파일 목록과 해결 방법을 안내하세요.
   ```bash
   git status
   ```

7. **머지 성공 시 변경 요약** — 어떤 파일이 추가/수정/삭제됐는지 출력하세요.
   ```bash
   git diff --stat HEAD@{1} HEAD
   ```
