import { useCallback, useEffect, useRef, useState } from "react";
import { getDocDetails, uploadDocument } from "../api/kmsApi";
import { TERMINAL_STATUSES, useUploadStatus } from "../hooks/useUploadStatus";
import type { DocDetailsResponse, UploadResponse } from "../types/kms";
import { PipelineFlow } from "./PipelineFlow";
import { DocumentAnalyzer } from "./DocumentAnalyzer";

const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".pptx", ".txt", ".md"];
const ACCEPTED_MIME = ACCEPTED_EXTENSIONS.join(",");

const STATUS_LABEL: Record<string, string> = {
  processing:      "처리 중...",
  stored:          "저장 완료",
  stored_partial:  "저장 완료 (Neo4j 부분 실패)",
  hitl_pending:    "수동 검토 대기 중",
  approved:        "검토 승인됨 — 재처리 준비 중",
  reprocessing:    "재처리 중...",
  rejected:        "거부됨",
  failed:          "처리 실패",
};

const STATUS_COLOR: Record<string, string> = {
  processing:      "#f59e0b",
  stored:          "#22c55e",
  stored_partial:  "#84cc16",
  hitl_pending:    "#3b82f6",
  approved:        "#8b5cf6",
  reprocessing:    "#f59e0b",
  rejected:        "#6b7280",
  failed:          "#ef4444",
};

const SESSION_KEY = "kms_upload_result";


