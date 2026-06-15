import { useCallback, useEffect, useState } from "react";
import { SplitView } from "./SplitView";
import {
  approveHitl, applyCategory, getHitlMarkdown, getPageImages,
  listHitlQueue, rejectHitl, reprocessHitl, suggestCategory,
} from "../lib/hitlApi";
import type { CategorySuggestion, PageImage } from "../lib/hitlApi";
import type { HitlQueueItem } from "../types/kms";

type TabStatus = "pending" | "approved" | "rejected" | "reprocessing";

const STATUS_COLOR: Record<string, string> = {
  pending:      "#f59e0b",
  approved:     "#22c55e",
  rejected:     "#ef4444",
  reprocessing: "#6366f1",
};
const STAGE_LABEL: Record<string, string> = {
  stage2_validate:           "Markdown 검증",
  stage4_chunk_validate:     "청크 검증",
  stage5b_metadata_validate: "KB 카테고리 검증",
};
const PAGE_SIZE = 20;

// ── localStorage helpers ──────────────────────────────────────────────────────
const HIDDEN_KEY = "hitl_hidden_ids";

function loadHiddenIds(): Set<string> {
  try {
    const saved = localStorage.getItem(HIDDEN_KEY);
    return saved ? new Set(JSON.parse(saved) as string[]) : new Set<string>();
  } catch { return new Set<string>(); }
}
function saveHiddenIds(ids: Set<string>) {
  localStorage.setItem(HIDDEN_KEY, JSON.stringify([...ids]));
}

