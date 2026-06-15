import React from "react";

interface Props {
  isOpen: boolean;
  docTitle: string;
  onConfirm: () => void;
  onCancel: () => void;
  loading?: boolean;
}

export function DeleteConfirmModal({ isOpen, docTitle, onConfirm, onCancel, loading }: Props) {
  if (!isOpen) return null;

  return (
    <div style={{
      position: "fixed", inset: 0, zIndex: 1000,
      background: "rgba(0,0,0,0.45)",
      display: "flex", alignItems: "center", justifyContent: "center",
    }}>
      <div style={{
        background: "#fff", borderRadius: 12, padding: "28px 32px",
        width: 420, boxShadow: "0 8px 32px rgba(0,0,0,0.18)",
        display: "flex", flexDirection: "column", gap: 16,
      }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <span style={{ fontSize: 22 }}>🗑️</span>
          <span style={{ fontSize: 16, fontWeight: 700, color: "#1e293b" }}>문서 삭제</span>
        </div>

        <div style={{ fontSize: 14, color: "#475569", lineHeight: 1.6 }}>
          <strong style={{ color: "#1e293b" }}>{docTitle}</strong> 문서를 삭제하시겠습니까?
        </div>

        <div style={{
          padding: "10px 14px", borderRadius: 8,
          background: "#fef2f2", border: "1px solid #fca5a5",
          fontSize: 12, color: "#b91c1c", lineHeight: 1.6,
        }}>
          이 작업은 되돌릴 수 없습니다. PostgreSQL, pgVector, Neo4j, GCS 4개 저장소에서 영구 삭제됩니다.
        </div>

        <div style={{ display: "flex", gap: 8, justifyContent: "flex-end", marginTop: 4 }}>
          <button
            onClick={onCancel}
            disabled={loading}
            style={{
              padding: "8px 20px", borderRadius: 8, fontSize: 14, fontWeight: 500,
              border: "1px solid #e2e8f0", background: "#f8fafc",
              color: "#475569", cursor: loading ? "not-allowed" : "pointer",
            }}
          >취소</button>
          <button
            onClick={onConfirm}
            disabled={loading}
            style={{
              padding: "8px 20px", borderRadius: 8, fontSize: 14, fontWeight: 600,
              border: "none", background: loading ? "#fca5a5" : "#ef4444",
              color: "#fff", cursor: loading ? "not-allowed" : "pointer",
              minWidth: 72,
            }}
          >{loading ? "삭제 중..." : "삭제"}</button>
        </div>
      </div>
    </div>
  );
}