export function DocumentUpload({ isVisible = true }: { isVisible?: boolean }) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver]           = useState(false);
  const [uploading, setUploading]         = useState(false);
  const [uploadError, setUploadError]     = useState<string | null>(null);
  const [uploadResult, setUploadResult]   = useState<UploadResponse | null>(() => {
    // 새로고침 후에도 마지막 추적 문서를 복원
    try {
      const saved = sessionStorage.getItem(SESSION_KEY);
      return saved ? JSON.parse(saved) : null;
    } catch {
      return null;
    }
  });
  const [docDetails, setDocDetails]       = useState<DocDetailsResponse | null>(null);
  const [detailsError, setDetailsError]   = useState<string | null>(null);
  const [showDetails, setShowDetails]     = useState(false);
  const [pollKey, setPollKey]             = useState(0);
  const currentStatusRef = useRef<string | undefined>(undefined);

  // 탭으로 돌아올 때 미완료 상태이면 폴링 재시작
  useEffect(() => {
    if (isVisible && uploadResult?.doc_id) {
      if (!TERMINAL_STATUSES.has(currentStatusRef.current ?? "")) {
        setPollKey((k) => k + 1);
      }
    }
  }, [isVisible]); // eslint-disable-line react-hooks/exhaustive-deps

  // uploadResult 변경 시 sessionStorage 동기화
  useEffect(() => {
    if (uploadResult) {
      sessionStorage.setItem(SESSION_KEY, JSON.stringify(uploadResult));
    } else {
      sessionStorage.removeItem(SESSION_KEY);
    }
  }, [uploadResult]);

  const { status, error: statusError } = useUploadStatus(uploadResult?.doc_id ?? null, pollKey);

  const currentStatus = status?.status ?? uploadResult?.status;
  currentStatusRef.current = currentStatus;
  const statusColor   = currentStatus ? STATUS_COLOR[currentStatus] : undefined;
  const statusLabel   = currentStatus ? STATUS_LABEL[currentStatus] : undefined;
  const isTerminal = Boolean(currentStatus && TERMINAL_STATUSES.has(currentStatus));

  // 파이프라인 종료 후 agent_traces 상세를 가져온다.
  // 백엔드 수정으로 ainvoke 반환 후 upload_status 가 설정되므로
  // 이 시점에는 모든 harness 트레이스가 이미 기록된 상태 → 즉시 조회 가능.
  useEffect(() => {
    if (!isTerminal || !uploadResult?.doc_id || docDetails) return;
    setDetailsError(null);
    const timer = setTimeout(() => {
      getDocDetails(uploadResult.doc_id)
        .then((d) => {
          setDocDetails(d);
          setShowDetails(true);
        })
        .catch((e) => {
          setDetailsError(e instanceof Error ? e.message : "상세 조회 실패");
        });
    }, 300);
    return () => clearTimeout(timer);
  }, [isTerminal, uploadResult?.doc_id, docDetails]);

  const handleFile = useCallback(async (file: File) => {
    const ext = "." + file.name.split(".").pop()?.toLowerCase();
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      setUploadError(`지원하지 않는 형식입니다. 지원 형식: ${ACCEPTED_EXTENSIONS.join(", ")}`);
      return;
    }

    setUploadError(null);
    setUploadResult(null);
    setDocDetails(null);
    setShowDetails(false);
    setUploading(true);

    try {
      const result = await uploadDocument(file);
      setUploadResult(result);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "업로드 중 오류 발생");
    } finally {
      setUploading(false);
    }
  }, []);

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) handleFile(file);
    e.target.value = "";
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  };

  // 파이프라인 표시용 traces
  // docDetails 가 로드됐으면 (1개 이상 trace) 항상 docDetails 우선 사용.
  // 폴링 스냅샷은 race condition 으로 불완전할 수 있으므로 fallback 으로만 사용.
  const liveTraces =
    docDetails && docDetails.agent_traces.length > 0
      ? docDetails.agent_traces
      : status?.agent_traces ?? [];
  // approved → reprocessing → stored 전환 중 모두 진행 중으로 표시
  const isProcessing = uploading || currentStatus === "processing" || currentStatus === "reprocessing" || currentStatus === "approved";

  return (
    <div style={{ maxWidth: 960, margin: "40px auto" }}>

      {/* --- 업로드 카드 --- */}
      <div style={styles.card}>
        <h2 style={styles.title}>사내 문서 업로드</h2>
        <p style={styles.sub}>PDF · DOCX · PPTX · TXT · MD를 KMS 파이프라인으로 처리합니다.</p>

        {/* 드래그 앤 드롭 영역 */}
        <div
          style={{
            ...styles.dropZone,
            borderColor: dragOver ? "#6366f1" : "#d1d5db",
            background:  dragOver ? "#eef2ff"  : "#f9fafb",
          }}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => fileInputRef.current?.click()}
          role="button"
          tabIndex={0}
          onKeyDown={(e) => e.key === "Enter" && fileInputRef.current?.click()}
        >
          <span style={styles.dropIcon}>📄</span>
          <p style={styles.dropText}>
            {uploading ? "업로드 중..." : "파일을 드래그하거나 클릭하여 선택"}
          </p>
          <p style={styles.dropHint}>{ACCEPTED_EXTENSIONS.join(" · ")}</p>
          <input
            ref={fileInputRef}
            type="file"
            accept={ACCEPTED_MIME}
            onChange={onFileChange}
            style={{ display: "none" }}
            disabled={uploading}
          />
        </div>

        {/* 업로드 에러 */}
        {uploadError && (
          <div style={{ ...styles.banner, background: "#fef2f2", borderColor: "#fca5a5", color: "#dc2626" }}>
            ⚠️ {uploadError}
          </div>
        )}

        {/* 처리 상태 */}
        {uploadResult && (
          <div style={styles.statusBox}>
            <div style={styles.statusRow}>
              <span style={styles.label}>문서 ID</span>
              <code style={styles.code}>{uploadResult.doc_id}</code>
            </div>

            <div style={styles.statusRow}>
              <span style={styles.label}>상태</span>
              <span style={{ ...styles.badge, background: statusColor }}>
                {statusLabel ?? currentStatus}
              </span>
            </div>

            {/* 처리 중 진행 표시 */}
            {currentStatus === "processing" && (
              <div style={styles.progressBar}>
                <div style={styles.progressFill} />
              </div>
            )}

            {/* 완료 상세 */}
            {isTerminal && (
              <div style={styles.detailBox}>
                {currentStatus === "stored" && (
                  <p style={{ color: "#166534" }}>
                    ✅ DB에 저장 완료.
                  </p>
                )}
                {currentStatus === "stored_partial" && (
                  <p style={{ color: "#3f6212" }}>
                    ✅ PostgreSQL/pgVector 저장 완료 (Neo4j 연결 실패 — 관계 그래프 미반영)
                  </p>
                )}
                {currentStatus === "hitl_pending" && (
                  <p style={{ color: "#1e40af" }}>
                    🔵 문서 품질이 기준 미달입니다. <strong>HITL 검토 큐</strong>에서 승인하면 파이프라인이 자동으로 재개됩니다.
                  </p>
                )}
                {currentStatus === "approved" && (
                  <p style={{ color: "#6d28d9" }}>
                    ✅ 검토 승인됨. 재처리 시작 중...
                  </p>
                )}
                {currentStatus === "reprocessing" && (
                  <p style={{ color: "#92400e" }}>
                    🔄 재처리 중입니다. 파이프라인이 진행 중이에요.
                  </p>
                )}
                {currentStatus === "rejected" && (
                  <p style={{ color: "#4b5563" }}>
                    ⛔ 거부된 문서입니다. 새 파일을 업로드하세요.
                  </p>
                )}
                {currentStatus === "failed" && (
                  <p style={{ color: "#991b1b" }}>
                    ❌ 처리 실패: {status?.error ?? "알 수 없는 오류"}
                  </p>
                )}

                {/* 상세 패널 토글 */}
                {docDetails && (
                  <button
                    style={{ ...styles.detailToggle, marginTop: 10 }}
                    onClick={() => setShowDetails((v) => !v)}
                  >
                    {showDetails ? "▲ 청크 분석 닫기" : "▼ 청크 분석 보기"}
                  </button>
                )}
                {detailsError && (
                  <p style={{ color: "#92400e", fontSize: 12, marginTop: 6 }}>
                    상세 조회 실패: {detailsError}
                  </p>
                )}
              </div>
            )}
          </div>
        )}

        {statusError && (
          <div style={{ ...styles.banner, background: "#fff7ed", borderColor: "#fdba74", color: "#9a3412" }}>
            상태 조회 오류: {statusError}
          </div>
        )}
      </div>

      {/* --- 파이프라인 흐름 (항시 표시 — 업로드 전: 전체 대기, 처리 중: 실시간, 완료: 결과) --- */}
      <div style={{ padding: "0 0 8px" }}>
        <PipelineFlow traces={liveTraces} isProcessing={isProcessing} />
      </div>

      {/* --- 청크 분석 (완료 후만 표시) --- */}
      {showDetails && docDetails && (
        <div style={{ padding: "0 0 40px" }}>
          {docDetails.chunks.length > 0 && (
            <DocumentAnalyzer chunks={docDetails.chunks} />
          )}
          {docDetails.chunks.length === 0 && (
            <div style={styles.emptyChunks}>청크 데이터가 없습니다.</div>
          )}
        </div>
      )}
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  card: {
    padding: 32,
    borderRadius: 12,
    boxShadow: "0 2px 16px rgba(0,0,0,0.08)",
    fontFamily: "system-ui, sans-serif",
    background: "#fff",
  },
  title: { margin: "0 0 4px", fontSize: 20, fontWeight: 700 },
  sub: { margin: "0 0 20px", fontSize: 14, color: "#6b7280" },
  dropZone: {
    border: "2px dashed",
    borderRadius: 10,
    padding: "32px 16px",
    textAlign: "center",
    cursor: "pointer",
    transition: "all 0.2s",
    userSelect: "none",
  },
  dropIcon: { fontSize: 36 },
  dropText:  { margin: "8px 0 4px", fontSize: 15, fontWeight: 500, color: "#374151" },
  dropHint:  { margin: 0, fontSize: 12, color: "#9ca3af" },
  banner: {
    marginTop: 16,
    padding: "10px 14px",
    borderRadius: 8,
    border: "1px solid",
    fontSize: 14,
  },
  statusBox: {
    marginTop: 20,
    padding: 16,
    borderRadius: 8,
    background: "#f8fafc",
    border: "1px solid #e2e8f0",
  },
  statusRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    marginBottom: 10,
  },
  label: { fontSize: 12, color: "#64748b", minWidth: 64 },
  code: {
    fontSize: 11,
    background: "#f1f5f9",
    padding: "2px 6px",
    borderRadius: 4,
    color: "#475569",
    wordBreak: "break-all",
  },
  badge: {
    fontSize: 12,
    fontWeight: 600,
    color: "#fff",
    padding: "3px 10px",
    borderRadius: 20,
  },
  progressBar: {
    height: 4,
    background: "#e5e7eb",
    borderRadius: 2,
    overflow: "hidden",
    marginBottom: 10,
  },
  progressFill: {
    height: "100%",
    width: "40%",
    background: "#f59e0b",
    borderRadius: 2,
    animation: "slide 1.5s infinite",
  },
  detailBox: {
    marginTop: 8,
    padding: "10px 12px",
    background: "#fff",
    borderRadius: 6,
    border: "1px solid #e5e7eb",
    fontSize: 13,
  },
  detailToggle: {
    display: "block",
    background: "#f1f5f9",
    border: "1px solid #e2e8f0",
    borderRadius: 6,
    padding: "6px 14px",
    fontSize: 12,
    fontWeight: 600,
    color: "#475569",
    cursor: "pointer",
    width: "100%",
    textAlign: "left",
  },
  emptyChunks: {
    marginTop: 16,
    padding: 16,
    background: "#fff",
    borderRadius: 10,
    border: "1px solid #e2e8f0",
    fontSize: 13,
    color: "#94a3b8",
    textAlign: "center",
  },
};
