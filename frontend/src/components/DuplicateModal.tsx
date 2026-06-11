import type { ExistingDocInfo } from "../lib/kmsApi";

interface IdenticalProps {
  type: "identical";
  existingDoc: ExistingDocInfo;
  onKeepExisting: () => void;
  onReupload: () => void;
  onCancel: () => void;
}

interface ModifiedProps {
  type: "modified";
  existingDoc: ExistingDocInfo;
  onKeepExisting: () => void;
  onReplace: () => void;
  onAddNew: () => void;
  onCancel: () => void;
}

type DuplicateModalProps = IdenticalProps | ModifiedProps;

const OVERLAY: React.CSSProperties = {
  position: "fixed", inset: 0, background: "rgba(0,0,0,0.45)",
  display: "flex", alignItems: "center", justifyContent: "center", zIndex: 9999,
};

const MODAL: React.CSSProperties = {
  background: "#fff", borderRadius: 14, padding: "28px 32px",
  width: 440, maxWidth: "90vw",
  boxShadow: "0 8px 40px rgba(0,0,0,0.18)",
};

const BTN_BASE: React.CSSProperties = {
  padding: "9px 18px", borderRadius: 8, fontSize: 14, fontWeight: 600,
  cursor: "pointer", border: "none", flex: 1,
};

export function DuplicateModal(props: DuplicateModalProps) {
  const { existingDoc, onCancel } = props;

  const formattedDate = existingDoc.created_at
    ? new Date(existingDoc.created_at).toLocaleDateString("ko-KR")
    : null;

  return (
    <div style={OVERLAY}>
      <div style={MODAL}>
        {props.type === "identical" ? (
          <>
            <div style={{ fontSize: 20, marginBottom: 4 }}>⚠️ 중복 파일 감지</div>
            <p style={{ fontSize: 14, color: "#475569", margin: "0 0 16px" }}>
              이미 동일한 파일이 KMS에 저장되어 있습니다.
            </p>
            <div style={{ background: "#f8fafc", borderRadius: 8, padding: "10px 14px", marginBottom: 20, fontSize: 13 }}>
              <div style={{ fontWeight: 600, color: "#1e293b", marginBottom: 4 }}>
                {existingDoc.original_filename ?? "알 수 없음"}
              </div>
              <div style={{ color: "#64748b" }}>
                상태: {existingDoc.upload_status ?? "-"}
                {formattedDate && ` · ${formattedDate}`}
              </div>
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button
                style={{ ...BTN_BASE, background: "#6366f1", color: "#fff" }}
                onClick={props.onKeepExisting}
              >
                기존 문서 보기
              </button>
              <button
                style={{ ...BTN_BASE, background: "#f1f5f9", color: "#475569" }}
                onClick={props.onReupload}
              >
                그래도 재업로드
              </button>
              <button
                style={{ ...BTN_BASE, flex: "0 0 auto", background: "transparent", color: "#94a3b8" }}
                onClick={onCancel}
              >
                취소
              </button>
            </div>
          </>
        ) : (
          <>
            <div style={{ fontSize: 20, marginBottom: 4 }}>🔄 수정본 감지</div>
            <p style={{ fontSize: 14, color: "#475569", margin: "0 0 16px" }}>
              같은 파일명이지만 수정된 내용이 감지되었습니다.
            </p>
            <div style={{ background: "#f8fafc", borderRadius: 8, padding: "10px 14px", marginBottom: 20, fontSize: 13 }}>
              <div style={{ fontWeight: 600, color: "#1e293b", marginBottom: 4 }}>
                기존: {existingDoc.original_filename ?? "알 수 없음"}
              </div>
              <div style={{ color: "#64748b" }}>
                상태: {existingDoc.upload_status ?? "-"}
                {formattedDate && ` · ${formattedDate}`}
              </div>
            </div>
            <div style={{ display: "flex", gap: 10 }}>
              <button
                style={{ ...BTN_BASE, background: "#ef4444", color: "#fff" }}
                onClick={props.onReplace}
              >
                기존 버전 교체
              </button>
              <button
                style={{ ...BTN_BASE, background: "#6366f1", color: "#fff" }}
                onClick={props.onAddNew}
              >
                새 버전으로 추가
              </button>
              <button
                style={{ ...BTN_BASE, flex: "0 0 auto", background: "transparent", color: "#94a3b8" }}
                onClick={onCancel}
              >
                취소
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
