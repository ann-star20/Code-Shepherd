# ui-ux-spec.md — 지식그래프 파이프라인 UI/UX 신규 구현 지침

> 출처: 현재 구현 코드 (`frontend/src/`) 역추출. 새 프로젝트에서 **처음부터 구현**할 때 이 파일 하나로 완결.
> 스타일: **Tailwind CSS** 전용 (CSS-in-JS 없음). 컴포넌트 구조 → 아토믹 디자인 (atoms → molecules → organisms).

---

## 1. 디자인 시스템 & 컬러 토큰

### 1.1 도메인 색상 (그래프 노드 & 배지)

```typescript
// utils/nodeStyler.ts 또는 constants/colors.ts
export const DOMAIN_COLOR = {
  security:    "#1D9E75",  // teal-600 계열
  performance: "#BA7517",  // amber-700 계열
  both:        "#534AB7",  // purple-600 계열
  rejected:    "#E24B4A",  // red-500
};

// Tailwind 배지용 (Badge.tsx)
export const DOMAIN_BADGE_CLASS = {
  security:    "bg-teal-100   text-teal-800",
  performance: "bg-orange-100 text-orange-800",
  both:        "bg-purple-100 text-purple-800",
};
```

### 1.2 상태(Status) 색상

```
PENDING  → bg-gray-300               (회색 점)
RUNNING  → bg-blue-500 animate-pulse  (파란 점, 맥박 애니메이션)
DONE     → bg-green-500              (초록 점 + ✓)
FAILED   → bg-red-500                (빨간 점 + ✕)

토스트
success  → bg-emerald-50 border-emerald-200 text-emerald-800
error    → bg-rose-50    border-rose-200    text-rose-800
warning  → bg-amber-50   border-amber-200   text-amber-800
info     → bg-white      border-stone-200   text-stone-800
```

### 1.3 심각도(Severity) 색상

```typescript
export const SEVERITY_CLASS = {
  critical: "text-red-600    font-semibold",
  high:     "text-orange-500 font-semibold",
  medium:   "text-yellow-500",
  low:      "text-green-600",
};
```

### 1.4 기본 팔레트

- 텍스트: `text-gray-900 / 600 / 400`
- 배경: `bg-white / bg-gray-50 / bg-gray-100`
- 보더: `border-gray-200 / border-gray-300`
- 카드: `rounded-lg border bg-white shadow-sm`
- 모달: `rounded-2xl shadow-2xl bg-white`

---

## 2. Atoms (재사용 기본 단위)

### 2.1 StatusDot — 파이프라인 단계 상태 점

```tsx
// atoms/StatusDot.tsx
type StepStatus = "PENDING" | "RUNNING" | "DONE" | "FAILED";

const CONFIG: Record<StepStatus, { cls: string; icon: string }> = {
  PENDING: { cls: "bg-gray-300",               icon: "·" },
  RUNNING: { cls: "bg-blue-500 animate-pulse",  icon: "·" },
  DONE:    { cls: "bg-green-500",               icon: "✓" },
  FAILED:  { cls: "bg-red-500",                 icon: "✕" },
};

export function StatusDot({ status, label }: { status: StepStatus; label?: string }) {
  const { cls, icon } = CONFIG[status];
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block h-2.5 w-2.5 rounded-full ${cls}`} />
      <span className="text-sm">{label ?? icon}</span>
    </span>
  );
}
```

### 2.2 Badge — 도메인/infer_action 배지

```tsx
// atoms/Badge.tsx
type Domain      = "security" | "performance" | "both";
type InferAction = "NEW" | "MERGE" | "RELATED_TO";

// 도메인 배지
export function DomainBadge({ domain, size = "sm" }: { domain: Domain; size?: "sm" | "md" }) {
  const colorCls = DOMAIN_BADGE_CLASS[domain];
  const sizeCls  = size === "sm" ? "px-1.5 py-0.5 text-xs" : "px-2.5 py-1 text-sm";
  return (
    <span className={`inline-flex items-center rounded-full font-medium ${colorCls} ${sizeCls}`}>
      {domain}
    </span>
  );
}

// infer_action 배지 (NEW / MERGE / RELATED_TO)
const ACTION_CLASS: Record<InferAction, string> = {
  NEW:        "bg-sky-100    text-sky-800",
  MERGE:      "bg-violet-100 text-violet-800",
  RELATED_TO: "bg-amber-100  text-amber-800",
};

