<!-- ---
source_of_truth:
  - docs/PRD-domain.md (§3.1.4 doc_id 마스터 키 설계, §7 데이터 모델 개요)
---
## F1: 타입 정의 및 유틸 함수

### SDD

**파일**: `src/types/concept.ts`
```typescript
export type ConceptDomain = "security" | "performance" | "both"
export type NodeStatus = "DRAFT" | "APPROVED" | "COMMITTED" | "REJECTED"
export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW"

export interface ConceptNode {
  id: string
  name: string
  domain: ConceptDomain
  status: NodeStatus
  cwe_id?: string
  severity?: Severity
  description_ko?: string
  aliases: string[]
  tags: string[]          // Tag Node 방식: ["security", "performance"]
}
```

**파일**: `src/types/pipeline.ts`
```typescript
export type AgentStep = "Input" | "Crawler" | "Extractor" | "Writer" | "Resolver"
export type StepStatus = "PENDING" | "RUNNING" | "DONE" | "FAILED"

export interface PipelineStep {
  agent: AgentStep
  status: StepStatus
}

export interface StagingRecord {
  id: string
  session_id: string
  concept_json: ConceptNode
  state: NodeStatus
}
```

**파일**: `src/types/graph.ts`
```typescript
export interface GraphNode {
  id: string
  name: string
  domain: ConceptDomain
  status: NodeStatus      // DRAFT면 가상 노드
  x?: number
  y?: number
}

export interface GraphEdge {
  source: string
  target: string
  type: string            // TAGGED_WITH | SAME_AS | RELATED_TO 등
}

export interface VirtualNodeStyle {
  opacity: number         // DRAFT: 0.65 / COMMITTED: 1.0
  strokeDasharray: string // DRAFT: "5,3" / COMMITTED: "none"
  color: string
}
```

**파일**: `src/utils/nodeStyler.ts`
```typescript
// 노드 상태·도메인별 시각 스타일 결정 — 순수 함수
export function getNodeStyle(status: NodeStatus, domain: ConceptDomain): VirtualNodeStyle
export function getDomainColor(domain: ConceptDomain): string
  // security → "#1D9E75" / performance → "#BA7517" / both → "#534AB7"
```

**파일**: `src/utils/docId.ts`
```typescript
// 클라이언트 사이드 doc_id 표시용 (파싱만, 생성은 백엔드)
export function parseDocId(docId: string): { prefix: string; urlPart: string; hash: string }
```

### TDD (AAA)

파일: `src/utils/__tests__/nodeStyler.test.ts`

| ID | Arrange | Act | Assert |
|----|---------|-----|--------|
| T_F1_draft_style | `status="DRAFT"`, `domain="security"` | `getNodeStyle(...)` | `opacity === 0.65`, `strokeDasharray === "5,3"` |
| T_F1_committed_style | `status="COMMITTED"`, `domain="security"` | `getNodeStyle(...)` | `opacity === 1`, `strokeDasharray === "none"` |
| T_F1_rejected_style | `status="REJECTED"`, `domain="performance"` | `getNodeStyle(...)` | `color` includes red (`#E24B4A` 계열) |
| T_F1_domain_color_security | `domain="security"` | `getDomainColor(...)` | `"#1D9E75"` |
| T_F1_domain_color_both | `domain="both"` | `getDomainColor(...)` | `"#534AB7"` |
| T_F1_parse_doc_id | `"EXT_https---docs-django_a3f9c21b"` | `parseDocId(...)` | `prefix="EXT"`, `hash="a3f9c21b"` |

### COMMIT
```
feat(frontend): add TypeScript domain types concept pipeline graph
test(frontend): add nodeStyler docId util unit tests with AAA pattern
feat(frontend): implement nodeStyler getDomainColor getNodeStyle pure functions
``` -->
