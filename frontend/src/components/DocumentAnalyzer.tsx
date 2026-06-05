import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { ChunkItem } from "../types/kms";

type TabKey   = "all" | "parent" | "child";
type ViewMode = "rendered" | "raw";
type TopView  = "chunks" | "preview";

interface DocumentAnalyzerProps {
  chunks: ChunkItem[];
}

function analyzeMarkdown(text: string) {
  const tables     = (text.match(/^\|[-|:\s]+\|/gm)  ?? []).length;
  const headers    = (text.match(/^#{1,6}\s/gm)       ?? []).length;
  const codeBlocks = Math.floor((text.match(/```/g)   ?? []).length / 2);
  const lists      = (text.match(/^[-*+]\s/gm)        ?? []).length;
  const images     = (text.match(/!\[/g)              ?? []).length;
  return { tables, headers, codeBlocks, lists, images };
}

export function DocumentAnalyzer({ chunks }: DocumentAnalyzerProps) {
  const [topView,     setTopView]     = useState<TopView>("chunks");
  const [activeTab,   setActiveTab]   = useState<TabKey>("all");
  const [selectedId,  setSelectedId]  = useState<string>(chunks[0]?.chunk_id ?? "");
  const [viewMode,    setViewMode]    = useState<ViewMode>("rendered");
  const [previewMode, setPreviewMode] = useState<ViewMode>("rendered");

  const parentChunks = chunks.filter(c => c.chunk_type === "parent");
  const childChunks  = chunks.filter(c => c.chunk_type === "child");

  const fullMarkdown = parentChunks
    .slice()
    .sort((a, b) => (a.page_number ?? 999) - (b.page_number ?? 999))
    .map(c => c.content)
    .join("\n\n---\n\n");

  const stats = analyzeMarkdown(fullMarkdown);

  const filtered =
    activeTab === "all"    ? chunks :
    activeTab === "parent" ? parentChunks :
    childChunks;

  const selected = chunks.find(c => c.chunk_id === selectedId) ?? filtered[0] ?? null;

  const TABS: { key: TabKey; label: string }[] = [
    { key: "all",    label: `전체 (${chunks.length})`         },
    { key: "parent", label: `Parent (${parentChunks.length})` },
    { key: "child",  label: `Child (${childChunks.length})`   },
  ];

  return (
    <div style={styles.wrapper}>
      <div style={styles.cardHeader}>
        <div style={styles.headerLeft}>
          <span style={styles.heading}>문서 파싱 결과</span>
          <span style={styles.subheading}>{chunks.length}개 청크</span>
        </div>
        <div style={styles.topSwitcher}>
          <button style={{ ...styles.switchBtn, ...(topView === "chunks"  ? styles.switchBtnActive : {}) }} onClick={() => setTopView("chunks")}>
            📋 청크 분석
          </button>
          <button style={{ ...styles.switchBtn, ...(topView === "preview" ? styles.switchBtnActive : {}) }} onClick={() => setTopView("preview")}>
            📄 파싱 미리보기
          </button>
        </div>
      </div>

      {topView === "chunks" && (
        <>
          <div style={styles.tabBar}>
            {TABS.map(tab => (
              <button key={tab.key} style={{ ...styles.tab, ...(activeTab === tab.key ? styles.tabActive : {}) }} onClick={() => setActiveTab(tab.key)}>
                {tab.label}
              </button>
            ))}
            <div style={{ marginLeft: "auto", display: "flex", gap: 0 }}>
              {(["rendered", "raw"] as const).map(m => (
                <button key={m} style={{ ...styles.viewBtn, ...(viewMode === m ? styles.viewBtnActive : {}) }} onClick={() => setViewMode(m)}>
                  {m === "rendered" ? "렌더링 뷰" : "Raw 텍스트"}
                </button>
              ))}
            </div>
          </div>

          <div style={styles.body}>
            <div style={styles.leftPanel}>
              <table style={styles.table}>
                <thead>
                  <tr>
                    {["#", "타입", "섹션", "토큰", "페이지"].map(h => (
                      <th key={h} style={styles.th}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.length === 0 ? (
                    <tr><td colSpan={5} style={{ ...styles.td, color: "#9ca3af", textAlign: "center", padding: 16 }}>청크 없음</td></tr>
                  ) : (
                    filtered.map((chunk, i) => {
                      const isActive = chunk.chunk_id === selectedId;
                      const isParent = chunk.chunk_type === "parent";
                      return (
                        <tr key={chunk.chunk_id} style={{ ...styles.tr, ...(isActive ? styles.trActive : {}), cursor: "pointer" }} onClick={() => setSelectedId(chunk.chunk_id)}>
                          <td style={{ ...styles.td, color: "#94a3b8", width: 28 }}>{i + 1}</td>
                          <td style={styles.td}>
                            <span style={{ ...styles.typeBadge, background: isParent ? "#6366f1" : "#0ea5e9" }}>{chunk.chunk_type}</span>
                          </td>
                          <td style={{ ...styles.td, maxWidth: 90, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                            <span style={{ color: "#475569", fontSize: 11 }}>{chunk.section_header?.slice(0, 14) ?? "—"}</span>
                          </td>
                          <td style={{ ...styles.td, color: "#64748b", fontVariantNumeric: "tabular-nums" }}>{chunk.token_count ?? "—"}</td>
                          <td style={{ ...styles.td, color: "#64748b", fontVariantNumeric: "tabular-nums" }}>{chunk.page_number ?? "—"}</td>
                        </tr>
                      );
                    })
                  )}
                </tbody>
              </table>
            </div>

            <div style={styles.rightPanel}>
              {selected ? (
                <>
                  <div style={styles.metaRow}>
                    <span style={{ ...styles.typeBadge, background: selected.chunk_type === "parent" ? "#6366f1" : "#0ea5e9", fontSize: 12, padding: "3px 10px" }}>
                      {selected.chunk_type}
                    </span>
                    {selected.section_header && <span style={styles.sectionTitle}>{selected.section_header}</span>}
                    <div style={styles.metaStats}>
                      {selected.token_count != null && <span style={styles.stat}>{selected.token_count} tokens</span>}
                      {selected.page_number  != null && <span style={styles.stat}>p.{selected.page_number}</span>}
                      <span style={styles.stat}>{selected.content.length} chars</span>
                    </div>
                  </div>
                  <div style={styles.contentArea}>
                    {viewMode === "rendered" ? (
                      <div style={styles.markdownBody}>
                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>{selected.content}</ReactMarkdown>
                      </div>
                    ) : (
                      <pre style={styles.rawContent}>{selected.content}</pre>
                    )}
                  </div>
                </>
              ) : (
                <p style={{ color: "#9ca3af", fontSize: 13, padding: 16 }}>왼쪽 목록에서 청크를 선택하세요</p>
              )}
            </div>
          </div>
        </>
      )}

      {topView === "preview" && (
        <div style={styles.previewWrapper}>
          <div style={styles.previewSidebar}>
            <p style={styles.sidebarTitle}>구조 분석</p>
            {[
              { icon: "📊", label: "감지된 표",    val: stats.tables,     color: stats.tables > 0 ? "#16a34a" : "#dc2626",  mark: stats.tables > 0 ? "✅" : "⚠️" },
              { icon: "📑", label: "헤더 / 제목",  val: stats.headers,    color: stats.headers > 0 ? "#2563eb" : "#94a3b8", mark: stats.headers > 0 ? "✅" : "—" },
              { icon: "💻", label: "코드 블록",    val: stats.codeBlocks, color: "#64748b", mark: "" },
              { icon: "📝", label: "리스트 항목",  val: stats.lists,      color: "#64748b", mark: "" },
              { icon: "🖼️", label: "이미지 참조",  val: stats.images,     color: "#64748b", mark: "" },
            ].map(({ icon, label, val, color, mark }) => (
              <div key={label} style={styles.statCard}>
                <span style={styles.statIcon}>{icon}</span>
                <div style={styles.statInfo}>
                  <span style={styles.statLabel}>{label}</span>
                  <span style={{ ...styles.statValue, color }}>{val}개 {mark}</span>
                </div>
              </div>
            ))}
            <div style={styles.sidebarDivider} />
            <div style={styles.statCard}>
              <span style={styles.statIcon}>🗂️</span>
              <div style={styles.statInfo}><span style={styles.statLabel}>Parent 청크</span><span style={{ ...styles.statValue, color: "#6366f1" }}>{parentChunks.length}개</span></div>
            </div>
            <div style={styles.statCard}>
              <span style={styles.statIcon}>✂️</span>
              <div style={styles.statInfo}><span style={styles.statLabel}>Child 청크</span><span style={{ ...styles.statValue, color: "#0ea5e9" }}>{childChunks.length}개</span></div>
            </div>
          </div>

          <div style={styles.previewMain}>
            <div style={styles.previewHeader}>
              <span style={styles.previewHeaderTitle}>전체 문서 미리보기</span>
              <div style={{ display: "flex", gap: 0 }}>
                {(["rendered", "raw"] as const).map(m => (
                  <button key={m} style={{ ...styles.viewBtn, ...(previewMode === m ? styles.viewBtnActive : {}) }} onClick={() => setPreviewMode(m)}>
                    {m === "rendered" ? "렌더링 뷰" : "Raw 텍스트"}
                  </button>
                ))}
              </div>
            </div>
            <div style={styles.previewContent}>
              {fullMarkdown ? (
                previewMode === "rendered" ? (
                  <div style={styles.markdownBody}>
                    <ReactMarkdown remarkPlugins={[remarkGfm]} components={mdComponents}>{fullMarkdown}</ReactMarkdown>
                  </div>
                ) : (
                  <pre style={{ ...styles.rawContent, margin: 0, borderRadius: 0, background: "transparent" }}>{fullMarkdown}</pre>
                )
              ) : (
                <p style={{ color: "#9ca3af", fontSize: 13, padding: 16 }}>Parent 청크가 없습니다.</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const mdComponents = {
  table:      ({ ...p }: React.HTMLAttributes<HTMLTableElement>)           => <table      style={markdownStyles.table}      {...p} />,
  thead:      ({ ...p }: React.HTMLAttributes<HTMLTableSectionElement>)    => <thead      style={markdownStyles.thead}      {...p} />,
  th:         ({ ...p }: React.ThHTMLAttributes<HTMLTableCellElement>)     => <th         style={markdownStyles.th}         {...p} />,
  td:         ({ ...p }: React.TdHTMLAttributes<HTMLTableCellElement>)     => <td         style={markdownStyles.td}         {...p} />,
  tr:         ({ ...p }: React.HTMLAttributes<HTMLTableRowElement>)        => <tr         style={markdownStyles.tr}         {...p} />,
  h1:         ({ ...p }: React.HTMLAttributes<HTMLHeadingElement>)         => <h1         style={markdownStyles.h1}         {...p} />,
  h2:         ({ ...p }: React.HTMLAttributes<HTMLHeadingElement>)         => <h2         style={markdownStyles.h2}         {...p} />,
  h3:         ({ ...p }: React.HTMLAttributes<HTMLHeadingElement>)         => <h3         style={markdownStyles.h3}         {...p} />,
  p:          ({ ...p }: React.HTMLAttributes<HTMLParagraphElement>)       => <p          style={markdownStyles.p}          {...p} />,
  pre:        ({ ...p }: React.HTMLAttributes<HTMLPreElement>)             => <pre        style={markdownStyles.pre}        {...p} />,
  code:       ({ ...p }: React.HTMLAttributes<HTMLElement>)                => <code       style={markdownStyles.code}       {...p} />,
  ul:         ({ ...p }: React.HTMLAttributes<HTMLUListElement>)           => <ul         style={markdownStyles.ul}         {...p} />,
  ol:         ({ ...p }: React.OlHTMLAttributes<HTMLOListElement>)         => <ol         style={markdownStyles.ol}         {...p} />,
  li:         ({ ...p }: React.LiHTMLAttributes<HTMLLIElement>)            => <li         style={markdownStyles.li}         {...p} />,
  blockquote: ({ ...p }: React.BlockquoteHTMLAttributes<HTMLQuoteElement>) => <blockquote style={markdownStyles.blockquote} {...p} />,
  hr:         ({ ...p }: React.HTMLAttributes<HTMLHRElement>)              => <hr         style={markdownStyles.hr}         {...p} />,
};

const styles: Record<string, React.CSSProperties> = {
  wrapper:      { marginTop: 16, background: "#fff", borderRadius: 12, border: "1px solid #e2e8f0", boxShadow: "0 1px 4px rgba(0,0,0,0.04)", overflow: "hidden", fontFamily: "system-ui, sans-serif" },
  cardHeader:   { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 20px 0", flexWrap: "wrap", gap: 8 },
  headerLeft:   { display: "flex", alignItems: "baseline", gap: 8 },
  heading:      { fontSize: 14, fontWeight: 700, color: "#1e293b" },
  subheading:   { fontSize: 12, color: "#94a3b8" },
  topSwitcher:  { display: "flex", gap: 0, borderRadius: 8, overflow: "hidden", border: "1px solid #e2e8f0" },
  switchBtn:    { background: "#f8fafc", border: "none", borderRight: "1px solid #e2e8f0", padding: "5px 14px", fontSize: 12, fontWeight: 500, color: "#64748b", cursor: "pointer", transition: "all 0.15s", whiteSpace: "nowrap" },
  switchBtnActive: { background: "#6366f1", color: "#fff", fontWeight: 700, borderColor: "#6366f1" },
  viewBtn:      { background: "#f8fafc", border: "1px solid #e2e8f0", padding: "4px 12px", fontSize: 11, fontWeight: 500, color: "#64748b", cursor: "pointer", transition: "all 0.15s" },
  viewBtnActive: { background: "#6366f1", color: "#fff", borderColor: "#6366f1", fontWeight: 700 },
  tabBar:       { display: "flex", alignItems: "center", padding: "8px 20px 0", borderBottom: "1px solid #f1f5f9", gap: 0 },
  tab:          { background: "none", border: "none", padding: "6px 14px", fontSize: 12, fontWeight: 500, color: "#64748b", cursor: "pointer", borderBottom: "2px solid transparent", marginBottom: -1, transition: "all 0.15s" },
  tabActive:    { color: "#6366f1", borderBottomColor: "#6366f1", fontWeight: 700 },
  body:         { display: "flex", height: 420 },
  leftPanel:    { width: 240, flexShrink: 0, borderRight: "1px solid #f1f5f9", overflowY: "auto" },
  table:        { width: "100%", borderCollapse: "collapse", fontSize: 11 },
  th:           { padding: "6px 8px", textAlign: "left", color: "#94a3b8", fontWeight: 600, fontSize: 10, background: "#f8fafc", borderBottom: "1px solid #f1f5f9", position: "sticky", top: 0, whiteSpace: "nowrap" },
  td:           { padding: "7px 8px", fontSize: 11, color: "#374151", borderBottom: "1px solid #f8fafc", verticalAlign: "middle" },
  tr:           { transition: "background 0.1s" },
  trActive:     { background: "#eff6ff", borderLeft: "3px solid #6366f1" },
  typeBadge:    { display: "inline-block", fontSize: 9, fontWeight: 700, color: "#fff", padding: "1px 5px", borderRadius: 8, whiteSpace: "nowrap" },
  rightPanel:   { flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" },
  metaRow:      { display: "flex", alignItems: "center", gap: 8, padding: "10px 16px", borderBottom: "1px solid #f1f5f9", flexWrap: "wrap", flexShrink: 0 },
  sectionTitle: { fontSize: 13, fontWeight: 600, color: "#1e293b" },
  metaStats:    { marginLeft: "auto", display: "flex", gap: 6 },
  stat:         { fontSize: 11, color: "#94a3b8", background: "#f8fafc", padding: "2px 8px", borderRadius: 10 },
  contentArea:  { flex: 1, overflowY: "auto", padding: "0 16px 16px" },
  markdownBody: { paddingTop: 12, fontSize: 13, color: "#334155", lineHeight: 1.8 },
  rawContent:   { marginTop: 12, flex: 1, fontSize: 12, lineHeight: 1.7, color: "#334155", background: "#f8fafc", borderRadius: 8, padding: 14, overflowY: "auto", whiteSpace: "pre-wrap", wordBreak: "break-word", margin: 0, fontFamily: "monospace" },
  previewWrapper: { display: "flex", height: 520, overflow: "hidden" },
  previewSidebar: { width: 200, flexShrink: 0, borderRight: "1px solid #f1f5f9", padding: "16px 14px", background: "#f8fafc", overflowY: "auto" },
  sidebarTitle:   { fontSize: 11, fontWeight: 700, color: "#94a3b8", letterSpacing: "0.06em", textTransform: "uppercase", margin: "0 0 12px" },
  statCard:  { display: "flex", alignItems: "center", gap: 8, padding: "6px 0", borderBottom: "1px solid #f1f5f9" },
  statIcon:  { fontSize: 16, lineHeight: 1, flexShrink: 0 },
  statInfo:  { display: "flex", flexDirection: "column", gap: 1 },
  statLabel: { fontSize: 10, color: "#94a3b8" },
  statValue: { fontSize: 12, fontWeight: 700 },
  sidebarDivider: { height: 1, background: "#e2e8f0", margin: "10px 0" },
  previewMain:    { flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" },
  previewHeader:  { display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 16px", borderBottom: "1px solid #f1f5f9", flexShrink: 0 },
  previewHeaderTitle: { fontSize: 12, fontWeight: 600, color: "#475569" },
  previewContent: { flex: 1, overflowY: "auto", padding: "0 20px 20px" },
};

const markdownStyles: Record<string, React.CSSProperties> = {
  h1: { fontSize: 20, fontWeight: 700, color: "#1e293b", borderBottom: "2px solid #e2e8f0", paddingBottom: 6, marginBottom: 12, marginTop: 16 },
  h2: { fontSize: 16, fontWeight: 700, color: "#1e293b", borderBottom: "1px solid #f1f5f9", paddingBottom: 4, marginBottom: 10, marginTop: 14 },
  h3: { fontSize: 14, fontWeight: 600, color: "#334155", marginBottom: 8, marginTop: 12 },
  p:  { marginBottom: 8, marginTop: 0, lineHeight: 1.8 },
  table: { borderCollapse: "collapse", width: "100%", marginBottom: 12, fontSize: 12 },
  thead: { background: "#f8fafc" },
  th: { border: "1px solid #e2e8f0", padding: "6px 10px", textAlign: "left", fontWeight: 600, color: "#1e293b", fontSize: 12 },
  td: { border: "1px solid #e2e8f0", padding: "5px 10px", color: "#374151", fontSize: 12 },
  tr: { borderBottom: "1px solid #f1f5f9" },
  pre: { background: "#f8fafc", borderRadius: 6, padding: "10px 14px", overflowX: "auto", marginBottom: 10 },
  code: { background: "#f1f5f9", borderRadius: 3, padding: "1px 5px", fontSize: 12, fontFamily: "monospace" },
  ul: { paddingLeft: 20, marginBottom: 8 },
  ol: { paddingLeft: 20, marginBottom: 8 },
  li: { marginBottom: 3, lineHeight: 1.7 },
  blockquote: { borderLeft: "3px solid #6366f1", paddingLeft: 12, color: "#64748b", fontStyle: "italic", margin: "8px 0" },
  hr: { border: "none", borderTop: "1px solid #e2e8f0", margin: "12px 0" },
};
