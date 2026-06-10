import { useCallback, useEffect, useState, type CSSProperties, type ReactNode } from "react";
import { DocumentUpload } from "../../components/DocumentUpload";
import { HitlQueue } from "../../components/HitlQueue";
import { getDocDetails, listDocuments } from "../../lib/kmsApi";
import type { AgentTraceItem, ChunkItem, DocDetailsResponse, DocListItem } from "../../types/kms";

type Tab = "upload" | "hitl" | "stored";
type DetailTab = "info" | "chunks" | "traces";

const STATUS_LABEL: Record<string, string> = {
  stored:         "저장 완료",
  stored_partial: "저장 완료 (Neo4j 부분 실패)",
};
const STATUS_COLOR: Record<string, string> = {
  stored:         "#22c55e",
  stored_partial: "#84cc16",
};

// ── KPI Card ──────────────────────────────────────────────────────────────────
function KpiCard({
  label, value, sub, color = "#6366f1", loading,
}: {
  label: string; value: number | string; sub?: string; color?: string; loading?: boolean;
}) {
  return (
    <div style={{
      flex: 1, minWidth: 0, padding: "14px 18px", borderRadius: 10,
      background: "#fff", border: "1px solid #e2e8f0",
      boxShadow: "0 1px 4px rgba(0,0,0,0.04)",
    }}>
      <div style={{ fontSize: 11, color: "#64748b", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", marginBottom: 6 }}>
        {label}
      </div>
      <div style={{ fontSize: 26, fontWeight: 700, color: loading ? "#e2e8f0" : color, lineHeight: 1 }}>
        {loading ? "—" : value}
      </div>
      {sub && <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 4 }}>{sub}</div>}
    </div>
  );
}

// ── Tab Button ────────────────────────────────────────────────────────────────
function TabBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "10px 20px", fontSize: 14,
        fontWeight: active ? 700 : 500,
        color: active ? "#6366f1" : "#64748b",
        background: "none", border: "none",
        borderBottom: active ? "2px solid #6366f1" : "2px solid transparent",
        marginBottom: -2, cursor: "pointer", transition: "all 0.15s", whiteSpace: "nowrap",
      }}
    >
      {children}
    </button>
  );
}

// ── Right-panel sub-components ────────────────────────────────────────────────
function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={{ display: "flex", gap: 10, marginBottom: 8 }}>
      <span style={{ fontSize: 11, color: "#64748b", minWidth: 72, paddingTop: 2 }}>{label}</span>
      <span style={{
        fontSize: 12, color: "#334155", wordBreak: "break-all",
        fontFamily: mono ? "monospace" : undefined,
      }}>{value}</span>
    </div>
  );
}

function DocInfoPanel({ doc, details }: { doc: DocListItem; details: DocDetailsResponse | null }) {
  const traceId = details?.agent_traces?.[0]?.trace_id;
  return (
    <div>
      <InfoRow label="Doc ID"  value={doc.doc_id}  mono />
      {traceId         && <InfoRow label="Trace ID" value={traceId} mono />}
      {doc.title       && <InfoRow label="제목"     value={doc.title} />}
      {doc.file_type   && <InfoRow label="형식"     value={doc.file_type.toUpperCase()} />}
      {doc.category    && <InfoRow label="카테고리"  value={doc.category} />}
      {doc.doc_complexity && <InfoRow label="복잡도" value={doc.doc_complexity} />}
      <InfoRow label="Neo4j" value={doc.neo4j_synced == null ? "—" : doc.neo4j_synced ? "✓ 완료" : "✗ 미완료"} />
      <InfoRow label="상태"  value={STATUS_LABEL[doc.status] ?? doc.status} />
      {doc.created_at && <InfoRow label="생성일" value={new Date(doc.created_at).toLocaleString("ko-KR")} />}
      {details && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid #f1f5f9" }}>
          <div style={{ fontSize: 11, fontWeight: 600, color: "#64748b", marginBottom: 6 }}>저장소 경로</div>
          <div style={{ fontSize: 11, color: "#94a3b8", fontFamily: "monospace" }}>
            gcs://kms-bucket/{doc.doc_id}/
          </div>
        </div>
      )}
    </div>
  );
}