export function ActionBadge({ action, confidence, target }:
  { action: InferAction; confidence?: number; target?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5
                      text-xs font-medium ${ACTION_CLASS[action]}`}>
      {action === "NEW"        && `NEW (${(confidence! * 100).toFixed(1)}%)`}
      {action === "MERGE"      && `MERGE → ${target}`}
      {action === "RELATED_TO" && `RELATED_TO ${target}`}
    </span>
  );
}
```

### 2.3 Button

```tsx
// atoms/Button.tsx
const VARIANT = {
  primary: "bg-blue-600   text-white hover:bg-blue-700",
  danger:  "bg-red-600    text-white hover:bg-red-700",
  ghost:   "bg-transparent text-gray-700 hover:bg-gray-100",
  outline: "border border-stone-300 text-stone-700 hover:bg-stone-100",
};

export function Button({ variant = "primary", disabled, children, onClick, type = "button" }) {
  return (
    <button
      type={type} onClick={onClick} disabled={disabled}
      className={`rounded-lg px-3.5 py-1.5 text-sm font-semibold transition
        ${VARIANT[variant]} disabled:opacity-40 disabled:cursor-not-allowed`}
    >
      {children}
    </button>
  );
}
```

---

## 3. Molecules

### 3.1 PipelineStepIndicator — 5단계 진행 표시

```tsx
// molecules/PipelineStepIndicator.tsx
const STEPS = [
  { agent: "Input",     desc: "링크 유효성 및 ETag 캐싱 분석"        },
  { agent: "Crawler",   desc: "DOM 파싱 및 텍스트 블록 정제"          },
  { agent: "Extractor", desc: "Gemini 구조화 의미 스키마 추출"        },
  { agent: "Writer",    desc: "PostgreSQL / Neo4j 스테이징 적재"      },
  { agent: "Resolver",  desc: "하이브리드 유사도 판정 및 동의어 수렴"  },
];

export function PipelineStepIndicator({ statuses }: { statuses: Record<string, StepStatus> }) {
  return (
    <ol className="flex flex-col gap-2">
      {STEPS.map(({ agent, desc }) => {
        const status    = statuses[agent] ?? "PENDING";
        const isRunning = status === "RUNNING";
        return (
          <li key={agent}
              className={`flex items-start gap-2 rounded px-2 py-1.5 transition
                ${isRunning ? "bg-blue-50 font-bold text-blue-700" : "text-gray-600"}`}>
            <StatusDot status={status} />
            <div>
              <p className="text-sm font-medium">{agent}</p>
              <p className="text-xs text-gray-400">{desc}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
```

### 3.2 DuplicateDocumentModal — 중복 문서 감지 팝업

**트리거**: `POST /api/documents/check-duplicate` → `is_duplicate: true`

```tsx
// molecules/DuplicateDocumentModal.tsx
export function DuplicateDocumentModal({ url, onClose }: { url: string; onClose: () => void }) {
  return (
    <div role="dialog" aria-label="중복 문서 안내"
         className="fixed inset-0 z-50 flex items-center justify-center">
      {/* 딤 오버레이 */}
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />

      <div className="relative w-[440px] max-w-[90vw] bg-white rounded-2xl shadow-2xl p-6 flex flex-col gap-4">
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center
                           rounded-full bg-amber-100 text-amber-600 text-lg">
            ⚠
          </span>
          <div>
            <h3 className="font-serif text-lg font-bold text-stone-900">중복 문서 안내</h3>
            <p className="text-sm text-stone-600 mt-1 break-all">
              <span className="font-mono text-stone-800">{url}</span>는
              이미 지식화된 문서입니다.
            </p>
          </div>
        </div>
        <div className="flex justify-end">
          <Button variant="primary" onClick={onClose}>확인</Button>
        </div>
      </div>
    </div>
  );
}
```

### 3.3 DiffSummaryCard — 스테이징 집계 카드

```tsx
// molecules/DiffSummaryCard.tsx
export function DiffSummaryCard({ newCount, updateCount, mergeCount }:
  { newCount: number; updateCount: number; mergeCount: number }) {
  return (
    <div className="flex gap-4 rounded-lg border bg-white px-4 py-3 text-sm shadow-sm">
      <span>신규 <strong className="text-sky-700">{newCount}</strong>개</span>
      <span className="text-gray-300">·</span>
      <span>업데이트 <strong className="text-violet-700">{updateCount}</strong>개</span>
      <span className="text-gray-300">·</span>
      <span>병합 <strong className="text-amber-700">{mergeCount}</strong>개</span>
    </div>
  );
}
```

### 3.4 MetadataLearnModal — HITL 메타데이터 보정 폼

**트리거**: Pre-scan `infer_confidence < 0.8` 또는 미탐지 도메인

```tsx
// molecules/MetadataLearnModal.tsx
const NOT_LISTED = "__not_listed__";

export function MetadataLearnModal({ prescanResult, suggestions, onSubmit, onCancel }) {
  const [selectedFramework, setSelectedFramework] = useState(suggestions[0] ?? "");
  const [customFramework, setCustomFramework]     = useState("");
  const [pattern, setPattern]                     = useState("");
  const [supportedLangs, setSupportedLangs]       = useState("");
  const [defaultLang, setDefaultLang]             = useState("");
  const [isSubmitting, setIsSubmitting]           = useState(false);
  const [errorMessage, setErrorMessage]           = useState("");

  const isCustom  = selectedFramework === NOT_LISTED;
  const canSubmit = (isCustom ? customFramework.trim() : selectedFramework.trim())
                    && pattern.trim() && supportedLangs.trim();

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    try {
      await onSubmit({
        framework:      isCustom ? customFramework : selectedFramework,
        pattern,
        supported_langs: supportedLangs.split(",").map(s => s.trim()),
        default_lang:    defaultLang.trim() || undefined,
      });
    } catch {
      setErrorMessage("학습 요청에 실패했습니다. 다시 시도해주세요.");
    } finally { setIsSubmitting(false); }
  };

  return (
    <div role="dialog" className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" />
      <div className="relative w-[480px] max-w-[90vw] bg-white rounded-2xl shadow-2xl p-6 flex flex-col gap-4">
        <div>
          <h3 className="font-serif text-lg font-bold text-stone-900">
            메타데이터 자동 추론 실패 — 수동 보정 필요
          </h3>
          <p className="text-sm text-stone-500 mt-1 truncate">{prescanResult.original_url}</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          {/* 1. 프레임워크 선택 */}
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-stone-600">프레임워크</span>
            <select value={selectedFramework} onChange={e => setSelectedFramework(e.target.value)}
                    className="rounded border border-stone-300 px-2 py-1.5 text-sm">
              {suggestions.map(fw => <option key={fw}>{fw}</option>)}
              <option value={NOT_LISTED}>[목록에 없음 — 직접 입력]</option>
            </select>
          </label>

          {/* 2. 직접 입력 (조건부) */}
          {isCustom && (
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-stone-600">신규 프레임워크명</span>
              <input value={customFramework} onChange={e => setCustomFramework(e.target.value)}
                     placeholder="예: Astro"
                     className="rounded border border-stone-300 px-2 py-1.5 text-sm" />
            </label>
          )}

          {/* 3. URL 패턴 */}
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-stone-600">URL 패턴 (정규식)</span>
            <input value={pattern} onChange={e => setPattern(e.target.value)}
                   placeholder="예: docs\.astro\.build"
                   className="rounded border border-stone-300 px-2 py-1.5 text-sm font-mono" />
          </label>

          {/* 4. 지원 언어 */}
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-stone-600">지원 언어 (쉼표 구분)</span>
            <input value={supportedLangs} onChange={e => setSupportedLangs(e.target.value)}
                   placeholder="예: TypeScript, JavaScript"
                   className="rounded border border-stone-300 px-2 py-1.5 text-sm" />
          </label>

          {/* 5. 기본 언어 */}
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-stone-600">기본 언어 (선택)</span>
            <input value={defaultLang} onChange={e => setDefaultLang(e.target.value)}
                   placeholder="예: TypeScript"
                   className="rounded border border-stone-300 px-2 py-1.5 text-sm" />
          </label>

          {errorMessage && (
            <p role="alert" className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1.5">
              {errorMessage}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <Button variant="outline" onClick={onCancel}>취소</Button>
            <Button variant="primary" type="submit" disabled={!canSubmit || isSubmitting}>
              {isSubmitting ? "학습 중..." : "학습 및 계속"}
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}
```

---

## 4. Organisms

### 4.1 ApprovalPanel — HITL 전체 승인/거부

```tsx
// organisms/ApprovalPanel.tsx
export function ApprovalPanel({ diff, isLoading, onApproveAll, onRejectAll }) {
  return (
    <div className="flex flex-col gap-4 rounded-lg border bg-white p-4 shadow-sm">
      {diff === null
        ? <p className="text-sm text-gray-500">로딩 중...</p>
        : <DiffSummaryCard
            newCount={diff.draft}
            updateCount={diff.approved}
            mergeCount={diff.committed}
          />
      }
      <div className="flex gap-2">
        {isLoading ? (
          <>
            <Button variant="primary" disabled>전체 승인</Button>
            <Button variant="danger"  disabled>전체 거부</Button>
            {/* CSS 스피너 (외부 라이브러리 없음) */}
            <span className="inline-block h-5 w-5 animate-spin rounded-full
                             border-2 border-blue-500 border-t-transparent" />
          </>
        ) : (
          <>
            <Button variant="primary" onClick={onApproveAll}>전체 승인</Button>
            <Button variant="danger"  onClick={onRejectAll}>전체 거부</Button>
          </>
        )}
      </div>
    </div>
  );
}
```

### 4.2 ConceptInspector — 상세 인스펙터 패널

```tsx
// organisms/ConceptInspector.tsx
export function ConceptInspector({ node, isDraft, onApprove, onReject, onClose }) {
  // ★ 빈 상태 가드레일 — 무한 로딩 탈출
  if (!node) {
    return (
      <div className="flex h-48 items-center justify-center rounded-lg border bg-white
                      text-sm text-gray-400">
        노드를 클릭하세요
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border bg-white p-4 shadow-sm">
      {/* 헤더: 이름 + 도메인/ActionBadge + 닫기 */}
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-gray-900">{node.name}</span>
          {node.domains?.map(d => <DomainBadge key={d} domain={d} size="sm" />)}
          {node.infer_action && (
            <ActionBadge
              action={node.infer_action}
              confidence={node.infer_confidence}
              target={node.target_concept_name}
            />
          )}
        </div>
        <button onClick={onClose}
                className="shrink-0 text-gray-400 hover:text-gray-600 text-sm">✕</button>
      </div>

      {/* 상세 정보 — 2열 그리드 */}
      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
        {node.cwe_id && (
          <><dt className="text-gray-400 whitespace-nowrap">CWE</dt>
            <dd className="font-mono text-gray-800">{node.cwe_id}</dd></>
        )}
        {node.owasp_id && (
          <><dt className="text-gray-400 whitespace-nowrap">OWASP</dt>
            <dd className="font-mono text-gray-800">{node.owasp_id}</dd></>
        )}
        {node.severity && (
          <><dt className="text-gray-400">Severity</dt>
            <dd className={SEVERITY_CLASS[node.severity]}>{node.severity}</dd></>
        )}
        {node.description_ko && (
          <><dt className="text-gray-400 pt-0.5">설명</dt>
            <dd className="text-gray-800 leading-relaxed">{node.description_ko}</dd></>
        )}
        {node.aliases?.length > 0 && (
          <><dt className="text-gray-400 pt-0.5">별칭</dt>
            <dd className="flex flex-wrap gap-1">
              {node.aliases.map(a => (
                <span key={a} className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-700">
                  {a}
                </span>
              ))}
            </dd></>
        )}
        {/* infer_confidence 신뢰도 바 */}
        {node.infer_confidence != null && (
          <><dt className="text-gray-400">신뢰도</dt>
            <dd className="flex items-center gap-2">
              <div className="h-1.5 w-24 rounded-full bg-gray-200">
                <div className="h-full rounded-full bg-blue-500 transition-all"
                     style={{ width: `${node.infer_confidence * 100}%` }} />
              </div>
              <span className="text-xs text-gray-500">
                {(node.infer_confidence * 100).toFixed(1)}%
              </span>
            </dd></>
        )}
      </dl>

      {/* ★ CodeExample 가드레일 — 없으면 즉시 표시, 스피너 금지 */}
      {node.mechanisms?.length === 0 && (
        <p className="text-xs text-gray-400 italic">코드 예제 없음</p>
      )}

      {/* DRAFT 전용 승인/거부 */}
      {isDraft && (
        <div className="flex gap-2 border-t pt-3">
          <Button variant="primary" onClick={() => onApprove(node.id)}>승인</Button>
          <Button variant="danger"  onClick={() => onReject(node.id)}>거부</Button>
        </div>
      )}
    </div>
  );
}
```

### 4.3 TopologyViewer — DRAFT/COMMITTED/MERGE_PENDING 그래프 시각화

**노드 상태별 스타일 규칙:**

```typescript
// utils/nodeStyler.ts
type NodeStatus = "COMMITTED" | "DRAFT" | "MERGE_PENDING" | "REJECTED";

export function getNodeStyle(status: NodeStatus, domain: string) {
  const color = DOMAIN_COLOR[domain] ?? "#94a3b8";
  switch (status) {
    case "COMMITTED":     return { opacity: 1,    dashed: false, color };
    case "DRAFT":         return { opacity: 0.65, dashed: true,  color };           // 점선 + 반투명
    case "MERGE_PENDING": return { opacity: 1,    dashed: false, color,
                                   ring: "#8B5CF6" };                               // 보라 링
    case "REJECTED":      return { opacity: 0.3,  dashed: false, color: "#E24B4A" }; // 빨간+반투명
    default:              return { opacity: 0.5,  dashed: true,  color: "#94a3b8" };
  }
}
// ★ strokeDasharray는 SVG 속성 → react-force-graph-2d의 nodeCanvasObject 커스텀 콜백으로 직접 그려야 함
```

**DRAFT 가상 노드 병합 로직 (hooks/useGraphMerge.ts):**
```
MERGE      → target 노드 상태를 MERGE_PENDING으로 변경 (신규 노드 없음)
RELATED_TO → 신규 DRAFT 노드 생성 + RELATED_TO_CANDIDATE 엣지
NEW        → 신규 독립 DRAFT 노드 (엣지 없음)
```

**범례 컴포넌트 (좌하단 고정):**
```tsx
const LEGEND = [
  { label: "security",     color: "#1D9E75" },
  { label: "performance",  color: "#BA7517" },
  { label: "both",         color: "#534AB7" },
  { label: "draft (점선)", color: "#94a3b8" },
];

<div className="absolute bottom-3 left-3 z-10 flex gap-3
                rounded bg-white/80 px-2 py-1 text-xs shadow">
  {LEGEND.map(({ label, color }) => (
    <span key={label} className="flex items-center gap-1">
      <span className="inline-block h-3 w-3 rounded-full" style={{ background: color }} />
      {label}
    </span>
  ))}
</div>
```

### 4.4 LogConsole — 실시간 SSE 로그

```tsx
// organisms/LogConsole.tsx
export function LogConsole({ logs, isConnected }: { logs: string[]; isConnected: boolean }) {
  const bottomRef = useRef<HTMLDivElement>(null);
  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [logs]);

  return (
    <div className="flex flex-col rounded-lg border border-gray-700 bg-gray-950 text-sm">
      <div className="flex items-center justify-between border-b border-gray-700 px-3 py-1.5">
        <span className="font-mono text-xs text-gray-400">Runtime Log</span>
        {isConnected
          ? <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-green-400" />
          : <span className="text-xs text-red-400">연결 끊김</span>
        }
      </div>
      <div className="h-48 overflow-y-auto p-3 space-y-0.5">
        {logs.map((line, i) => (
          <div key={i} className="font-mono text-xs text-gray-300 leading-relaxed">{line}</div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
```

---

## 5. 토스트 알림 시스템 (외부 라이브러리 없음)

```tsx
// 타입
type ToastKind = "info" | "success" | "warning" | "error";
type ToastItem = { id: string; kind: ToastKind; message: string };

// 훅
export function useToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const addToast = useCallback((kind: ToastKind, message: string) => {
    const id = `t-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setToasts(prev => [...prev, { id, kind, message }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 4000);
  }, []);
  const dismiss = useCallback((id: string) =>
    setToasts(prev => prev.filter(t => t.id !== id)), []);
  return { toasts, addToast, dismiss };
}

