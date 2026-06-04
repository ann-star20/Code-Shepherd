<!-- CLAUDE.md -->
## 세션 시작 규칙

모든 세션 시작 시 **첫 번째 액션**으로 아래를 실행한다:

```bash
echo "Phase1-Task1-schema" > ~/.claude/.current_task
```

작업명 형식: `Phase{번호}-Task{번호}-{설명}`
현재 Phase: 1
현재 Task: PRD §8 개발 순서 참고

## Skill routing

When the user's request matches an available skill, invoke it via the Skill tool. When in doubt, invoke the skill.

Key routing rules:
- Product ideas/brainstorming → invoke /office-hours
- Strategy/scope → invoke /plan-ceo-review
- Architecture → invoke /plan-eng-review
- Design system/plan review → invoke /design-consultation or /plan-design-review
- Full review pipeline → invoke /autoplan
- Bugs/errors → invoke /investigate
- QA/testing site behavior → invoke /qa or /qa-only
- Code review/diff check → invoke /review
- Visual polish → invoke /design-review
- Ship/deploy/PR → invoke /ship or /land-and-deploy
- Save progress → invoke /context-save
- Resume context → invoke /context-restore
- Author a backlog-ready spec/issue → invoke /spec
