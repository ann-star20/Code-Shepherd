import { useCallback, useEffect, useState } from "react";
import { DocumentUpload } from "../../components/DocumentUpload";
import { HitlQueue } from "../../components/HitlQueue";
import { listDocuments } from "../../lib/kmsApi";
import type { DocListItem } from "../../types/kms";

type Tab = "upload" | "hitl" | "stored";

const STATUS_LABEL: Record<string, string> = {
  stored:         "저장 완료",
  stored_partial: "저장 완료 (Neo4j 부분 실패)",
};

const STATUS_COLOR: Record<string, string> = {
  stored:         "#22c55e",
  stored_partial: "#84cc16",
};

function StoredDocsList() {
  const [docs, setDocs]       = useState<DocListItem[]>([]);
  const [total, setTotal]     = useState(0);
  const [offset, setOffset]   = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const PAGE = 20;

  const load = useCallback(async (pageOffset = 0) => {
    setLoading(true);
    setError(null);
    try {
      const [storedRes, partialRes] = await Promise.all([
        listDocuments("stored", PAGE, pageOffset),
        listDocuments("stored_partial", PAGE, pageOffset),
      ]);
      const merged = [...storedRes.docs, ...partialRes.docs].sort(
        (a, b) => (b.created_at ?? "").localeCompare(a.created_at ?? ""),
      );
      setDocs(merged);
      setTotal(storedRes.total + partialRes.total);
      setOffset(pageOffset);
    } catch (e) {
      setError(e instanceof Error ? e.message : "조회 실패");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(0); }, [load]);

  const hasPrev = offset > 0;
  const hasNext = offset + PAGE < total;

  return (
    <div style={{ maxWidth: 900, margin: "0 auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
        <h2 style={{ margin: 0, fontSize: 18, fontWeight: 700 }}>적재 완료 문서</h2>
        <button onClick={() => void load(offset)} style={btn.refresh} disabled={loading}>
          {loading ? "로딩..." : "새로고침"}
        </button>
      </div>

      {error && (
        <div style={{ padding: "10px 14px", borderRadius: 8, background: "#fef2f2", border: "1px solid #fca5a5", color: "#dc2626", marginBottom: 12, fontSize: 14 }}>
          ⚠️ {error}
        </div>
      )}

      {loading && docs.length === 0 ? (
        <p style={{ color: "#94a3b8", textAlign: "center", padding: 40 }}>불러오는 중...</p>
      ) : docs.length === 0 ? (
        <p style={{ color: "#94a3b8", textAlign: "center", padding: 40 }}>적재 완료 문서가 없습니다.</p>
      ) : (
        <>
          <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
            <thead>
              <tr style={{ background: "#f8fafc" }}>
                {["제목", "형식", "상태", "생성일"].map((h) => (
                  <th key={h} style={{ padding: "10px 12px", textAlign: "left", borderBottom: "1px solid #e2e8f0", fontWeight: 600, color: "#475569" }}>{h}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {docs.map((doc) => (
                <tr key={doc.doc_id} style={{ borderBottom: "1px solid #f1f5f9" }}>
                  <td style={{ padding: "10px 12px", color: "#1e293b", maxWidth: 320, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                    {doc.title ?? doc.doc_id}
                  </td>
                  <td style={{ padding: "10px 12px", color: "#64748b" }}>{doc.file_type ?? "-"}</td>
                  <td style={{ padding: "10px 12px" }}>
                    <span style={{ fontSize: 11, fontWeight: 600, color: "#fff", background: STATUS_COLOR[doc.status] ?? "#94a3b8", padding: "2px 8px", borderRadius: 12 }}>
                      {STATUS_LABEL[doc.status] ?? doc.status}
                    </span>
                  </td>
                  <td style={{ padding: "10px 12px", color: "#94a3b8", fontSize: 12 }}>
                    {doc.created_at ? new Date(doc.created_at).toLocaleDateString("ko-KR") : "-"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginTop: 16, fontSize: 13, color: "#64748b" }}>
            <span>총 {total}건</span>
            <div style={{ display: "flex", gap: 8 }}>
              <button onClick={() => void load(offset - PAGE)} disabled={!hasPrev || loading} style={btn.page}>이전</button>
              <button onClick={() => void load(offset + PAGE)} disabled={!hasNext || loading} style={btn.page}>다음</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}

const btn = {
  refresh: {
    padding: "6px 14px", fontSize: 12, borderRadius: 6,
    border: "1px solid #e2e8f0", background: "#f8fafc",
    color: "#475569", cursor: "pointer",
  } as React.CSSProperties,
  page: {
    padding: "5px 12px", fontSize: 12, borderRadius: 6,
    border: "1px solid #e2e8f0", background: "#fff",
    color: "#475569", cursor: "pointer",
  } as React.CSSProperties,
};

function TabBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "10px 20px",
        fontSize: 14,
        fontWeight: active ? 700 : 500,
        color: active ? "#6366f1" : "#64748b",
        background: "none",
        border: "none",
        borderBottom: active ? "2px solid #6366f1" : "2px solid transparent",
        marginBottom: -2,
        cursor: "pointer",
        transition: "all 0.15s",
      }}
    >
      {children}
    </button>
  );
}

export default function KmsManagePage() {
  const [tab, setTab] = useState<Tab>("upload");

  return (
    <div style={{ padding: "24px 32px" }}>
      <div style={{ display: "flex", gap: 0, marginBottom: 24, borderBottom: "2px solid #f1f5f9" }}>
        <TabBtn active={tab === "upload"} onClick={() => setTab("upload")}>📄 문서 업로드</TabBtn>
        <TabBtn active={tab === "hitl"}   onClick={() => setTab("hitl")}>🔍 HITL 검토</TabBtn>
        <TabBtn active={tab === "stored"} onClick={() => setTab("stored")}>✅ 적재 완료 문서</TabBtn>
      </div>

      {tab === "upload" && <DocumentUpload isVisible={tab === "upload"} />}
      {tab === "hitl"   && <HitlQueue />}
      {tab === "stored" && <StoredDocsList />}
    </div>
  );
}
