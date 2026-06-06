import { useCallback, useEffect, useState } from "react";
import { SplitView } from "./SplitView";
import { approveHitl, applyCategory, getHitlMarkdown, getPageImages, listHitlQueue, rejectHitl, reprocessHitl, suggestCategory } from "../lib/hitlApi";
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

export function HitlQueue() {
  const [tab, setTab]         = useState<TabStatus>("pending");
  const [items, setItems]     = useState<HitlQueueItem[]>([]);
  const [total, setTotal]     = useState(0);
  const [offset, setOffset]   = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState<string | null>(null);
  const [selected, setSelected] = useState<HitlQueueItem | null>(null);
  const [busy, setBusy]       = useState(false);
  const [actionMsg, setActionMsg] = useState<string | null>(null);

  const [kbSuggestion, setKbSuggestion] = useState<CategorySuggestion | null>(null);
  const [kbLoading, setKbLoading]       = useState(false);
  const [kbInput, setKbInput]           = useState("");
  const [kbSelected, setKbSelected]     = useState<string>("");

  const reviewerId = "admin";

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
    load(0);
    setSelected(null);
    setActionMsg(null);
  }, [load]);

  const isKbEvolution = (item: HitlQueueItem | null) =>
    item?.stage === "stage5b_metadata_validate" &&
    typeof item?.issues === "object" &&
    Array.isArray((item.issues as Record<string, unknown>)?.["issues"]) &&
    ((item.issues as Record<string, unknown>)?.["issues"] as string[])
      .some((i: string) => i.includes("새 카테고리"));

  const handleKbSuggest = async (item: HitlQueueItem) => {
    setKbLoading(true);
    setKbSuggestion(null);
    setKbSelected("");
    try {
      const data = await suggestCategory(item.queue_id);
      setKbSuggestion(data);
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

  const handleApprove = async (item: HitlQueueItem, autoReprocess: boolean) => {
    setBusy(true);
    setActionMsg(null);
    try {
      const res = await approveHitl(item.queue_id, { reviewer_id: reviewerId, auto_reprocess: autoReprocess });
      setActionMsg(res.message);
      await load(offset);
      setSelected(null);
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "오류 발생");
    } finally {
      setBusy(false);
    }
  };

  const handleReject = async (item: HitlQueueItem, note: string) => {
    if (!note.trim()) { setActionMsg("거부 사유를 입력하세요."); return; }
    setBusy(true);
    setActionMsg(null);
    try {
      const res = await rejectHitl(item.queue_id, { reviewer_id: reviewerId, review_note: note });
      setActionMsg(res.message);
      await load(offset);
      setSelected(null);
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "오류 발생");
    } finally {
      setBusy(false);
    }
  };

  const handleReprocess = async (item: HitlQueueItem, skipValidation: boolean) => {
    setBusy(true);
    setActionMsg(null);
    try {
      const res = await reprocessHitl(item.queue_id, { reviewer_id: reviewerId, skip_validation: skipValidation });
      setActionMsg(res.message);
      await load(offset);
      setSelected(null);
    } catch (e) {
      setActionMsg(e instanceof Error ? e.message : "오류 발생");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div style={styles.root}>
      <h2 style={styles.heading}>HITL 검토 큐</h2>
      <p style={styles.sub}>수동 검토가 필요한 문서를 확인하고 승인·거부·재처리합니다.</p>

      <div style={styles.tabs}>
        {(["pending", "reprocessing", "approved", "rejected"] as TabStatus[]).map((s) => (
          <button key={s} style={{ ...styles.tab, ...(tab === s ? styles.tabActive : {}) }} onClick={() => setTab(s)}>
            <span style={{ ...styles.dot, background: STATUS_COLOR[s] }} />
            {{ pending: "대기 중", reprocessing: "재처리 중", approved: "승인됨", rejected: "거부됨" }[s]}
          </button>
        ))}
        <button style={styles.refresh} onClick={() => load(offset)} disabled={loading}>↻</button>
      </div>

      {error     && <div style={styles.errBanner}>{error}</div>}
      {actionMsg && <div style={styles.infoBanner}>{actionMsg}</div>}

      <div style={styles.layout}>
        <div style={styles.list}>
          {total > 0 && (
            <div style={styles.pagination}>
              <span style={styles.pageInfo}>총 {total}건</span>
              <div style={{ display: "flex", gap: 4 }}>
                <button style={styles.pageBtn} disabled={offset === 0 || loading} onClick={() => load(Math.max(0, offset - PAGE_SIZE))}>‹</button>
                <span style={styles.pageInfo}>{Math.floor(offset / PAGE_SIZE) + 1} / {Math.ceil(total / PAGE_SIZE)}</span>
                <button style={styles.pageBtn} disabled={offset + PAGE_SIZE >= total || loading} onClick={() => load(offset + PAGE_SIZE)}>›</button>
              </div>
            </div>
          )}
          {loading && <p style={styles.empty}>로딩 중...</p>}
          {!loading && items.length === 0 && <p style={styles.empty}>항목이 없습니다.</p>}
          {items.map((item) => (
            <div
              key={item.queue_id}
              style={{ ...styles.card, ...(selected?.queue_id === item.queue_id ? styles.cardActive : {}) }}
              onClick={() => { setSelected(item); setActionMsg(null); }}
            >
              <div style={styles.cardTop}>
                <span style={styles.stageBadge}>{STAGE_LABEL[item.stage] ?? item.stage}</span>
                <span style={{ ...styles.statusDot, color: STATUS_COLOR[item.status] }}>●</span>
              </div>
              <div style={styles.docId} title={item.doc_id}>{item.doc_id.slice(0, 16)}…</div>
              <div style={styles.reason}>{item.reason}</div>
              {item.quality_score !== null && <div style={styles.score}>품질 점수: <strong>{item.quality_score.toFixed(2)}</strong></div>}
              <div style={styles.createdAt}>{item.created_at.slice(0, 19).replace("T", " ")}</div>
            </div>
          ))}
        </div>

        {selected && (
          <ItemDetail
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
            onKbSuggest={() => handleKbSuggest(selected)}
            onKbSelect={setKbSelected}
            onKbInputChange={setKbInput}
            onKbApply={() => handleKbApply(selected)}
            onLoadMarkdown={getHitlMarkdown}
          onGetPageImages={getPageImages}
          />
        )}
      </div>
    </div>
  );
}

