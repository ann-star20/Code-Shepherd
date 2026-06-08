import { useState, useRef, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { PageImage } from "../lib/hitlApi";

interface SplitViewProps {
  markdown: string;
  pageImages: PageImage[];
  rawText?: string;
}

export function SplitView({ markdown, pageImages, rawText }: SplitViewProps) {
  const [currentPage, setCurrentPage] = useState(1);
  const [zoom,        setZoom]        = useState(100);   // %
  const [leftPct,     setLeftPct]     = useState(50);    // split %
  const [dragging,    setDragging]    = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  const currentImage = pageImages.find(p => p.page === currentPage);
  const totalPages   = pageImages.length;

  const handleDividerMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    setDragging(true);

    const onMouseMove = (ev: MouseEvent) => {
      if (!containerRef.current) return;
      const rect   = containerRef.current.getBoundingClientRect();
      const newPct = ((ev.clientX - rect.left) / rect.width) * 100;
      setLeftPct(Math.min(80, Math.max(20, newPct)));
    };

    const onMouseUp = () => {
      setDragging(false);
      document.removeEventListener("mousemove", onMouseMove);
      document.removeEventListener("mouseup",   onMouseUp);
    };

    document.addEventListener("mousemove", onMouseMove);
    document.addEventListener("mouseup",   onMouseUp);
  }, []);

  return (
    <div
      ref={containerRef}
      data-testid="split-view"
      style={{
        display:    "flex",
        height:     "100%",
        width:      "100%",
        overflow:   "hidden",
        userSelect: dragging ? "none" : "auto",
      }}
    >
      {/* ── Left: PDF ───────────────────────────────── */}
      <div
        data-testid="pdf-panel"
        style={{
          width:          `${leftPct}%`,
          flexShrink:     0,
          display:        "flex",
          flexDirection:  "column",
          overflow:       "hidden",
          background:     "#f1f5f9",
        }}
      >
        {/* Toolbar */}
        <div style={{
          padding:      "5px 10px",
          borderBottom: "1px solid #e2e8f0",
          display:      "flex",
          alignItems:   "center",
          gap:          5,
          flexWrap:     "wrap",
          background:   "#fff",
          flexShrink:   0,
        }}>
          {/* Page buttons */}
          {totalPages > 0 && pageImages.map(p => (
            <button
              key={p.page}
              data-testid={`page-btn-${p.page}`}
              onClick={() => setCurrentPage(p.page)}
              style={{
                padding:    "2px 7px",
                borderRadius: 5,
                border:     "1px solid #e2e8f0",
                background: currentPage === p.page ? "#6366f1" : "#fff",
                color:      currentPage === p.page ? "#fff" : "#475569",
                fontSize:   11,
                fontWeight: 600,
                cursor:     "pointer",
              }}
            >{p.page}</button>
          ))}
          {totalPages > 0 && (
            <span
              data-testid="current-page-indicator"
              style={{ fontSize: 11, color: "#64748b" }}
            >
              {currentPage} / {totalPages}
            </span>
          )}

          {/* Zoom controls */}
          <div style={{ marginLeft: "auto", display: "flex", alignItems: "center", gap: 3 }}>
            <button
              onClick={() => setZoom(z => Math.max(50, z - 25))}
              title="축소"
              style={zoomBtn}
            >−</button>
            <span style={{ fontSize: 11, color: "#64748b", minWidth: 34, textAlign: "center" }}>
              {zoom}%
            </span>
            <button
              onClick={() => setZoom(z => Math.min(300, z + 25))}
              title="확대"
              style={zoomBtn}
            >+</button>
            <button
              onClick={() => setZoom(100)}
              title="너비 맞춤"
              style={{ ...zoomBtn, padding: "0 7px", minWidth: 36, fontSize: 10 }}
            >맞춤</button>
          </div>
        </div>

        {/* Image / text area */}
        <div style={{ flex: 1, overflow: "auto", padding: 0 }}>
          {pageImages.length === 0 && rawText ? (
            <pre style={{
              margin:      0,
              padding:     "12px 16px",
              fontFamily:  "monospace",
              fontSize:    13,
              lineHeight:  1.6,
              color:       "#334155",
              whiteSpace:  "pre-wrap",
              wordBreak:   "break-word",
              background:  "transparent",
              border:      "none",
            }}>{rawText}</pre>
          ) : pageImages.length === 0 ? (
            <p style={{ color: "#94a3b8", fontSize: 13, textAlign: "center", margin: "32px 0" }}>
              페이지 이미지가 없습니다
            </p>
          ) : currentImage ? (
            <img
              data-testid="pdf-page-image"
              src={currentImage.url}
              alt={`페이지 ${currentPage}`}
              style={{
                display:     "block",
                width:       `${zoom}%`,
                maxWidth:    "none",
                height:      "auto",
                borderRadius: 0,
                boxShadow:   "none",
              }}
            />
          ) : null}
        </div>
      </div>

      {/* ── Draggable divider ───────────────────────── */}
      <div
        onMouseDown={handleDividerMouseDown}
        onMouseEnter={e => { e.currentTarget.style.background = "#a5b4fc"; }}
        onMouseLeave={e => { e.currentTarget.style.background = "#e2e8f0"; }}
        style={{
          width:      6,
          flexShrink: 0,
          background: "#e2e8f0",
          cursor:     "col-resize",
          display:    "flex",
          flexDirection: "column",
          alignItems: "center",
          justifyContent: "center",
          gap:        3,
          transition: "background 0.15s",
        }}
      >
        {[0, 1, 2].map(i => (
          <div key={i} style={{ width: 3, height: 3, borderRadius: "50%", background: "#94a3b8" }} />
        ))}
      </div>

      {/* ── Right: Markdown ─────────────────────────── */}
      <div
        data-testid="markdown-panel"
        style={{
          flex:       1,
          minWidth:   0,
          overflowY:  "auto",
          overflowX:  "auto",
          padding:    "14px 18px",
          background: "#fff",
          fontSize:   14,
          lineHeight: 1.7,
          color:      "#1e293b",
        }}
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
      </div>
    </div>
  );
}

const zoomBtn: React.CSSProperties = {
  width:        24,
  height:       24,
  borderRadius: 4,
  border:       "1px solid #e2e8f0",
  background:   "#f8fafc",
  cursor:       "pointer",
  fontSize:     14,
  fontWeight:   700,
  display:      "flex",
  alignItems:   "center",
  justifyContent: "center",
  color:        "#475569",
  padding:      0,
};
