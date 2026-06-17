import { useCallback, useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";
import { getDocDetails, listDocuments, uploadDocument, checkDuplicate, replaceDocument, type CheckDuplicateResult, type ExistingDocInfo } from "../lib/kmsApi";
import { computeFileHash } from "../lib/fileHash";
import { DuplicateModal } from "./DuplicateModal";
import { listHitlQueue } from "../lib/hitlApi";
import { TERMINAL_STATUSES, useUploadStatus } from "../hooks/useUploadStatus";
import type { DocDetailsResponse, UploadResponse } from "../types/kms";
import { PipelineFlow } from "./PipelineFlow";
import { DocumentAnalyzer } from "./DocumentAnalyzer";

// ── KPI data hook ─────────────────────────────────────────────────────────────
interface KpiCounts {
  total: number; processing: number; hitl: number; stored: number; other: number; loading: boolean;
}

function useKpiCounts(refreshKey: number): KpiCounts {
  const [kpi, setKpi] = useState<KpiCounts>({ total: 0, processing: 0, hitl: 0, stored: 0, other: 0, loading: true });

  useEffect(() => {
    let cancelled = false;
    setKpi((k: KpiCounts) => ({ ...k, loading: true }));
    void Promise.allSettled([
      listDocuments(undefined, 1, 0),
      listDocuments("processing", 1, 0),
      listHitlQueue("pending", 1, 0),
      listDocuments("stored", 1, 0),
      listDocuments("stored_partial", 1, 0),
      listDocuments("failed", 1, 0),
      listDocuments("rejected", 1, 0),
    ]).then(([allRes, procRes, hitlRes, storedRes, partialRes, failedRes, rejectedRes]) => {
      if (cancelled) return;
      const total      = allRes.status      === "fulfilled" ? allRes.value.total      : 0;
      const processing = procRes.status     === "fulfilled" ? procRes.value.total     : 0;
      const hitl       = hitlRes.status     === "fulfilled" ? hitlRes.value.total     : 0;
      const stored     = (storedRes.status  === "fulfilled" ? storedRes.value.total   : 0) +
                         (partialRes.status === "fulfilled" ? partialRes.value.total  : 0);
      const failed     = (failedRes.status   === "fulfilled" ? failedRes.value.total   : 0) +
                         (rejectedRes.status === "fulfilled" ? rejectedRes.value.total : 0);
      // 나머지(approved, reprocessing, pending 등)
      const other      = Math.max(0, total - processing - hitl - stored - failed);
      setKpi({ total, processing, hitl, stored, other: failed + other, loading: false });
    });
    return () => { cancelled = true; };
  }, [refreshKey]);

  return kpi;
}

// ── KPI Card ──────────────────────────────────────────────────────────────────
function KpiCard({ label, value, color, loading }: { label: string; value: number; color: string; loading: boolean }) {
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
    </div>
  );
}

// ── Constants ─────────────────────────────────────────────────────────────────
const ACCEPTED_EXTENSIONS = [".pdf", ".docx", ".pptx", ".txt", ".md"];
const ACCEPTED_MIME = ACCEPTED_EXTENSIONS.join(",");
const SESSION_KEY = "kms_upload_result";

const STATUS_LABEL: Record<string, string> = {
  processing:     "처리 중...",
  stored:         "저장 완료",
  stored_partial: "저장 완료 (Neo4j 부분 실패)",
  hitl_pending:   "수동 검토 대기 중",
  approved:       "검토 승인됨 — 재처리 준비 중",
  reprocessing:   "재처리 중...",
  rejected:       "거부됨",
  failed:         "처리 실패",
};
const STATUS_COLOR: Record<string, string> = {
  processing:     "#f59e0b",
  stored:         "#22c55e",
  stored_partial: "#84cc16",
  hitl_pending:   "#3b82f6",
  approved:       "#8b5cf6",
  reprocessing:   "#f59e0b",
  rejected:       "#6b7280",
  failed:         "#ef4444",
};

