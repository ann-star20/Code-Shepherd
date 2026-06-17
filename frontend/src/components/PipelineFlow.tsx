import type { AgentTraceItem } from "../types/kms";

const STAGES = [
  { agent: "DocumentParserAgent",    label: "문서 파싱 Agent",  icon: "🔬", step: 1, nodeType: "agent" as const },
  { agent: "MarkdownValidateAgent",  label: "Markdown 검증",    icon: "🔍", step: 2, nodeType: "agent" as const },
  { agent: "ChunkingAgent",          label: "청킹",             icon: "✂️", step: 3, nodeType: "tool"  as const },
  { agent: "ChunkValidateAgent",     label: "청크 검증",        icon: "📋", step: 4, nodeType: "tool"  as const },
  { agent: "MetadataExtractAgent",   label: "메타데이터 추출",  icon: "🏷️", step: 5, nodeType: "agent" as const },
  { agent: "MetadataValidateAgent",  label: "메타데이터 검증",  icon: "✅", step: 6, nodeType: "agent" as const },
  { agent: "StoreRouteAgent",        label: "저장",             icon: "💾", step: 7, nodeType: "tool"  as const },
] as const;

const STATUS_BG: Record<string, string> = {
  success: "#14532d",
  fail:    "#450a0a",
  running: "#451a03",
  pending: "#1f2937",
};

const STATUS_BORDER: Record<string, string> = {
  success: "#22c55e",
  fail:    "#ef4444",
  running: "#f59e0b",
  pending: "#374151",
};

const STATUS_LABEL: Record<string, string> = {
  success: "완료",
  fail:    "실패",
  running: "실행중",
  pending: "대기",
};

const STATUS_DOT: Record<string, string> = {
  success: "#22c55e",
  fail:    "#ef4444",
  running: "#f59e0b",
  pending: "#4b5563",
};

function formatMs(ms: number): string {
  return ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
}

interface PipelineFlowProps {
  traces: AgentTraceItem[];
  isProcessing?: boolean;
}

