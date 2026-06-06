import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { PageImage } from "../lib/hitlApi";

interface SplitViewProps {
  markdown: string;
  pageImages: PageImage[];
}

export function SplitView({ markdown, pageImages }: SplitViewProps) {
  const [currentPage, setCurrentPage] = useState(1);

  const currentImage = pageImages.find(p => p.page === currentPage);
  const totalPages   = pageImages.length;

  return (
    <div
      data-testid="split-view"
      style={{ display: "flex", gap: 0, height: "100%", overflow: "hidden" }}
    >
      {/* Left: PDF pages */}
      <div
        data-testid="pdf-panel"
        style={{
          flex: 1,
          display: "flex",
          flexDirection: "column",
          borderRight: "1px solid #e2e8f0",
          overflow: "hidden",
          background: "#f1f5f9",
        }}
      >
        {/* Page nav */}
        {totalPages > 0 && (
          <div style={{ padding: "8px 12px", borderBottom: "1px solid #e2e8f0", display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", background: "#fff" }}>
            {pageImages.map(p => (
              <button
                key={p.page}
                data-testid={`page-btn-${p.page}`}
                onClick={() => setCurrentPage(p.page)}
                style={{
                  padding: "3px 9px",
                  borderRadius: 6,
                  border: "1px solid #e2e8f0",
                  background: currentPage === p.page ? "#6366f1" : "#fff",
                  color: currentPage === p.page ? "#fff" : "#475569",
                  fontSize: 12,
                  fontWeight: 600,
                  cursor: "pointer",
                }}
              >
                {p.page}
              </button>
            ))}
            <span
              data-testid="current-page-indicator"
              style={{ marginLeft: "auto", fontSize: 12, color: "#64748b" }}
            >
              {currentPage} / {totalPages}
            </span>
          </div>
        )}

        <div style={{ flex: 1, overflowY: "auto", display: "flex", justifyContent: "center", padding: 16 }}>
          {pageImages.length === 0 ? (
            <p style={{ color: "#94a3b8", fontSize: 13, textAlign: "center", margin: "auto" }}>페이지 이미지가 없습니다</p>
          ) : currentImage ? (
            <img
              data-testid="pdf-page-image"
              src={currentImage.url}
              alt={`페이지 ${currentPage}`}
              style={{ maxWidth: "100%", height: "auto", borderRadius: 4, boxShadow: "0 2px 8px rgba(0,0,0,0.12)" }}
            />
          ) : null}
        </div>
      </div>

      {/* Right: Markdown */}
      <div
        data-testid="markdown-panel"
        style={{
          flex: 1,
          overflowY: "auto",
          padding: "16px 20px",
          background: "#fff",
          fontSize: 14,
          lineHeight: 1.7,
          color: "#1e293b",
        }}
      >
        <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
      </div>
    </div>
  );
}
