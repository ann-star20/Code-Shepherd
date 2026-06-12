import React, { useRef, useState } from "react";
import { DeleteConfirmModal } from "./DeleteConfirmModal";
import { deleteDocument, replaceDocument } from "../lib/kmsApi";
import type { DocDetailsResponse, DocListItem } from "../types/kms";

const STATUS_LABEL: Record<string, string> = {
  stored:         "저장 완료",
  stored_partial: "저장 완료 (Neo4j 부분 실패)",
};

function qualityColor(score: number | null | undefined): string {
  if (score == null) return "#94a3b8";
  if (score >= 0.8) return "#22c55e";
  if (score >= 0.6) return "#f59e0b";
  return "#ef4444";
}
function qualityLabel(score: number | null | undefined): string {
  if (score == null) return "분석 미완료";
  if (score >= 0.8) return "양호";
  if (score >= 0.6) return "보통";
  return "낮음";
}

function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={{ display: "flex", gap: 10, marginBottom: 8 }}>
      <span style={{ fontSize: 11, color: "#64748b", minWidth: 72, paddingTop: 2 }}>{label}</span>
      <span style={{ fontSize: 12, color: "#334155", wordBreak: "break-all", fontFamily: mono ? "monospace" : undefined }}>
        {value}
      </span>
    </div>
  );
}

interface Props {
  doc: DocListItem;
  details: DocDetailsResponse | null;
  detailLoading: boolean;
  onRefresh: () => void;
}

export function DocStatusPanel({ doc, details, detailLoading, onRefresh }: Props) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [deleteOpen, setDeleteOpen]     = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError]   = useState<string | null>(null);
  const [replaceLoading, setReplaceLoading] = useState(false);
  const [replaceError, setReplaceError] = useState<string | null>(null);

  const score = details?.quality_score ?? null;
  const color = qualityColor(score);

  async function handleDelete() {
    setDeleteLoading(true);
    setDeleteError(null);
    try {
      await deleteDocument(doc.doc_id);
      setDeleteOpen(false);
      onRefresh();
    } catch (e) {
      setDeleteError(e instanceof Error ? e.message : "삭제 실패");
    } finally {
      setDeleteLoading(false);
    }
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    e.target.value = "";
    setReplaceLoading(true);
    setReplaceError(null);
    try {
      await replaceDocument(doc.doc_id, file);
      onRefresh();
    } catch (err) {
      setReplaceError(err instanceof Error ? err.message : "재적재 실패");
    } finally {
      setReplaceLoading(false);
    }
  }

  if (detailLoading) {
    return <div style={{ textAlign: "center", color: "#94a3b8", fontSize: 13, padding: 24 }}>불러오는 중...</div>;
  }

  return (
    <div>
      {/* Quality score card */}
      <div style={{
        padding: "14px 16px", borderRadius: 10, marginBottom: 16,
        background: "#f8fafc", border: `1.5px solid ${color}22`,
        display: "flex", alignItems: "center", gap: 16,
      }}>
        <div style={{
          width: 52, height: 52, borderRadius: "50%",
          border: `3px solid ${color}`,
          display: "flex", alignItems: "center", justifyContent: "center",
          flexShrink: 0,
        }}>
          <span style={{ fontSize: 15, fontWeight: 800, color }}>
            {score != null ? Math.round(score * 100) : "—"}
          </span>
        </div>
        <div>
          <div style={{ fontSize: 11, color: "#64748b", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", marginBottom: 2 }}>
            품질 점수
          </div>
          <div style={{ fontSize: 18, fontWeight: 700, color, lineHeight: 1 }}>
            {qualityLabel(score)}
          </div>
        </div>
      </div>

      {/* Meta */}
      <InfoRow label="Doc ID"   value={doc.doc_id} mono />
      {doc.title        && <InfoRow label="제목"      value={doc.title} />}
      {doc.file_type    && <InfoRow label="형식"      value={doc.file_type.toUpperCase()} />}
      {doc.category     && <InfoRow label="카테고리"  value={doc.category} />}
      {doc.doc_complexity && <InfoRow label="복잡도" value={doc.doc_complexity} />}
      <InfoRow label="Neo4j"  value={doc.neo4j_synced == null ? "—" : doc.neo4j_synced ? "✓ 완료" : "✗ 미완료"} />
      <InfoRow label="상태"   value={STATUS_LABEL[doc.status] ?? doc.status} />
      {doc.created_at   && <InfoRow label="생성일"   value={new Date(doc.created_at).toLocaleString("ko-KR")} />}

      {/* Error banners */}
      {replaceError && (
        <div style={{ padding: "8px 12px", borderRadius: 6, background: "#fef2f2", border: "1px solid #fca5a5", color: "#b91c1c", fontSize: 12, marginTop: 12 }}>
          ⚠️ {replaceError}
        </div>
      )}
      {deleteError && (
        <div style={{ padding: "8px 12px", borderRadius: 6, background: "#fef2f2", border: "1px solid #fca5a5", color: "#b91c1c", fontSize: 12, marginTop: 12 }}>
          ⚠️ {deleteError}
        </div>
      )}

      {/* Action buttons */}
      <div style={{ display: "flex", gap: 8, marginTop: 16 }}>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.hwp,.docx,.txt,.md"
          onChange={handleFileChange}
          style={{ display: "none" }}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={replaceLoading}
          style={{
            flex: 1, padding: "8px 0", borderRadius: 8, fontSize: 13, fontWeight: 600,
            border: "1px solid #6366f1", background: "#f5f3ff",
            color: "#6366f1", cursor: replaceLoading ? "not-allowed" : "pointer",
          }}
        >{replaceLoading ? "처리 중..." : "🔄 재적재"}</button>
        <button
          onClick={() => setDeleteOpen(true)}
          disabled={deleteLoading}
          style={{
            flex: 1, padding: "8px 0", borderRadius: 8, fontSize: 13, fontWeight: 600,
            border: "1px solid #ef4444", background: "#fef2f2",
            color: "#ef4444", cursor: deleteLoading ? "not-allowed" : "pointer",
          }}
        >🗑️ 삭제</button>
      </div>

      <DeleteConfirmModal
        isOpen={deleteOpen}
        docTitle={doc.title ?? doc.doc_id.slice(0, 20) + "…"}
        onConfirm={handleDelete}
        onCancel={() => { setDeleteOpen(false); setDeleteError(null); }}
        loading={deleteLoading}
      />
    </div>
  );
}