export function PipelineFlow({ traces, isProcessing = false }: PipelineFlowProps) {
  const byAgent = Object.fromEntries(traces.map((t) => [t.agent_name, t]));

  const lastSuccessStep = STAGES.reduce((max, s) => {
    const t = byAgent[s.agent];
    return t?.status === "success" ? Math.max(max, s.step) : max;
  }, 0);
  const runningStep = isProcessing ? lastSuccessStep + 1 : -1;

  const successCount = traces.filter((t) => t.status === "success").length;
  const runningStage = STAGES.find((s) => s.step === runningStep);

  return (
    <div style={styles.wrapper}>
      <div style={styles.header}>
        <div style={styles.headerLeft}>
          <span style={styles.headerIcon}>🤖</span>
          <span style={styles.headerTitle}>KMS 멀티 에이전트 파이프라인</span>
        </div>
        <div style={styles.headerRight}>
          <span style={{ ...styles.badge, background: "#1e1b4b", color: "#a5b4fc", borderColor: "#4f46e5" }}>
            🤖 LLM Agent ×4
          </span>
          <span style={{ ...styles.badge, background: "#1c1917", color: "#a8a29e", borderColor: "#44403c" }}>
            ⚙️ Tool ×3
          </span>
          {isProcessing && runningStage && (
            <span style={{ ...styles.agentCount, color: "#f59e0b", borderColor: "#f59e0b55", background: "#451a03" }}>
              ▶ {runningStage.label} 처리중
            </span>
          )}
          <span style={styles.agentCount}>{successCount} / {STAGES.length} 완료</span>
        </div>
      </div>

      <div style={styles.flow}>
        {([STAGES.slice(0, 4), STAGES.slice(4)] as Array<typeof STAGES[number][]>).map((rowStages, rowIdx) => (
          <div key={rowIdx}>
            {rowIdx > 0 && (
              <div style={styles.rowDivider}>
                <div style={styles.rowConnVertLine} />
                <div style={styles.rowConnHorizLine} />
                <div style={styles.rowConnArrow} />
              </div>
            )}

            <div style={styles.flowRow}>
              {rowIdx > 0 && (
                <>
                  <div style={{ width: 120, flexShrink: 0 }} />
                  <div style={{ flex: 1, minWidth: 20 }} />
                </>
              )}
              {rowStages.flatMap((stage, i) => {
                const trace          = byAgent[stage.agent];
                const isRunning      = stage.step === runningStep;
                const rawTraceStatus = trace?.status ?? "pending";
                const sk: keyof typeof STATUS_BORDER =
                  isRunning
                    ? "running"
                    : !isProcessing && rawTraceStatus === "running"
                    ? "fail"
                    : rawTraceStatus;

                const isLlmAgent  = stage.nodeType === "agent";
                const idleAccent  = isLlmAgent ? "#4f46e5" : "#374151";
                const borderColor = (sk === "pending" && !isRunning) ? idleAccent : STATUS_BORDER[sk];
                const bgColor     = (sk === "pending" && !isRunning && isLlmAgent) ? "#1e1b4b" : STATUS_BG[sk];

                const card = (
                  <div
                    key={stage.agent}
                    style={{
                      ...styles.nodeCard,
                      background:  bgColor,
                      borderColor: borderColor,
                      animation: isRunning ? "pulse-glow 1.2s ease-in-out infinite" : undefined,
                      boxShadow: sk === "success" ? `0 0 0 1px ${borderColor}33` : "none",
                    }}
                    title={trace?.error_message ?? undefined}
                  >
                    <div style={{ ...styles.cardHeader, borderBottomColor: borderColor + "44" }}>
                      <div style={styles.cardHeaderLeft}>
                        <div style={{
                          ...styles.statusDot,
                          background: STATUS_DOT[sk],
                          animation: isRunning ? "pulse-dot 0.8s ease-in-out infinite" : "none",
                        }} />
                        <span style={{ ...styles.cardType, color: isLlmAgent ? "#a5b4fc" : "#6b7280" }}>
                          {isLlmAgent ? "Agent" : "Tool"}
                        </span>
                      </div>
                      <span style={styles.stepNum}>{stage.step}</span>
                    </div>

                    <div style={styles.cardBody}>
                      <span style={styles.nodeIcon}>{stage.icon}</span>
                      <span style={styles.nodeLabel}>{stage.label}</span>
                      {trace?.execution_ms != null && (
                        <span style={styles.timing}>{formatMs(trace.execution_ms)}</span>
                      )}
                      {isRunning && <span style={styles.runningBadge}>▶ 처리중</span>}
                      {sk === "fail" && trace?.error_message && (
                        <span style={styles.errorMsg}>{trace.error_message.slice(0, 30)}…</span>
                      )}
                    </div>

                    <div style={{ ...styles.cardFooter, borderTopColor: borderColor + "33" }}>
                      <span style={{ ...styles.statusPill, color: borderColor, borderColor: borderColor + "55", background: borderColor + "15" }}>
                        {STATUS_LABEL[sk]}
                      </span>
                    </div>
                  </div>
                );

                if (i < rowStages.length - 1) {
                  return [
                    card,
                    <div key={`conn-${stage.agent}`} style={styles.connector}>
                      <div style={{ ...styles.connLine, background: sk === "success" ? "#22c55e66" : "#374151" }} />
                      <div style={{ ...styles.connArrow, borderLeftColor: sk === "success" ? "#22c55e66" : "#374151" }} />
                    </div>,
                  ];
                }
                return [card];
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  wrapper: {
    background:   "#0d1117",
    borderRadius: 14,
    padding:      "20px 24px 24px",
    marginTop:    24,
    border:       "1px solid #21262d",
    fontFamily:   "system-ui, sans-serif",
  },
  header: {
    display:        "flex",
    alignItems:     "center",
    justifyContent: "space-between",
    marginBottom:   20,
    paddingBottom:  14,
    borderBottom:   "1px solid #21262d",
  },
  headerLeft:  { display: "flex", alignItems: "center", gap: 8 },
  headerIcon:  { fontSize: 16 },
  headerTitle: { color: "#e6edf3", fontSize: 13, fontWeight: 600 },
  headerRight: { display: "flex", alignItems: "center", gap: 6 },
  badge: {
    fontSize: 10, fontWeight: 700, padding: "3px 9px",
    borderRadius: 20, border: "1px solid", letterSpacing: "0.03em",
  },
  agentCount: {
    color: "#8b949e", fontSize: 11, background: "#21262d",
    padding: "3px 10px", borderRadius: 20,
  },
  flow:    { display: "flex", flexDirection: "column", gap: 0, padding: "0 0 8px" },
  flowRow: { display: "flex", alignItems: "center", gap: 0, width: "100%" },
  rowDivider:       { position: "relative", height: 36, margin: "4px 0" },
  rowConnVertLine:  { position: "absolute" as const, right: 60, top: 0, width: 2, height: 18, background: "#4b5563", borderRadius: 1 },
  rowConnHorizLine: { position: "absolute" as const, left: "calc(33.333% + 20px)", top: 16, width: "calc(66.667% - 80px)", height: 2, background: "#4b5563" },
  rowConnArrow:     { position: "absolute" as const, left: "calc(33.333% + 15px)", top: 18, width: 0, height: 0, borderLeft: "5px solid transparent", borderRight: "5px solid transparent", borderTop: "6px solid #6b7280" },
  nodeCard: {
    width: 120, borderRadius: 10, border: "1.5px solid", flexShrink: 0,
    cursor: "default", transition: "border-color 0.4s ease, background-color 0.4s ease, box-shadow 0.3s", overflow: "hidden",
  },
  cardHeader:     { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "7px 10px 6px", borderBottom: "1px solid" },
  cardHeaderLeft: { display: "flex", alignItems: "center", gap: 6 },
  statusDot:  { width: 7, height: 7, borderRadius: "50%", flexShrink: 0, transition: "background-color 0.4s ease" },
  cardType:   { fontSize: 10, fontWeight: 700, letterSpacing: "0.05em", textTransform: "uppercase" as const },
  stepNum:    { color: "#6e7681", fontSize: 10, fontWeight: 600 },
  cardBody:   { display: "flex", flexDirection: "column", alignItems: "center", padding: "12px 8px 10px", gap: 6, minHeight: 74, justifyContent: "center" },
  nodeIcon:   { fontSize: 22, lineHeight: 1 },
  nodeLabel:  { color: "#e6edf3", fontSize: 11, fontWeight: 600, textAlign: "center", lineHeight: 1.35 },
  timing:     { color: "#8b949e", fontSize: 10, fontVariantNumeric: "tabular-nums" },
  runningBadge: { color: "#f59e0b", fontSize: 10, fontWeight: 700 },
  errorMsg:   { color: "#f87171", fontSize: 9, textAlign: "center", lineHeight: 1.3, maxWidth: 100 },
  cardFooter: { display: "flex", justifyContent: "center", padding: "6px 8px", borderTop: "1px solid" },
  statusPill: { fontSize: 9, fontWeight: 700, padding: "2px 10px", borderRadius: 10, border: "1px solid", letterSpacing: "0.04em" },
  connector:  { display: "flex", alignItems: "center", flex: 1, minWidth: 20 },
  connLine:   { flex: 1, height: 2, transition: "background-color 0.4s ease" },
  connArrow:  { width: 0, height: 0, borderTop: "4px solid transparent", borderBottom: "4px solid transparent", borderLeft: "6px solid", transition: "border-left-color 0.4s ease" },
};
