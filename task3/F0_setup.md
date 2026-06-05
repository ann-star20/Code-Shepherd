---
source_of_truth:
  - task3.md
  - docs/PRD-indfa.md (§5.1 기술 스택, §5.4 환경별 전환 방법)
---
## F0: 프로젝트 셋업

### SDD

```
frontend/
├── index.html
├── vite.config.ts        # path alias (@/ → src/), proxy /api → backend:8000
├── tsconfig.json
├── tailwind.config.ts
├── package.json
└── src/
    ├── assets/styles/globals.css   # @tailwind base/components/utilities
    ├── main.tsx
    └── App.tsx
```

**vite.config.ts 핵심 설정**:
```typescript
resolve: { alias: { "@": path.resolve(__dirname, "src") } },
server: { proxy: { "/api": "http://localhost:8000" } },
test: { environment: "jsdom", globals: true, setupFiles: ["./src/test/setup.ts"] }
```

### TDD (AAA)

파일: `src/test/setup.test.ts`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_F0_alias | `import { something } from "@/utils/nodeStyler"` | 빌드 또는 import | 에러 없이 import 성공 |
| T_F0_tailwind | globals.css에 `@tailwind` 3줄 존재 | CSS 파싱 | `@tailwind base` 포함 확인 |

### COMMIT
```
chore(frontend): init vite react ts tailwind with path alias and api proxy
chore(frontend): add vitest rtl test environment setup
```

---