function ChunksPanel({ chunks }: { chunks: ChunkItem[] }) {
  if (chunks.length === 0) return (
    <div style={{ color: "#94a3b8", fontSize: 13, textAlign: "center", padding: 24 }}>청크 데이터 없음</div>
  );
  const parents  = chunks.filter(c => c.chunk_type === "parent");
  const children = chunks.filter(c => c.chunk_type === "child");
  return (
    <div>
      <div style={{ fontSize: 12, color: "#64748b", marginBottom: 10 }}>
        Parent {parents.length}개 · Child {children.length}개 · 총 {chunks.length}개
      </div>
      {chunks.map((chunk) => (
        <div key={chunk.chunk_id} style={{
          marginBottom: 8, padding: "10px 12px", borderRadius: 8, fontSize: 12,
          background: chunk.chunk_type === "parent" ? "#f0f9ff" : "#f8fafc",
          border: `1px solid ${chunk.chunk_type === "parent" ? "#bae6fd" : "#e2e8f0"}`,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
            <span style={{ fontWeight: 600, color: chunk.chunk_type === "parent" ? "#0284c7" : "#64748b" }}>
              {chunk.chunk_type === "parent" ? "Parent" : "Child"}
              {chunk.section_header ? ` · ${chunk.section_header}` : ""}
            </span>
            <span style={{ color: "#94a3b8" }}>{chunk.token_count ?? "—"}tok</span>
          </div>
          <div style={{ color: "#374151", lineHeight: 1.5, maxHeight: 72, overflow: "hidden" }}>
            {chunk.content.slice(0, 180)}{chunk.content.length > 180 ? "…" : ""}
          </div>
        </div>
      ))}
    </div>
  );
}

function TracesPanel({ traces }: { traces: AgentTraceItem[] }) {
  if (traces.length === 0) return (
    <div style={{ color: "#94a3b8", fontSize: 13, textAlign: "center", padding: 24 }}>처리 이력 없음</div>
  );
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
      {traces.map((t) => (
        <div key={t.trace_id} style={{
          padding: "10px 12px", borderRadius: 8, background: "#f8fafc",
          border: "1px solid #e2e8f0", fontSize: 12,
        }}>
          <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
            <span style={{ fontWeight: 600, color: "#334155" }}>{t.agent_name}</span>
            <span style={{
              fontSize: 11, fontWeight: 600, color: "#fff",
              background: t.status === "success" ? "#22c55e" : t.status === "fail" ? "#ef4444" : "#f59e0b",
              padding: "1px 7px", borderRadius: 10,
            }}>{t.status}</span>
          </div>
          <div style={{ color: "#94a3b8", fontFamily: "monospace", wordBreak: "break-all", marginBottom: 2 }}>
            {t.trace_id}
          </div>
          {t.execution_ms !== null && (
            <div style={{ color: "#64748b" }}>{t.execution_ms}ms</div>
          )}
          {t.error_message && (
            <div style={{ color: "#ef4444", marginTop: 2 }}>{t.error_message}</div>
          )}
        </div>
      ))}
    </div>
  );
}

// ── StoredDocsList ─────────────────────────────────────────────────────────────
const STORED_PAGE = 20;

function StoredDocsList() {
  const [docs, setDocs]         = useState<DocListItem[]>([]);
  const [total, setTotal]       = useState(0);
  const [offset, setOffset]     = useState(0);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [kpi, setKpi]           = useState({ total: 0, neo4j: 0, partial: 0, loading: true });

  // right panel
  const [selected, setSelected]         = useState<DocListItem | null>(null);
  const [details, setDetails]           = useState<DocDetailsResponse | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailTab, setDetailTab]       = useState<DetailTab>("info");

  const load = useCallback(async (pageOffset = 0) => {
    setLoading(true);
    setError(null);
    try {
      const [storedRes, partialRes] = await Promise.all([
        listDocuments("stored",         STORED_PAGE, pageOffset),
        listDocuments("stored_partial", STORED_PAGE, pageOffset),
      ]);
      const merged = [...storedRes.docs, ...partialRes.docs].sort(
        (a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""),
      );
      setDocs(merged);
      setTotal(storedRes.total + partialRes.total);
      setOffset(pageOffset);
      setKpi({
        total:   storedRes.total + partialRes.total,
        neo4j:   merged.filter(d => d.neo4j_synced === true).length,
        partial: partialRes.total,
        loading: false,
      });
    } catch (e) {
      setError(e instanceof Error ? e.message : "조회 실패");
      setKpi(k => ({ ...k, loading: false }));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(0); }, [load]);

  const handleRowClick = useCallback(async (doc: DocListItem) => {
    setSelected(doc);
    setDetailTab("info");
    if (details?.doc_id === doc.doc_id) return;
    setDetails(null);
    setDetailLoading(true);
    try {
      const d = await getDocDetails(doc.doc_id);
      setDetails(d);
    } catch {
      setDetails(null);
    } finally {
      setDetailLoading(false);
    }
  }, [details]);

  const hasPrev = offset > 0;
  const hasNext = offset + STORED_PAGE < total;

  const DETAIL_TABS: { key: DetailTab; label: string }[] = [
    { key: "info",   label: "기본 정보" },
    { key: "chunks", label: "Chunk" },
    { key: "traces", label: "처리 이력" },
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* KPI Row */}
      <div style={{ display: "flex", gap: 12 }}>
        <KpiCard label="전체 문서"     value={kpi.total}   color="#6366f1" loading={kpi.loading} />
        <KpiCard label="Neo4j 완료"   value={kpi.neo4j}   sub="현재 페이지 기준" color="#22c55e" loading={kpi.loading} />
        <KpiCard label="pgVector 완료" value={kpi.total}   sub="전체 적재" color="#3b82f6" loading={kpi.loading} />
        <KpiCard label="부분 적재"     value={kpi.partial} sub="Neo4j 미반영"  color="#f59e0b" loading={kpi.loading} />
      </div>

      {error && (
        <div style={{ padding: "10px 14px", borderRadius: 8, background: "#fef2f2", border: "1px solid #fca5a5", color: "#dc2626", fontSize: 14 }}>
          ⚠️ {error}
        </div>
      )}

      {/* Split: table + detail panel */}
      <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>
        {/* Table */}
        <div style={{
          flex: 1, minWidth: 0, background: "#fff", borderRadius: 12,
          border: "1px solid #e2e8f0", overflow: "hidden",
        }}>
          {/* Table header */}
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "14px 16px", borderBottom: "1px solid #f1f5f9" }}>
            <span style={{ fontSize: 14, fontWeight: 700, color: "#1e293b" }}>적재 완료 문서</span>
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span style={{ fontSize: 12, color: "#94a3b8" }}>총 {total}건</span>
              <button onClick={() => void load(offset)} style={btnSt.refresh} disabled={loading}>↻</button>
            </div>
          </div>

          {/* Table body */}
          {loading && docs.length === 0 ? (
            <div style={{ padding: 48, textAlign: "center", color: "#94a3b8", fontSize: 13 }}>불러오는 중...</div>
          ) : docs.length === 0 ? (
            <div style={{ padding: 48, textAlign: "center", color: "#94a3b8", fontSize: 13 }}>적재 완료 문서가 없습니다.</div>
          ) : (
            <div style={{ overflowX: "auto" }}>
              <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                <thead>
                  <tr style={{ background: "#f8fafc" }}>
                    {["문서명", "형식", "카테고리", "복잡도", "Neo4j", "상태", "생성일"].map((h) => (
                      <th key={h} style={{ padding: "10px 12px", textAlign: "left", borderBottom: "1px solid #e2e8f0", fontWeight: 600, color: "#475569", fontSize: 12, whiteSpace: "nowrap" }}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {docs.map((doc) => {
                    const isSelected = selected?.doc_id === doc.doc_id;
                    return (
                      <tr
                        key={doc.doc_id}
                        onClick={() => void handleRowClick(doc)}
                        style={{
                          borderBottom: "1px solid #f1f5f9",
                          cursor: "pointer",
                          background: isSelected ? "#eff6ff" : "transparent",
                          transition: "background 0.1s",
                        }}
                        onMouseEnter={e => { if (!isSelected) (e.currentTarget as HTMLElement).style.background = "#f8fafc"; }}
                        onMouseLeave={e => { if (!isSelected) (e.currentTarget as HTMLElement).style.background = "transparent"; }}
                      >
                        <td style={{ padding: "10px 12px", color: "#1e293b", maxWidth: 240, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap", fontWeight: 500 }}>
                          {doc.title ?? doc.doc_id.slice(0, 16) + "…"}
                        </td>
                        <td style={{ padding: "10px 12px", color: "#64748b" }}>{doc.file_type ?? "-"}</td>
                        <td style={{ padding: "10px 12px", color: "#475569" }}>{doc.category ?? "-"}</td>
                        <td style={{ padding: "10px 12px" }}>
                          {doc.doc_complexity ? (
                            <span style={{
                              fontSize: 11, fontWeight: 600, color: "#fff",
                              background: doc.doc_complexity === "HIGH" ? "#f59e0b" : "#22c55e",
                              padding: "2px 7px", borderRadius: 10,
                            }}>{doc.doc_complexity}</span>
                          ) : "-"}
                        </td>
                        <td style={{ padding: "10px 12px", fontWeight: 700 }}>
                          <span style={{ color: doc.neo4j_synced === true ? "#22c55e" : "#cbd5e1" }}>
                            {doc.neo4j_synced == null ? "—" : doc.neo4j_synced ? "✓" : "✗"}
                          </span>
                        </td>
                        <td style={{ padding: "10px 12px" }}>
                          <span style={{
                            fontSize: 11, fontWeight: 600, color: "#fff",
                            background: STATUS_COLOR[doc.status] ?? "#94a3b8",
                            padding: "2px 8px", borderRadius: 10, whiteSpace: "nowrap",
                          }}>{STATUS_LABEL[doc.status] ?? doc.status}</span>
                        </td>
                        <td style={{ padding: "10px 12px", color: "#94a3b8", fontSize: 12, whiteSpace: "nowrap" }}>
                          {doc.created_at ? new Date(doc.created_at).toLocaleDateString("ko-KR") : "-"}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Pagination */}
          {total > STORED_PAGE && (
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "10px 16px", borderTop: "1px solid #f1f5f9", fontSize: 13, color: "#64748b" }}>
              <span>총 {total}건</span>
              <div style={{ display: "flex", gap: 6 }}>
                <button onClick={() => void load(offset - STORED_PAGE)} disabled={!hasPrev || loading} style={btnSt.page}>이전</button>
                <button onClick={() => void load(offset + STORED_PAGE)} disabled={!hasNext || loading} style={btnSt.page}>다음</button>
              </div>
            </div>
          )}
        </div>

        {/* Right detail panel */}
        {selected && (
          <div style={{
            width: 380, flexShrink: 0, background: "#fff", borderRadius: 12,
            border: "1px solid #e2e8f0", overflow: "hidden",
            boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
          }}>
            {/* Panel header */}
            <div style={{ padding: "12px 16px", borderBottom: "1px solid #f1f5f9", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
              <span style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>
                {selected.title ?? selected.doc_id.slice(0, 18) + "…"}
              </span>
              <button
                onClick={() => setSelected(null)}
                style={{ background: "none", border: "none", fontSize: 16, cursor: "pointer", color: "#94a3b8", lineHeight: 1 }}
              >✕</button>
            </div>

            {/* Panel tabs */}
            <div style={{ display: "flex", borderBottom: "1px solid #f1f5f9" }}>
              {DETAIL_TABS.map(({ key, label }) => (
                <button
                  key={key}
                  onClick={() => setDetailTab(key)}
                  style={{
                    flex: 1, padding: "8px 4px", fontSize: 12,
                    fontWeight: detailTab === key ? 700 : 500,
                    color: detailTab === key ? "#6366f1" : "#64748b",
                    background: "none", border: "none",
                    borderBottom: detailTab === key ? "2px solid #6366f1" : "2px solid transparent",
                    cursor: "pointer",
                  }}
                >{label}</button>
              ))}
            </div>

            {/* Panel content */}
            <div style={{ padding: 16, maxHeight: 520, overflowY: "auto" }}>
              {detailLoading ? (
                <div style={{ textAlign: "center", color: "#94a3b8", fontSize: 13, padding: 24 }}>불러오는 중...</div>
              ) : detailTab === "info" ? (
                <DocInfoPanel doc={selected} details={details} />
              ) : detailTab === "chunks" ? (
                <ChunksPanel chunks={details?.chunks ?? []} />
              ) : (
                <TracesPanel traces={details?.agent_traces ?? []} />
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

// ── Button styles ──────────────────────────────────────────────────────────────
const btnSt = {
  refresh: {
    padding: "4px 10px", fontSize: 14, borderRadius: 6,
    border: "1px solid #e2e8f0", background: "#f8fafc",
    color: "#475569", cursor: "pointer",
  } as React.CSSProperties,
  page: {
    padding: "5px 12px", fontSize: 12, borderRadius: 6,
    border: "1px solid #e2e8f0", background: "#fff",
    color: "#475569", cursor: "pointer",
  } as React.CSSProperties,
};

// ── Main Page ──────────────────────────────────────────────────────────────────
export default function KmsManagePage() {
  const [tab, setTab] = useState<Tab>("upload");

  return (
    <div style={{ background: "#f8fafc", minHeight: "100%" }}>
      {/* Tab bar */}
      <div style={{
        display: "flex", gap: 0,
        borderBottom: "2px solid #e2e8f0",
        background: "#fff",
        padding: "0 24px",
        position: "sticky", top: 0, zIndex: 10,
      }}>
        <TabBtn active={tab === "upload"} onClick={() => setTab("upload")}>📄 문서 업로드</TabBtn>
        <TabBtn active={tab === "hitl"}   onClick={() => setTab("hitl")}>🔍 HITL 검토</TabBtn>
        <TabBtn active={tab === "stored"} onClick={() => setTab("stored")}>✅ 적재 완료 문서</TabBtn>
      </div>

      {/* Content */}
      <div style={{ padding: "20px 24px" }}>
        {tab === "upload" && <DocumentUpload isVisible={tab === "upload"} />}
        {tab === "hitl"   && <HitlQueue />}
        {tab === "stored" && <StoredDocsList />}
      </div>
    </div>
  );
}