// 컨테이너 (페이지 최상단 삽입)
const KIND_CLASS: Record<ToastKind, string> = {
  success: "bg-emerald-50 border-emerald-200 text-emerald-800",
  error:   "bg-rose-50    border-rose-200    text-rose-800",
  warning: "bg-amber-50   border-amber-200   text-amber-800",
  info:    "bg-white      border-stone-200   text-stone-800",
};
const KIND_ICON = { success: "✓", error: "✗", warning: "⚠", info: "ℹ" };

function ToastContainer({ toasts, onDismiss }) {
  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 pointer-events-none"
         role="status" aria-live="polite">
      {toasts.map(t => (
        <div key={t.id}
             className={`pointer-events-auto flex items-center gap-2 rounded-xl border
               px-4 py-3 shadow-lg text-sm font-medium max-w-sm ${KIND_CLASS[t.kind]}`}>
          <span className="shrink-0">{KIND_ICON[t.kind]}</span>
          <span className="flex-1">{t.message}</span>
          <button onClick={() => onDismiss(t.id)}
                  className="shrink-0 text-stone-400 hover:text-stone-600">×</button>
        </div>
      ))}
    </div>
  );
}

// 사용 예시
addToast("success", `${count}개 핵심 기술 개념 도출 완료`);
addToast("error",   "Extractor 실패 — 추출된 개념이 없습니다");
addToast("info",    "Crawler Agent 시작 — 원본 텍스트 정제 중");
addToast("warning", "ETag 중복 감지 — 재크롤링 건너뜁니다");
```

---

## 6. 페이지 레벨 상태 머신

```typescript
type PipelineState =
  | "IDLE"             // 초기, URL 입력 대기
  | "RUNNING"          // 파이프라인 진행 중
  | "WAITING_APPROVAL" // HITL 게이트 — 사용자 승인 대기
  | "COMMITTING"       // 최종 적재 중
  | "FINISHED"         // 완료
  | "ERROR";           // 실패