// ── HitlQueue ─────────────────────────────────────────────────────────────────
export function HitlQueue() {
  const [tab, setTab]           = useState<TabStatus>("pending");
  const [items, setItems]       = useState<HitlQueueItem[]>([]);
  const [total, setTotal]       = useState(0);
  const [offset, setOffset]     = useState(0);
  const [loading, setLoading]   = useState(false);
  const [error, setError]       = useState<string | null>(null);
  const [selected, setSelected] = useState<HitlQueueItem | null>(null);
  const [busy, setBusy]         = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  // KB Evolution
  const [kbSuggestion, setKbSuggestion] = useState<CategorySuggestion | null>(null);
  const [kbLoading, setKbLoading]       = useState(false);
  const [kbInput, setKbInput]           = useState("");
  const [kbSelected, setKbSelected]     = useState<string>("");

  // delete (hide) — localStorage-based
  const [hiddenIds, setHiddenIds] = useState<Set<string>>(loadHiddenIds);
  const [showHidden, setShowHidden] = useState(false);

  const reviewerId = "admin";
  const canDelete  = tab === "approved" || tab === "rejected";

  const load = useCallback(async (pageOffset = 0) => {
    setLoading(true);
    setError(null);
    try {
      const data = await listHitlQueue(tab, PAGE_SIZE, pageOffset);
      setItems(data.items);
      setTotal(data.total);
      setOffset(pageOffset);
    } catch (e) {
      setError(e instanceof Error ? e.message : "조회 실패");
    } finally {
      setLoading(false);
    }
  }, [tab]);

  useEffect(() => {
    void load(0);
    setSelected(null);
    setActionMsg(null);
  }, [load]);

  // ── delete helpers ────────────────────────────────────────────────────────
  const hideItem = (queueId: string) => {
    setHiddenIds(prev => {
      const next = new Set(prev);
      next.add(queueId);
      saveHiddenIds(next);
      return next;
    });
    if (selected?.queue_id === queueId) setSelected(null);
  };

  const restoreAll = () => {
    const empty = new Set<string>();
    setHiddenIds(empty);
    saveHiddenIds(empty);
    setShowHidden(false);
  };

  // ── KB Evolution ──────────────────────────────────────────────────────────
  const KB_EVOLUTION_TRIGGERS = ["새 카테고리", "Gemini 불확실성", "신규 기술 도메인", "대안 카테고리"];
  const isKbEvolution = (item: HitlQueueItem | null) =>
    item?.stage === "stage5b_metadata_validate" &&
    KB_EVOLUTION_TRIGGERS.some(t => (item?.reason ?? "").includes(t));

  const handleKbSuggest = async (item: HitlQueueItem) => {
    setKbLoading(true);
    setKbSuggestion(null);
    setKbSelected("");
    try {
      setKbSuggestion(await suggestCategory(item.queue_id));
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "제안 조회 실패");
    } finally {
      setKbLoading(false);
    }
  };

  const handleKbApply = async (item: HitlQueueItem) => {
    const category = kbInput.trim() || kbSelected;
    if (!category) { setActionMsg("카테고리를 선택하거나 입력하세요."); return; }
    setBusy(true);
    try {
      const res = await applyCategory(item.queue_id, category, "");
      setActionMsg(res.message);
      setKbSuggestion(null);
      setKbInput("");
      setKbSelected("");
      await load(offset);
      setSelected(null);
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "적용 실패");
    } finally {
      setBusy(false);
    }
  };

  // ── action handlers ───────────────────────────────────────────────────────
  const handleApprove = async (item: HitlQueueItem, autoReprocess: boolean) => {
    setBusy(true); setActionMsg(null);
    try {
      const res = await approveHitl(item.queue_id, { reviewer_id: reviewerId, auto_reprocess: autoReprocess });
      setActionMsg(res.message);
      await load(offset);
      setSelected(null);
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "오류 발생");
    } finally { setBusy(false); }
  };

  const handleReject = async (item: HitlQueueItem, note: string) => {
    if (!note.trim()) { setActionMsg("거부 사유를 입력하세요."); return; }
    setBusy(true); setActionMsg(null);
    try {
      const res = await rejectHitl(item.queue_id, { reviewer_id: reviewerId, review_note: note });
      setActionMsg(res.message);
      await load(offset);
      setSelected(null);
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "오류 발생");
    } finally { setBusy(false); }
  };

  const handleReprocess = async (item: HitlQueueItem, skipValidation: boolean) => {
    setBusy(true); setActionMsg(null);
    try {
      const res = await reprocessHitl(item.queue_id, { reviewer_id: reviewerId, skip_validation: skipValidation });
      setActionMsg(res.message);
      await load(offset);
      setSelected(null);
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "오류 발생");
    } finally { setBusy(false); }
  };

  // ── visible items (applying hide filter) ─────────────────────────────────
  const visibleItems = canDelete && !showHidden
    ? items.filter(item => !hiddenIds.has(item.queue_id))
    : items;
  const hiddenCount = canDelete
    ? items.filter(item => hiddenIds.has(item.queue_id)).length
    : 0;

  // ── render ────────────────────────────────────────────────────────────────
  return (
    <div style={{ fontFamily: "system-ui, sans-serif" }}>
      {/* Header */}
      <div style={{ marginBottom: 16 }}>
        <h2 style={{ margin: "0 0 4px", fontSize: 18, fontWeight: 700 }}>HITL 검토 큐</h2>
        <p style={{ margin: 0, fontSize: 13, color: "#6b7280" }}>
          수동 검토가 필요한 문서를 확인하고 승인·거부·재처리합니다.
        </p>
      </div>

      {/* Tab bar */}
      <div style={{ display: "flex", gap: 6, marginBottom: 16, alignItems: "center" }}>
        {(["pending", "reprocessing", "approved", "rejected"] as TabStatus[]).map((s) => (
          <button
            key={s}
            style={{
              display: "flex", alignItems: "center", gap: 6,
              padding: "6px 14px", borderRadius: 8,
              border: `1px solid ${tab === s ? STATUS_COLOR[s] : "#e2e8f0"}`,
              background: tab === s ? STATUS_COLOR[s] : "#f8fafc",
              fontSize: 13, fontWeight: 500,
              color: tab === s ? "#fff" : "#475569",
              cursor: "pointer",
            }}
            onClick={() => setTab(s)}
          >
            <span style={{ width: 8, height: 8, borderRadius: "50%", background: tab === s ? "rgba(255,255,255,0.6)" : STATUS_COLOR[s], display: "inline-block" }} />
            {{ pending: "대기 중", reprocessing: "재처리 중", approved: "승인됨", rejected: "거부됨" }[s]}
          </button>
        ))}
        <button
          style={{ marginLeft: "auto", padding: "6px 10px", borderRadius: 8, border: "1px solid #e2e8f0", background: "#fff", fontSize: 16, cursor: "pointer", color: "#6b7280" }}
          onClick={() => void load(offset)}
          disabled={loading}
        >↻</button>
      </div>

      {error     && <div style={{ padding: "10px 14px", borderRadius: 8, marginBottom: 12, background: "#fef2f2", border: "1px solid #fca5a5", color: "#dc2626", fontSize: 13 }}>{error}</div>}
      {actionMsg && <div style={{ padding: "10px 14px", borderRadius: 8, marginBottom: 12, background: "#f0fdf4", border: "1px solid #86efac", color: "#166534", fontSize: 13 }}>{actionMsg}</div>}

      {/* Split layout */}
      <div style={{ display: "flex", gap: 16, alignItems: "flex-start" }}>

        {/* Left: item list */}
        <div style={{ flex: "0 0 380px", display: "flex", flexDirection: "column", gap: 8 }}>
          {/* Pagination */}
          {total > 0 && (
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", padding: "4px 2px" }}>
              <span style={{ fontSize: 12, color: "#64748b" }}>총 {total}건{canDelete && hiddenCount > 0 ? ` (${hiddenCount}건 숨김)` : ""}</span>
              <div style={{ display: "flex", gap: 4 }}>
                <button style={{ padding: "3px 10px", borderRadius: 6, border: "1px solid #e2e8f0", background: "#f8fafc", fontSize: 14, cursor: "pointer", color: "#475569" }} disabled={offset === 0 || loading} onClick={() => void load(Math.max(0, offset - PAGE_SIZE))}>‹</button>
                <span style={{ fontSize: 12, color: "#64748b", lineHeight: "28px" }}>{Math.floor(offset / PAGE_SIZE) + 1} / {Math.ceil(total / PAGE_SIZE)}</span>
                <button style={{ padding: "3px 10px", borderRadius: 6, border: "1px solid #e2e8f0", background: "#f8fafc", fontSize: 14, cursor: "pointer", color: "#475569" }} disabled={offset + PAGE_SIZE >= total || loading} onClick={() => void load(offset + PAGE_SIZE)}>›</button>
              </div>
            </div>
          )}

          {loading && <p style={{ fontSize: 13, color: "#9ca3af", textAlign: "center", padding: 24 }}>로딩 중...</p>}
          {!loading && visibleItems.length === 0 && (
            <p style={{ fontSize: 13, color: "#9ca3af", textAlign: "center", padding: 24 }}>
              {canDelete && hiddenCount > 0 ? `${hiddenCount}건이 숨김 처리됨` : "항목이 없습니다."}
            </p>
          )}

          {visibleItems.map((item) => (
            <div
              key={item.queue_id}
              style={{
                padding: "12px 14px", borderRadius: 10, background: "#fff",
                border: selected?.queue_id === item.queue_id ? "1px solid #6366f1" : "1px solid #e2e8f0",
                boxShadow: selected?.queue_id === item.queue_id ? "0 0 0 3px rgba(99,102,241,0.1)" : "none",
                cursor: "pointer", transition: "box-shadow 0.15s",
              }}
              onClick={() => { setSelected(item); setActionMsg(null); }}
            >
              <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 6 }}>
                <span style={{ fontSize: 11, fontWeight: 600, color: "#6366f1", background: "#eef2ff", padding: "2px 8px", borderRadius: 12 }}>
                  {STAGE_LABEL[item.stage] ?? item.stage}
                </span>
                <span style={{ fontSize: 14, color: STATUS_COLOR[item.status] }}>●</span>
              </div>
              <div style={{ fontSize: 11, color: "#94a3b8", fontFamily: "monospace", marginBottom: 4 }} title={item.doc_id}>
                {item.doc_id.slice(0, 18)}…
              </div>
              {item.original_filename && (
                <div style={{ fontSize: 12, color: "#374151", fontWeight: 500, marginBottom: 2, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                  {item.original_filename}
                </div>
              )}
              <div style={{ fontSize: 12, color: "#6b7280", marginBottom: 4, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
                {item.reason}
              </div>
              {item.quality_score !== null && (
                <div style={{ fontSize: 12, color: "#6b7280" }}>품질 점수: <strong>{item.quality_score!.toFixed(2)}</strong></div>
              )}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 6 }}>
                <span style={{ fontSize: 11, color: "#9ca3af" }}>{item.created_at.slice(0, 19).replace("T", " ")}</span>
                {canDelete && (
                  <button
                    onClick={(e) => { e.stopPropagation(); hideItem(item.queue_id); }}
                    style={{
                      padding: "2px 8px", fontSize: 11, borderRadius: 6,
                      border: "1px solid #e2e8f0", background: "#f8fafc",
                      color: "#94a3b8", cursor: "pointer",
                    }}
                  >삭제</button>
                )}
              </div>
            </div>
          ))}

          {/* Hidden items control */}
          {canDelete && hiddenCount > 0 && (
            <div style={{ display: "flex", gap: 8, justifyContent: "center", padding: "8px 0", borderTop: "1px dashed #e2e8f0", marginTop: 4 }}>
              <button
                onClick={() => setShowHidden(v => !v)}
                style={{ fontSize: 12, color: "#6366f1", background: "none", border: "none", cursor: "pointer" }}
              >
                {showHidden ? "▲ 숨김 목록 접기" : `▼ 숨긴 항목 ${hiddenCount}건 보기`}
              </button>
              <span style={{ color: "#e2e8f0" }}>|</span>
              <button
                onClick={restoreAll}
                style={{ fontSize: 12, color: "#94a3b8", background: "none", border: "none", cursor: "pointer" }}
              >전체 복원</button>
            </div>
          )}
        </div>

        {/* Right: detail panel */}
        {selected && (
          <ItemDetail
            key={selected.queue_id}
            item={selected}
            busy={busy}
            onApprove={handleApprove}
            onReject={handleReject}
            onReprocess={handleReprocess}
            isKbEvolution={isKbEvolution(selected)}
            kbSuggestion={kbSuggestion}
            kbLoading={kbLoading}
            kbInput={kbInput}
            kbSelected={kbSelected}
            onKbSuggest={() => void handleKbSuggest(selected)}
            onKbSelect={setKbSelected}
            onKbInputChange={setKbInput}
            onKbApply={() => void handleKbApply(selected)}
            onLoadMarkdown={getHitlMarkdown}
            onGetPageImages={getPageImages}
          />
        )}

        {/* Placeholder when nothing selected */}
        {!selected && (
          <div style={{
            flex: 1, display: "flex", alignItems: "center", justifyContent: "center",
            minHeight: 240, borderRadius: 12, border: "1px dashed #e2e8f0",
            background: "#fafafa", color: "#94a3b8", fontSize: 13,
          }}>
            ← 항목을 선택하면 상세 정보가 표시됩니다
          </div>
        )}
      </div>
    </div>
  );
}

