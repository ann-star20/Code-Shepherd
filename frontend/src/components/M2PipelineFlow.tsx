const STAGES = [
  { key: "run_tools",     label: "도구 실행",   icon: "🔧", step: 1, nodeType: "tool"  as const, tools: "Pylint · Radon · ESLint · Bandit · Semgrep" },
  { key: "vector_search", label: "벡터 검색",   icon: "🔍", step: 2, nodeType: "tool"  as const, tools: "유사 이슈 RAG 검색" },
  { key: "llm_judge",     label: "LLM 판정",    icon: "⚖️", step: 3, nodeType: "agent" as const, tools: "심각도 · 오탐 판정" },
  { key: "store",         label: "결과 저장",   icon: "💾", step: 4, nodeType: "tool"  as const, tools: "이슈 영속화" },
] as const;

type StageKey = typeof STAGES[number]["key"];
type StageStatus = "pending" | "running" | "success" | "fail";

export type M2StageKey = StageKey;
export interface M2StageTrace {
  key:     StageKey;
  status:  StageStatus;
  ms?:     number;
}

function formatMs(ms: number): string {
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

const STATUS_BG: Record<StageStatus, string> = {
  success: "#f0fdf4",
  fail:    "#fef2f2",
  running: "#fffbeb",
  pending: "#f9fafb",
};
const STATUS_BORDER: Record<StageStatus, string> = {
  success: "#22c55e",
  fail:    "#ef4444",
  running: "#f59e0b",
  pending: "#e5e7eb",
};
const STATUS_DOT: Record<StageStatus, string> = {
  success: "#22c55e",
  fail:    "#ef4444",
  running: "#f59e0b",
  pending: "#d1d5db",
};
const STATUS_LABEL: Record<StageStatus, string> = {
  success: "완료",
  fail:    "실패",
  running: "실행중",
  pending: "대기",
};

export interface M2StageResult {
  staticIssues:   number;
  securityIssues: number;
}

interface Props {
  isLoading: boolean;
  stages?:   M2StageTrace[];
  found?:    boolean;
  result?:   M2StageResult;
}

export function M2PipelineFlow({ isLoading, stages, found, result }: Props) {
  const ORDER: StageKey[] = ["run_tools", "vector_search", "llm_judge", "store"];
  const byKey = Object.fromEntries((stages ?? []).map(t => [t.key, t]));

  function stageStatus(key: StageKey): StageStatus {
    const t = byKey[key];
    if (t) return t.status;
    // 단계별 데이터가 없으면 found/isLoading로 대략 표시 (백엔드 trace 연결 전 폴백)
    if (found) return "success";
    if (isLoading) return ORDER.indexOf(key) === 0 ? "running" : "pending";
    return "pending";
  }

  const successCount = STAGES.filter(st => stageStatus(st.key) === "success").length;
  const runningStage = STAGES.find(st => stageStatus(st.key) === "running");

  return (
    <div style={s.wrapper}>
      <div style={s.header}>
        <div style={s.headerLeft}>
          <span style={{ fontSize: 16 }}>🔍</span>
          <span style={s.headerTitle}>M2 정적 분석 · 보안 스캔 파이프라인</span>
        </div>
        <div style={s.headerRight}>
          <span style={{ ...s.badge, background: "#ede9fe", color: "#6d28d9", borderColor: "#c4b5fd" }}>
            🤖 LLM Agent ×1
          </span>
          <span style={{ ...s.badge, background: "#f3f4f6", color: "#6b7280", borderColor: "#e5e7eb" }}>
            ⚙️ Tool ×3
          </span>
          {result && (
            <>
              <span style={{ ...s.badge, background: "#ede9fe", color: "#6d28d9", borderColor: "#c4b5fd" }}>
                SA {result.staticIssues}건
              </span>
              <span style={{ ...s.badge, background: "#fee2e2", color: "#dc2626", borderColor: "#fca5a5" }}>
                SEC {result.securityIssues}건
              </span>
            </>
          )}
          {runningStage && (
            <span style={{ ...s.counter, color: "#b45309", borderColor: "#fcd34d", background: "#fffbeb", border: "1px solid" }}>
              ▶ {runningStage.label} 처리중
            </span>
          )}
          <span style={s.counter}>{successCount} / {STAGES.length} 완료</span>
        </div>
      </div>

      <div style={s.flow}>
        {STAGES.flatMap((stage, i) => {
          const sk = stageStatus(stage.key);
          const stageMs    = byKey[stage.key]?.ms;
          const isRunning  = sk === "running";
          const isLlmAgent = stage.nodeType === "agent";
          const idleAccent  = isLlmAgent ? "#c4b5fd" : "#e5e7eb";
          const borderColor = sk === "pending" ? idleAccent : STATUS_BORDER[sk];
          const bgColor     = sk === "pending" && isLlmAgent ? "#f5f3ff" : STATUS_BG[sk];

          const card = (
            <div key={stage.key} style={{
              ...s.card,
              background:  bgColor,
              borderColor,
              boxShadow:   sk === "success" ? `0 0 0 1px ${borderColor}33` : "none",
              animation:   isRunning ? "pulse-glow 1.2s ease-in-out infinite" : undefined,
            }}>
              <div style={{ ...s.cardHeader, borderBottomColor: borderColor + "44" }}>
                <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                  <div style={{
                    ...s.dot,
                    background: STATUS_DOT[sk],
                    animation:  isRunning ? "pulse-dot 0.8s ease-in-out infinite" : "none",
                  }} />
                  <span style={{ ...s.cardType, color: isLlmAgent ? "#6d28d9" : "#6b7280" }}>
                    {isLlmAgent ? "Agent" : "Tool"}
                  </span>
                </div>
                <span style={s.stepNum}>{stage.step}</span>
              </div>
              <div style={s.cardBody}>
                <span style={{ fontSize: 22, lineHeight: 1 }}>{stage.icon}</span>
                <span style={s.label}>{stage.label}</span>
                <span style={s.tools}>{stage.tools}</span>
                {stageMs != null && <span style={s.timing}>{formatMs(stageMs)}</span>}
                {isRunning && <span style={s.runningBadge}>▶ 처리중</span>}
              </div>
              <div style={{ ...s.cardFooter, borderTopColor: borderColor + "33" }}>
                <span style={{ ...s.statusPill, color: borderColor, borderColor: borderColor + "55", background: borderColor + "15" }}>
                  {STATUS_LABEL[sk]}
                </span>
              </div>
            </div>
          );

          if (i < STAGES.length - 1) {
            return [
              card,
              <div key={`conn-${stage.key}`} style={s.connector}>
                <div style={{ ...s.connLine, background: sk === "success" ? "#22c55e" : "#e5e7eb" }} />
                <div style={{ ...s.connArrow, borderLeftColor: sk === "success" ? "#22c55e" : "#e5e7eb" }} />
              </div>,
            ];
          }
          return [card];
        })}
      </div>
    </div>
  );
}

const s: Record<string, React.CSSProperties> = {
  wrapper:     { background: "#ffffff", borderRadius: 12, padding: "18px 22px 22px", border: "1px solid #e5e7eb", fontFamily: "system-ui, sans-serif" },
  header:      { display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 18, paddingBottom: 12, borderBottom: "1px solid #e5e7eb", flexWrap: "wrap", gap: 8 },
  headerLeft:  { display: "flex", alignItems: "center", gap: 8 },
  headerTitle: { color: "#111827", fontSize: 13, fontWeight: 600 },
  headerRight: { display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" },
  badge:       { fontSize: 10, fontWeight: 700, padding: "3px 9px", borderRadius: 20, border: "1px solid", letterSpacing: "0.03em" },
  counter:     { color: "#6b7280", fontSize: 11, background: "#f3f4f6", padding: "3px 10px", borderRadius: 20 },
  flow:        { display: "flex", alignItems: "center", width: "100%" },
  card:        { width: 130, borderRadius: 10, border: "1.5px solid", flexShrink: 0, overflow: "hidden", transition: "border-color 0.4s, background-color 0.4s, box-shadow 0.3s" },
  cardHeader:  { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "7px 10px 6px", borderBottom: "1px solid" },
  cardType:    { fontSize: 10, fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase" as const },
  stepNum:     { color: "#9ca3af", fontSize: 10, fontWeight: 600 },
  dot:         { width: 7, height: 7, borderRadius: "50%", flexShrink: 0, transition: "background-color 0.4s" },
  cardBody:    { display: "flex", flexDirection: "column", alignItems: "center", padding: "12px 8px 10px", gap: 5, minHeight: 84, justifyContent: "center" },
  label:       { color: "#111827", fontSize: 11, fontWeight: 600, textAlign: "center", lineHeight: 1.35 },
  tools:       { fontSize: 9, color: "#9ca3af", textAlign: "center", lineHeight: 1.3 },
  timing:      { color: "#6b7280", fontSize: 10, fontVariantNumeric: "tabular-nums" },
  runningBadge:{ color: "#b45309", fontSize: 10, fontWeight: 700 },
  cardFooter:  { display: "flex", justifyContent: "center", padding: "6px 8px", borderTop: "1px solid" },
  statusPill:  { fontSize: 9, fontWeight: 700, padding: "2px 10px", borderRadius: 10, border: "1px solid", letterSpacing: "0.04em" },
  connector:   { display: "flex", alignItems: "center", flex: 1, minWidth: 16 },
  connLine:    { flex: 1, height: 2, transition: "background-color 0.4s" },
  connArrow:   { width: 0, height: 0, borderTop: "4px solid transparent", borderBottom: "4px solid transparent", borderLeft: "6px solid", transition: "border-left-color 0.4s" },
};