// SSE 이벤트 처리 (usePipelineSSE)
// step_update → StepStatuses 갱신 → PipelineStepIndicator 자동 반영
// log         → LogConsole.logs 추가
// finished    → pipelineState = "FINISHED"
```

---

## 7. 구현 체크리스트 (신규 프로젝트 순서)

```
[ ] 1. 디자인 토큰 파일 (constants/colors.ts, constants/severity.ts)
[ ] 2. atoms: StatusDot → DomainBadge + ActionBadge → Button
[ ] 3. molecules: PipelineStepIndicator → DiffSummaryCard
             → DuplicateDocumentModal → MetadataLearnModal
[ ] 4. organisms: ApprovalPanel → LogConsole → ConceptInspector → TopologyViewer
[ ] 5. hooks: useToast → usePipelineSSE → useStagingApproval → useGraphMerge
[ ] 6. services: api.ts(baseURL VITE_API_BASE) → pipelineOrchestrator
             → stagingService → graphService
[ ] 7. 페이지 조립: PipelineState 머신 + ToastContainer + DashboardLayout
[ ] 8. 의존성: react-force-graph-2d, axios, react-router-dom@7, Tailwind
```

---

## ★ 구현 주의사항

- ★ **코드 예제 무한 로딩 방지**: `node.mechanisms?.length === 0` 즉시 "코드 예제 없음" 렌더. `undefined`와 `[]` 모두 처리.
- ★ **DRAFT 점선 노드**: `strokeDasharray`는 CSS 불가, `react-force-graph-2d`의 `nodeCanvasObject` 커스텀 콜백에서 Canvas API(`ctx.setLineDash([5,3])`)로 직접 그려야 함.
- ★ **SSE 프록시**: `X-Accel-Buffering: no` 헤더 없으면 nginx가 버퍼링해 실시간 로그 안 보임. 백엔드 응답 헤더에 반드시 추가.
- ★ **ActionBadge 위치**: ConceptInspector 헤더 + 그래프 노드 호버 툴팁 **두 곳** 모두 표시.
- ★ **infer_confidence만 신뢰**: `score_jaro_winkler/name_vector/desc_vector`는 현재 버그로 0.0. 신뢰도 바에는 `infer_confidence`(최종 결합 점수)만 표시.