function ItemDetail({
  item, busy, onApprove, onReject, onReprocess,
  isKbEvolution, kbSuggestion, kbLoading, kbInput, kbSelected,
  onKbSuggest, onKbSelect, onKbInputChange, onKbApply, onLoadMarkdown, onGetPageImages,
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
  const [rejectNote, setRejectNote]   = useState("");
  const [splitData, setSplitData]     = useState<{ markdown: string; pageImages: PageImage[] } | null>(null);
  const [splitLoading, setSplitLoading] = useState(false);

  const handleLoadSplitView = async () => {
    setSplitLoading(true);
    try {
      const [mdRes, images] = await Promise.all([
        onLoadMarkdown(item.queue_id),
        onGetPageImages(item.queue_id),
      ]);
      setSplitData({ markdown: mdRes.markdown, pageImages: images });
    } catch {
      setSplitData({ markdown: "Markdown 로드 실패", pageImages: [] });
    } finally {
      setSplitLoading(false);
    }
  };

  const isPending = item.status === "pending";
  const kbReady   = !!(kbInput.trim() || kbSelected);

  return (
    <div style={styles.detail}>
      <h3 style={styles.detailTitle}>항목 상세</h3>

      <Row label="Queue ID"   value={item.queue_id} mono />
      <Row label="Doc ID"     value={item.doc_id}   mono />
      <Row label="단계"       value={STAGE_LABEL[item.stage] ?? item.stage} />
      <Row label="사유"       value={item.reason} />
      {item.original_filename && <Row label="원본 파일" value={item.original_filename} />}
      {item.file_type         && <Row label="파일 유형" value={item.file_type.toUpperCase()} />}
      {item.parser_used       && <Row label="파서"     value={item.parser_used} />}
      {item.quality_score !== null && <Row label="품질 점수" value={item.quality_score!.toFixed(3)} />}
      {item.reviewer_id       && <Row label="검토자"   value={item.reviewer_id} />}
      {item.review_note       && <Row label="검토 메모" value={item.review_note} />}

      {(() => {
        const issues = item.issues as Record<string, unknown> | null;
        const qualityIssues = Array.isArray(issues?.["quality_issues"]) ? (issues!["quality_issues"] as string[]) : [];
        return qualityIssues.length > 0 ? (
          <div style={styles.issueBox}>
            <span style={styles.issueLabel}>이슈 목록</span>
            <ul style={{ margin: "6px 0 0", padding: "0 0 0 16px" }}>
              {qualityIssues.map((issue, i) => <li key={i} style={{ fontSize: 13, color: "#b45309", marginBottom: 4 }}>{issue}</li>)}
            </ul>
          </div>
        ) : null;
      })()}

      <div style={{ marginTop: 12 }}>
        <button style={{ ...styles.btn, background: "#64748b", fontSize: 12, padding: "5px 12px" }} disabled={splitLoading} onClick={handleLoadSplitView}>
          {splitLoading ? "로딩 중..." : "📄 Markdown 미리보기"}
        </button>
        {splitData !== null && (
          <div style={{ marginTop: 8, height: 500, borderRadius: 6, overflow: "hidden", border: "1px solid #e2e8f0" }}>
            <SplitView markdown={splitData.markdown} pageImages={splitData.pageImages} />
          </div>
        )}
      </div>

      {isKbEvolution && isPending && (
        <div style={styles.kbPanel}>
          <div style={styles.kbHeader}>
            <span style={styles.kbTitle}>AI 카테고리 제안</span>
            <button style={{ ...styles.btn, background: "#6366f1", fontSize: 12, padding: "5px 12px" }} disabled={kbLoading || busy} onClick={onKbSuggest}>
              {kbLoading ? "조회 중..." : "AI 제안 받기"}
            </button>
          </div>
          {kbSuggestion && (
            <>
              <p style={styles.kbReasoning}>{kbSuggestion.reasoning}</p>
              <div style={styles.kbChips}>
                {kbSuggestion.suggested.map((s) => (
                  <button key={s} style={{ ...styles.kbChip, ...(kbSelected === s ? styles.kbChipActive : {}) }} onClick={() => { onKbSelect(s); onKbInputChange(""); }}>
                    {s}
                  </button>
                ))}
              </div>
              {kbSuggestion.alternatives.length > 0 && <p style={styles.kbAlt}>차선책: {kbSuggestion.alternatives.join(", ")}</p>}
            </>
          )}
          <div style={styles.kbInputRow}>
            <input style={styles.noteInput} placeholder="직접 입력 (새 카테고리명)" value={kbInput} onChange={(e) => { onKbInputChange(e.target.value); onKbSelect(""); }} disabled={busy} />
            <button style={{ ...styles.btn, background: "#22c55e" }} disabled={busy || !kbReady} onClick={onKbApply}>확정 적용</button>
          </div>
        </div>
      )}

      {isPending && (
        <div style={styles.actions}>
          <button style={{ ...styles.btn, background: "#22c55e", fontSize: 14, padding: "10px 16px" }} disabled={busy} onClick={() => onApprove(item, true)}>
            ✅ 승인 (현재 Markdown으로 청킹 진행)
          </button>
          <p style={{ margin: "0 0 4px", fontSize: 11, color: "#6b7280" }}>현재 변환된 Markdown을 그대로 승인하고 다음 단계(청킹)를 시작합니다.</p>

          <button style={{ ...styles.btn, background: "#f59e0b", marginTop: 4 }} disabled={busy} onClick={() => onReprocess(item, true)}>
            ⚡ 강제 진행 (품질 기준 무시)
          </button>
          <p style={{ margin: "0 0 4px", fontSize: 11, color: "#6b7280" }}>품질 점수 기준을 무시하고 현재 상태로 강제 청킹합니다. 이슈가 남을 수 있습니다.</p>

          <div style={{ ...styles.rejectRow, marginTop: 8 }}>
            <input style={styles.noteInput} placeholder="거부 사유 입력..." value={rejectNote} onChange={(e) => setRejectNote(e.target.value)} disabled={busy} />
            <button style={{ ...styles.btn, background: "#ef4444" }} disabled={busy || !rejectNote.trim()} onClick={() => onReject(item, rejectNote)}>거부</button>
          </div>
        </div>
      )}
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={styles.row}>
      <span style={styles.rowLabel}>{label}</span>
      <span style={mono ? styles.rowMono : styles.rowValue}>{value}</span>
    </div>
  );
}

const styles: Record<string, React.CSSProperties> = {
  root:     { maxWidth: 1100, margin: "40px auto", fontFamily: "system-ui, sans-serif" },
  heading:  { margin: "0 0 4px", fontSize: 20, fontWeight: 700 },
  sub:      { margin: "0 0 20px", fontSize: 14, color: "#6b7280" },
  tabs:     { display: "flex", gap: 6, marginBottom: 16, alignItems: "center" },
  tab:      { display: "flex", alignItems: "center", gap: 6, padding: "6px 14px", borderRadius: 8, border: "1px solid #e2e8f0", background: "#f8fafc", fontSize: 13, fontWeight: 500, cursor: "pointer", color: "#475569" },
  tabActive:{ background: "#6366f1", color: "#fff", border: "1px solid #6366f1" },
  dot:      { width: 8, height: 8, borderRadius: "50%", display: "inline-block" },
  refresh:  { marginLeft: "auto", padding: "6px 10px", borderRadius: 8, border: "1px solid #e2e8f0", background: "#fff", fontSize: 16, cursor: "pointer", color: "#6b7280" },
  errBanner:  { padding: "10px 14px", borderRadius: 8, marginBottom: 12, background: "#fef2f2", border: "1px solid #fca5a5", color: "#dc2626", fontSize: 13 },
  infoBanner: { padding: "10px 14px", borderRadius: 8, marginBottom: 12, background: "#f0fdf4", border: "1px solid #86efac", color: "#166534", fontSize: 13 },
  layout:   { display: "flex", gap: 16, alignItems: "flex-start" },
  list:     { flex: "0 0 320px", display: "flex", flexDirection: "column", gap: 8 },
  card:     { padding: "12px 14px", borderRadius: 10, background: "#fff", border: "1px solid #e2e8f0", cursor: "pointer", transition: "box-shadow 0.15s" },
  cardActive: { border: "1px solid #6366f1", boxShadow: "0 0 0 3px rgba(99,102,241,0.12)" },
  cardTop:  { display: "flex", justifyContent: "space-between", marginBottom: 6 },
  stageBadge: { fontSize: 11, fontWeight: 600, color: "#6366f1", background: "#eef2ff", padding: "2px 8px", borderRadius: 12 },
  statusDot:  { fontSize: 14 },
  docId:    { fontSize: 11, color: "#94a3b8", fontFamily: "monospace", marginBottom: 4 },
  reason:   { fontSize: 13, color: "#374151", marginBottom: 4 },
  score:    { fontSize: 12, color: "#6b7280" },
  createdAt:{ fontSize: 11, color: "#9ca3af", marginTop: 4 },
  empty:    { fontSize: 13, color: "#9ca3af", textAlign: "center", padding: 24 },
  pagination: { display: "flex", justifyContent: "space-between", alignItems: "center", padding: "6px 4px", marginBottom: 4 },
  pageInfo: { fontSize: 12, color: "#64748b" },
  pageBtn:  { padding: "3px 10px", borderRadius: 6, border: "1px solid #e2e8f0", background: "#f8fafc", fontSize: 14, cursor: "pointer", color: "#475569" },
  detail:       { flex: 1, padding: "20px 24px", borderRadius: 12, background: "#fff", border: "1px solid #e2e8f0", boxShadow: "0 2px 8px rgba(0,0,0,0.06)" },
  detailTitle:  { margin: "0 0 16px", fontSize: 16, fontWeight: 700, color: "#1e293b" },
  row:          { display: "flex", gap: 12, marginBottom: 8, alignItems: "flex-start" },
  rowLabel:     { fontSize: 12, color: "#64748b", minWidth: 72, paddingTop: 1 },
  rowValue:     { fontSize: 13, color: "#334155" },
  rowMono:      { fontSize: 11, color: "#475569", fontFamily: "monospace", wordBreak: "break-all" },
  issueBox:     { marginTop: 12, padding: "10px 12px", background: "#f8fafc", borderRadius: 8, border: "1px solid #e2e8f0" },
  issueLabel:   { fontSize: 12, fontWeight: 600, color: "#64748b", display: "block", marginBottom: 6 },
  actions:      { marginTop: 20, display: "flex", flexDirection: "column", gap: 8 },
  btn:          { padding: "8px 16px", borderRadius: 8, border: "none", color: "#fff", fontWeight: 600, fontSize: 13, cursor: "pointer" },
  rejectRow:    { display: "flex", gap: 8, marginTop: 4 },
  noteInput:    { flex: 1, padding: "7px 12px", borderRadius: 8, border: "1px solid #cbd5e1", fontSize: 13, outline: "none" },
  kbPanel:      { marginTop: 16, padding: "14px 16px", borderRadius: 10, background: "#eef2ff", border: "1px solid #c7d2fe" },
  kbHeader:     { display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 8 },
  kbTitle:      { fontSize: 13, fontWeight: 700, color: "#4338ca" },
  kbReasoning:  { fontSize: 12, color: "#4b5563", margin: "4px 0 8px" },
  kbChips:      { display: "flex", flexWrap: "wrap" as const, gap: 6, marginBottom: 8 },
  kbChip:       { padding: "4px 12px", borderRadius: 16, fontSize: 12, fontWeight: 500, border: "1px solid #a5b4fc", background: "#fff", color: "#4338ca", cursor: "pointer" },
  kbChipActive: { background: "#6366f1", color: "#fff", border: "1px solid #6366f1" },
  kbAlt:        { fontSize: 11, color: "#6b7280", margin: "0 0 8px" },
  kbInputRow:   { display: "flex", gap: 8, marginTop: 4 },
};