// ── ItemDetail ────────────────────────────────────────────────────────────────
function ItemDetail({
  item, busy, onApprove, onReject, onReprocess,
  isKbEvolution, kbSuggestion, kbLoading, kbInput, kbSelected,
  onKbSuggest, onKbSelect, onKbInputChange, onKbApply,
  onLoadMarkdown, onGetPageImages,
}: {
  item: HitlQueueItem;
  busy: boolean;
  onApprove: (item: HitlQueueItem, auto: boolean) => void;
  onReject: (item: HitlQueueItem, note: string) => void;
  onReprocess: (item: HitlQueueItem, skip: boolean) => void;
  isKbEvolution: boolean;
  kbSuggestion: CategorySuggestion | null;
  kbLoading: boolean;
  kbInput: string;
  kbSelected: string;
  onKbSuggest: () => void;
  onKbSelect: (v: string) => void;
  onKbInputChange: (v: string) => void;
  onKbApply: () => void;
  onLoadMarkdown: (queueId: string) => Promise<{ markdown: string; path: string }>;
  onGetPageImages: (queueId: string) => Promise<PageImage[]>;
}) {
  const [rejectNote, setRejectNote]     = useState("");
  const [splitData, setSplitData]       = useState<{ markdown: string; pageImages: PageImage[] } | null>(null);
  const [splitLoading, setSplitLoading] = useState(false);

  const handleLoadSplitView = async () => {
    setSplitLoading(true);
    let md = "";
    let images: PageImage[] = [];
    try {
      const mdRes = await onLoadMarkdown(item.queue_id);
      md = mdRes.markdown;
    } catch (e) {
      md = `Markdown 로드 실패: ${e instanceof Error ? e.message : "알 수 없는 오류"}`;
    }
    try {
      images = await onGetPageImages(item.queue_id);
    } catch {
      // 이미지 로드 실패는 무시 — 마크다운은 표시
    }
    setSplitData({ markdown: md, pageImages: images });
    setSplitLoading(false);
  };

  const isPending = item.status === "pending";
  const kbReady   = !!(kbInput.trim() || kbSelected);

  const issues = item.issues as Record<string, unknown> | null;
  const qualityIssues: string[] = Array.isArray(issues?.["quality_issues"])
    ? (issues!["quality_issues"] as string[])
    : [];

  return (
    <div style={{
      flex: 1, padding: "20px 24px", borderRadius: 12, background: "#fff",
      border: "1px solid #e2e8f0", boxShadow: "0 2px 8px rgba(0,0,0,0.06)",
    }}>
      {/* Header */}
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 16 }}>
        <span style={{
          fontSize: 11, fontWeight: 600, color: "#fff",
          background: { pending: "#f59e0b", approved: "#22c55e", rejected: "#ef4444", reprocessing: "#6366f1" }[item.status] ?? "#94a3b8",
          padding: "3px 10px", borderRadius: 12,
        }}>
          {{ pending: "대기 중", approved: "승인됨", rejected: "거부됨", reprocessing: "재처리 중" }[item.status]}
        </span>
        <span style={{ fontSize: 13, fontWeight: 700, color: "#1e293b" }}>항목 상세</span>
      </div>

      {/* Info rows */}
      <Row label="Queue ID"   value={item.queue_id}                       mono />
      <Row label="Doc ID"     value={item.doc_id}                         mono />
      <Row label="단계"        value={STAGE_LABEL[item.stage] ?? item.stage} />
      <Row label="사유"        value={item.reason} />
      {item.original_filename && <Row label="원본 파일"  value={item.original_filename} />}
      {item.file_type         && <Row label="파일 유형"  value={item.file_type.toUpperCase()} />}
      {item.parser_used       && <Row label="파서"       value={item.parser_used} />}
      {item.quality_score !== null && item.quality_score !== undefined && (
        <Row label="품질 점수" value={item.quality_score.toFixed(3)} />
      )}
      {item.reviewer_id  && <Row label="검토자"    value={item.reviewer_id} />}
      {item.review_note  && <Row label="검토 메모" value={item.review_note} />}

      {/* Issue list */}
      {qualityIssues.length > 0 && (
        <div style={{ marginTop: 12, padding: "10px 12px", background: "#fffbeb", borderRadius: 8, border: "1px solid #fde68a" }}>
          <span style={{ fontSize: 12, fontWeight: 600, color: "#92400e", display: "block", marginBottom: 6 }}>이슈 목록</span>
          <ul style={{ margin: 0, padding: "0 0 0 16px" }}>
            {qualityIssues.map((issue, i) => (
              <li key={i} style={{ fontSize: 13, color: "#b45309", marginBottom: 3 }}>{issue}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Markdown preview */}
      <div style={{ marginTop: 14 }}>
        <button
          style={{ padding: "5px 12px", borderRadius: 8, border: "1px solid #e2e8f0", background: "#f8fafc", color: "#475569", fontWeight: 600, fontSize: 12, cursor: "pointer" }}
          disabled={splitLoading}
          onClick={() => void handleLoadSplitView()}
        >
          {splitLoading ? "로딩 중..." : "📄 Markdown 미리보기"}
        </button>
        {splitData !== null && (
          <div style={{ marginTop: 8, height: "calc(100vh - 320px)", minHeight: 540, borderRadius: 8, overflow: "hidden", border: "1px solid #e2e8f0" }}>
            <SplitView markdown={splitData.markdown} pageImages={splitData.pageImages} />
          </div>
        )}
      </div>

      {/* KB Evolution */}
      {isKbEvolution && isPending && (
        <div style={{ marginTop: 16, padding: "14px 16px", borderRadius: 10, background: "#eef2ff", border: "1px solid #c7d2fe" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 }}>
            <span style={{ fontSize: 13, fontWeight: 700, color: "#4338ca" }}>AI 카테고리 제안</span>
            <button
              style={{ padding: "5px 12px", borderRadius: 8, border: "none", background: "#6366f1", color: "#fff", fontWeight: 600, fontSize: 12, cursor: "pointer" }}
              disabled={kbLoading || busy}
              onClick={onKbSuggest}
            >
              {kbLoading ? "조회 중..." : "AI 제안 받기"}
            </button>
          </div>
          {kbSuggestion && (
            <>
              <p style={{ fontSize: 12, color: "#4b5563", margin: "4px 0 8px" }}>{kbSuggestion.reasoning}</p>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginBottom: 8 }}>
                {kbSuggestion.suggested.map((s) => (
                  <button
                    key={s}
                    style={{
                      padding: "4px 12px", borderRadius: 16, fontSize: 12, fontWeight: 500, cursor: "pointer",
                      border: "1px solid", borderColor: kbSelected === s ? "#6366f1" : "#a5b4fc",
                      background: kbSelected === s ? "#6366f1" : "#fff",
                      color: kbSelected === s ? "#fff" : "#4338ca",
                    }}
                    onClick={() => { onKbSelect(s); onKbInputChange(""); }}
                  >{s}</button>
                ))}
              </div>
              {kbSuggestion.alternatives.length > 0 && (
                <p style={{ fontSize: 11, color: "#6b7280", margin: "0 0 8px" }}>차선책: {kbSuggestion.alternatives.join(", ")}</p>
              )}
            </>
          )}
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            <input
              style={{ flex: 1, padding: "7px 12px", borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13, outline: "none" }}
              placeholder="직접 입력 (새 카테고리명)"
              value={kbInput}
              onChange={(e) => { onKbInputChange(e.target.value); onKbSelect(""); }}
              disabled={busy}
            />
            <button
              style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: "#22c55e", color: "#fff", fontWeight: 600, fontSize: 13, cursor: "pointer" }}
              disabled={busy || !kbReady}
              onClick={onKbApply}
            >확정 적용</button>
          </div>
        </div>
      )}

      {/* Actions (pending only) */}
      {isPending && (
        <div style={{ marginTop: 20, display: "flex", flexDirection: "column", gap: 8 }}>
          <button
            style={{ padding: "10px 16px", borderRadius: 8, border: "none", background: "#22c55e", color: "#fff", fontWeight: 600, fontSize: 14, cursor: "pointer" }}
            disabled={busy}
            onClick={() => onApprove(item, true)}
          >✅ 승인 (현재 Markdown으로 청킹 진행)</button>
          <p style={{ margin: "0 0 4px", fontSize: 11, color: "#6b7280" }}>현재 변환된 Markdown을 그대로 승인하고 다음 단계(청킹)를 시작합니다.</p>

          <button
            style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: "#f59e0b", color: "#fff", fontWeight: 600, fontSize: 13, cursor: "pointer", marginTop: 4 }}
            disabled={busy}
            onClick={() => onReprocess(item, true)}
          >⚡ 강제 진행 (품질 기준 무시)</button>
          <p style={{ margin: "0 0 4px", fontSize: 11, color: "#6b7280" }}>품질 점수 기준을 무시하고 현재 상태로 강제 청킹합니다.</p>

          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <input
              style={{ flex: 1, padding: "7px 12px", borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13, outline: "none" }}
              placeholder="거부 사유 입력..."
              value={rejectNote}
              onChange={(e) => setRejectNote(e.target.value)}
              disabled={busy}
            />
            <button
              style={{ padding: "8px 16px", borderRadius: 8, border: "none", background: "#ef4444", color: "#fff", fontWeight: 600, fontSize: 13, cursor: "pointer" }}
              disabled={busy || !rejectNote.trim()}
              onClick={() => onReject(item, rejectNote)}
            >거부</button>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={{ display: "flex", gap: 12, marginBottom: 8, alignItems: "flex-start" }}>
      <span style={{ fontSize: 12, color: "#64748b", minWidth: 72, paddingTop: 1 }}>{label}</span>
      <span style={{ fontSize: 13, color: "#334155", fontFamily: mono ? "monospace" : undefined, wordBreak: "break-all" }}>{value}</span>
    </div>
  );
}