// ── InfoRow ───────────────────────────────────────────────────────────────────
function InfoRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={{ display: "flex", gap: 8, marginBottom: 6 }}>
      <span style={{ fontSize: 11, color: "#64748b", minWidth: 68 }}>{label}</span>
      <span style={{ fontSize: 12, color: "#334155", wordBreak: "break-all", fontFamily: mono ? "monospace" : undefined }}>
        {value}
      </span>
    </div>
  );
}

// ── DocumentUpload ────────────────────────────────────────────────────────────
export function DocumentUpload({ isVisible = true, onGoToStored }: { isVisible?: boolean; onGoToStored?: (docId: string) => void }) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver]         = useState(false);
  const [uploading, setUploading]       = useState(false);
  const [uploadError, setUploadError]   = useState<string | null>(null);
  const [duplicateState, setDuplicateState] = useState<{
    type: "identical" | "modified";
    existingDoc: ExistingDocInfo;
    pendingFile: File;
    pendingHash: string;
  } | null>(null);
  const [uploadResult, setUploadResult] = useState<UploadResponse | null>(() => {
    try {
      const saved = sessionStorage.getItem(SESSION_KEY);
      return saved ? (JSON.parse(saved) as UploadResponse) : null;
    } catch { return null; }
  });
  const [docDetails, setDocDetails]     = useState<DocDetailsResponse | null>(null);
  const [detailsError, setDetailsError] = useState<string | null>(null);
  const [showChunks, setShowChunks]     = useState(false);
  const [pollKey, setPollKey]           = useState(0);
  const [kpiRefreshKey, setKpiRefreshKey] = useState(0);
  const currentStatusRef = useRef<string | undefined>(undefined);

  const kpi = useKpiCounts(kpiRefreshKey);

  useEffect(() => {
    if (isVisible && uploadResult?.doc_id) {
      if (!TERMINAL_STATUSES.has(currentStatusRef.current ?? "")) {
        setPollKey((k) => k + 1);
      }
    }
  }, [isVisible]); // eslint-disable-line react-hooks/exhaustive-deps

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
  const statusColor = currentStatus ? STATUS_COLOR[currentStatus] : undefined;
  const statusLabel = currentStatus ? STATUS_LABEL[currentStatus] : undefined;
  const isTerminal  = Boolean(currentStatus && TERMINAL_STATUSES.has(currentStatus));

  useEffect(() => {
    if (!isTerminal || !uploadResult?.doc_id || docDetails) return;
    setDetailsError(null);
    const timer = setTimeout(() => {
      getDocDetails(uploadResult.doc_id)
        .then((d) => { setDocDetails(d); })
        .catch((e) => { setDetailsError(e instanceof Error ? e.message : "상세 조회 실패"); });
    }, 300);
    return () => clearTimeout(timer);
  }, [isTerminal, uploadResult?.doc_id, docDetails]);

  const doUpload = useCallback(async (file: File, fileHash?: string | null) => {
    setUploading(true);
    setUploadError(null);
    try {
      const result = await uploadDocument(file, "upload", fileHash ?? undefined);
      setUploadResult(result);
      setKpiRefreshKey(k => k + 1);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "업로드 중 오류 발생");
    } finally {
      setUploading(false);
    }
  }, []);

  const doReplace = useCallback(async (oldDocId: string, file: File, fileHash?: string | null) => {
    setUploading(true);
    setUploadError(null);
    try {
      const result = await replaceDocument(oldDocId, file, fileHash);
      setUploadResult({ doc_id: result.new_doc_id, status: result.status, message: result.message, quality_score: null, hitl_required: false, chunk_count: 0 });
      setKpiRefreshKey(k => k + 1);
    } catch (e) {
      setUploadError(e instanceof Error ? e.message : "교체 중 오류 발생");
    } finally {
      setUploading(false);
    }
  }, []);

  const handleFile = useCallback(async (file: File) => {
    const ext = "." + (file.name.split(".").pop()?.toLowerCase() ?? "");
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      setUploadError(`지원하지 않는 형식입니다. 지원: ${ACCEPTED_EXTENSIONS.join(", ")}`);
      return;
    }
    setUploadError(null);
    setUploadResult(null);
    setDocDetails(null);
    setShowChunks(false);
    setDuplicateState(null);

    let fileHash: string | null = null;
    try {
      fileHash = await computeFileHash(file);
    } catch {
      // hash 실패 시 체크 없이 업로드 진행
    }

    if (fileHash) {
      try {
        const dupResult = await checkDuplicate(fileHash, file.name);
        if (dupResult.status !== "new" && dupResult.existing_doc) {
          setDuplicateState({
            type: dupResult.status,
            existingDoc: dupResult.existing_doc,
            pendingFile: file,
            pendingHash: fileHash,
          });
          return;
        }
      } catch {
        // 중복 체크 실패 시 업로드 계속 진행
      }
    }

    await doUpload(file, fileHash);
  }, [doUpload]);

  const onFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) void handleFile(file);
    e.target.value = "";
  };

  const onDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files[0];
    if (file) void handleFile(file);
  };

  const liveTraces =
    docDetails && docDetails.agent_traces.length > 0
      ? docDetails.agent_traces
      : status?.agent_traces ?? [];
  const isProcessing = uploading ||
    currentStatus === "processing" ||
    currentStatus === "reprocessing" ||
    currentStatus === "approved";

  const traceId = docDetails?.agent_traces?.[0]?.trace_id;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      {/* ── 중복 감지 모달 ─────────────────────────────────────────── */}
      {duplicateState && (
        duplicateState.type === "identical" ? (
          <DuplicateModal
            type="identical"
            existingDoc={duplicateState.existingDoc}
            onKeepExisting={() => { setDuplicateState(null); onGoToStored?.(duplicateState.existingDoc.doc_id); }}
            onReupload={() => {
              const { pendingFile, pendingHash, existingDoc } = duplicateState;
              setDuplicateState(null);
              void doReplace(existingDoc.doc_id, pendingFile, pendingHash);
            }}
            onCancel={() => setDuplicateState(null)}
          />
        ) : (
          <DuplicateModal
            type="modified"
            existingDoc={duplicateState.existingDoc}
            onKeepExisting={() => { setDuplicateState(null); onGoToStored?.(duplicateState.existingDoc.doc_id); }}
            onReplace={() => {
              const { pendingFile, pendingHash, existingDoc } = duplicateState;
              setDuplicateState(null);
              void doReplace(existingDoc.doc_id, pendingFile, pendingHash);
            }}
            onAddNew={() => {
              const { pendingFile, pendingHash } = duplicateState;
              setDuplicateState(null);
              void doUpload(pendingFile, pendingHash);
            }}
            onCancel={() => setDuplicateState(null)}
          />
        )
      )}

      {/* ── KPI Row ─────────────────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 12 }}>
        <KpiCard label="전체 문서" value={kpi.total}      color="#6366f1" loading={kpi.loading} />
        <KpiCard label="처리 중"   value={kpi.processing} color="#f59e0b" loading={kpi.loading} />
        <KpiCard label="HITL 대기" value={kpi.hitl}       color="#3b82f6" loading={kpi.loading} />
        <KpiCard label="적재 완료" value={kpi.stored}     color="#22c55e" loading={kpi.loading} />
        <KpiCard label="실패/거부" value={kpi.other}      color="#ef4444" loading={kpi.loading} />
      </div>

      {/* ── Main two-column area ─────────────────────────────────────── */}
      <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>

        {/* Left column: upload + status */}
        <div style={{ flex: "0 0 400px", display: "flex", flexDirection: "column", gap: 12 }}>

          {/* Upload card */}
          <div style={{
            padding: "20px 24px", borderRadius: 12,
            boxShadow: "0 2px 12px rgba(0,0,0,0.07)",
            background: "#fff",
          }}>
            <h2 style={{ margin: "0 0 2px", fontSize: 16, fontWeight: 700 }}>사내 문서 업로드</h2>
            <p style={{ margin: "0 0 16px", fontSize: 13, color: "#6b7280" }}>
              PDF · DOCX · PPTX · TXT · MD를 KMS 파이프라인으로 처리합니다.
            </p>

            <div
              style={{
                border: "2px dashed",
                borderColor: dragOver ? "#6366f1" : "#d1d5db",
                background: dragOver ? "#eef2ff" : "#f9fafb",
                borderRadius: 10, padding: "28px 16px",
                textAlign: "center", cursor: "pointer",
                transition: "all 0.2s", userSelect: "none",
              }}
              onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
              onDragLeave={() => setDragOver(false)}
              onDrop={onDrop}
              onClick={() => fileInputRef.current?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => e.key === "Enter" && fileInputRef.current?.click()}
            >
              <span style={{ fontSize: 32 }}>📄</span>
              <p style={{ margin: "8px 0 4px", fontSize: 14, fontWeight: 500, color: "#374151" }}>
                {uploading ? "업로드 중..." : "파일을 드래그하거나 클릭하여 선택"}
              </p>
              <p style={{ margin: 0, fontSize: 12, color: "#9ca3af" }}>
                {ACCEPTED_EXTENSIONS.join(" · ")}
              </p>
              <input
                ref={fileInputRef}
                type="file"
                accept={ACCEPTED_MIME}
                onChange={onFileChange}
                style={{ display: "none" }}
                disabled={uploading}
              />
            </div>

            {uploadError && (
              <div style={{ marginTop: 12, padding: "8px 12px", borderRadius: 8, background: "#fef2f2", border: "1px solid #fca5a5", color: "#dc2626", fontSize: 13 }}>
                ⚠️ {uploadError}
              </div>
            )}
            {statusError && (
              <div style={{ marginTop: 12, padding: "8px 12px", borderRadius: 8, background: "#fff7ed", border: "1px solid #fdba74", color: "#9a3412", fontSize: 13 }}>
                상태 조회 오류: {statusError}
              </div>
            )}
          </div>

          {/* Status card */}
          {uploadResult && (
            <div style={{
              padding: 16, borderRadius: 12, background: "#fff",
              border: "1px solid #e2e8f0", boxShadow: "0 1px 4px rgba(0,0,0,0.04)",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                <span style={{ fontSize: 11, color: "#64748b", minWidth: 48 }}>문서 ID</span>
                <code style={{ fontSize: 11, background: "#f1f5f9", padding: "2px 6px", borderRadius: 4, color: "#475569", wordBreak: "break-all", flex: 1 }}>
                  {uploadResult.doc_id}
                </code>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: currentStatus === "processing" ? 10 : 0 }}>
                <span style={{ fontSize: 11, color: "#64748b", minWidth: 48 }}>상태</span>
                <span style={{ fontSize: 12, fontWeight: 600, color: "#fff", background: statusColor, padding: "3px 10px", borderRadius: 20 }}>
                  {statusLabel ?? currentStatus}
                </span>
              </div>

              {currentStatus === "processing" && (
                <div style={{ height: 4, background: "#e5e7eb", borderRadius: 2, overflow: "hidden", marginTop: 8 }}>
                  <div style={{ height: "100%", width: "40%", background: "#f59e0b", borderRadius: 2, animation: "slide 1.5s infinite" }} />
                </div>
              )}

              {isTerminal && (
                <div style={{ marginTop: 10, fontSize: 13 }}>
                  {currentStatus === "stored"         && <p style={{ color: "#166534",  margin: 0 }}>✅ DB에 저장 완료.</p>}
                  {currentStatus === "stored_partial" && <p style={{ color: "#3f6212",  margin: 0 }}>✅ PostgreSQL/pgVector 완료 (Neo4j 연결 실패)</p>}
                  {currentStatus === "hitl_pending"   && <p style={{ color: "#1e40af",  margin: 0 }}>🔵 HITL 검토 큐에서 승인 시 파이프라인이 재개됩니다.</p>}
                  {currentStatus === "approved"       && <p style={{ color: "#6d28d9",  margin: 0 }}>✅ 검토 승인됨. 재처리 시작 중...</p>}
                  {currentStatus === "reprocessing"   && <p style={{ color: "#92400e",  margin: 0 }}>🔄 재처리 중입니다.</p>}
                  {currentStatus === "rejected"       && <p style={{ color: "#4b5563",  margin: 0 }}>⛔ 거부됨. 새 파일을 업로드하세요.</p>}
                  {currentStatus === "failed"         && <p style={{ color: "#991b1b",  margin: 0 }}>❌ 처리 실패: {status?.error ?? "알 수 없는 오류"}</p>}
                  {detailsError                       && <p style={{ color: "#92400e",  margin: "6px 0 0", fontSize: 12 }}>상세 조회 실패: {detailsError}</p>}

                  {docDetails && docDetails.chunks.length > 0 && (
                    <button
                      style={{
                        marginTop: 8, display: "block", background: "#f1f5f9",
                        border: "1px solid #e2e8f0", borderRadius: 6,
                        padding: "6px 14px", fontSize: 12, fontWeight: 600,
                        color: "#475569", cursor: "pointer", width: "100%", textAlign: "left",
                      }}
                      onClick={() => setShowChunks(v => !v)}
                    >
                      {showChunks ? "▲ 청크 분석 닫기" : "▼ 청크 분석 보기"}
                    </button>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Right column: doc info + pipeline flow */}
        <div style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column", gap: 12 }}>

          {/* Doc info panel (shows when upload result exists) */}
          {uploadResult ? (
            <div style={{
              padding: "14px 16px", borderRadius: 12, background: "#fff",
              border: "1px solid #e2e8f0",
            }}>
              <div style={{ fontSize: 13, fontWeight: 700, color: "#1e293b", marginBottom: 10 }}>문서 정보</div>
              <InfoRow label="Doc ID"   value={uploadResult.doc_id}                        mono />
              {traceId                && <InfoRow label="Trace ID"   value={traceId}        mono />}
              {docDetails?.file_type  && <InfoRow label="형식"        value={docDetails.file_type.toUpperCase()} />}
              {docDetails?.created_at && <InfoRow label="생성일"      value={new Date(docDetails.created_at).toLocaleString("ko-KR")} />}
              {uploadResult.chunk_count !== null && (
                <InfoRow label="청크 수" value={String(uploadResult.chunk_count)} />
              )}
              {uploadResult.quality_score !== null && uploadResult.quality_score !== undefined && (
                <InfoRow label="품질 점수" value={uploadResult.quality_score.toFixed(3)} />
              )}
              {uploadResult.hitl_required && currentStatus === "hitl_pending" && (
                <div style={{ marginTop: 8, padding: "6px 10px", borderRadius: 6, background: "#eff6ff", border: "1px solid #bfdbfe", fontSize: 12, color: "#1e40af" }}>
                  HITL 검토 큐로 이동됨 — HITL 검토 탭에서 승인하세요
                </div>
              )}
            </div>
          ) : (
            <div style={{
              padding: "20px 16px", borderRadius: 12, background: "#fff",
              border: "1px dashed #e2e8f0", textAlign: "center", color: "#94a3b8", fontSize: 13,
            }}>
              파일을 업로드하면 문서 정보가 여기 표시됩니다.
            </div>
          )}

          {/* Pipeline flow — always visible */}
          <div style={{ borderRadius: 12, overflow: "hidden" }}>
            <PipelineFlow traces={liveTraces} isProcessing={isProcessing} />
          </div>
        </div>
      </div>

      {/* ── Chunk analysis (expanded) ────────────────────────────────── */}
      {showChunks && docDetails && docDetails.chunks.length > 0 && (
        <div style={{ paddingBottom: 40 }}>
          <DocumentAnalyzer chunks={docDetails.chunks} docId={uploadResult?.doc_id} />
        </div>
      )}
    </div>
  );
}
