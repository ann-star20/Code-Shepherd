import { useState } from "react";
import { DocumentUpload } from "./components/DocumentUpload";
import { HitlQueue } from "./components/HitlQueue";
import { ChatBot } from "./components/ChatBot";

type Page = "upload" | "hitl" | "chat";

export default function App() {
  const [page, setPage] = useState<Page>("upload");

  return (
    <div style={{ minHeight: "100vh", background: "#f1f5f9", padding: "0 16px" }}>
      <header style={{
        background: "#fff",
        borderBottom: "1px solid #e5e7eb",
        padding: "14px 32px",
        display: "flex",
        alignItems: "center",
        gap: 24,
        marginBottom: 0,
      }}>
        <h1 style={{ margin: 0, fontSize: 18, fontWeight: 700, color: "#1e293b", flex: "none" }}>
          KMS — 지식 관리 시스템
        </h1>
        <nav style={{ display: "flex", gap: 4 }}>
          <NavBtn active={page === "upload"} onClick={() => setPage("upload")}>문서 업로드</NavBtn>
          <NavBtn active={page === "hitl"}   onClick={() => setPage("hitl")}>HITL 검토 큐</NavBtn>
          <NavBtn active={page === "chat"}   onClick={() => setPage("chat")}>💬 지식 챗봇</NavBtn>
        </nav>
      </header>
      <div style={{ display: page === "upload" ? "block" : "none" }}>
        <DocumentUpload isVisible={page === "upload"} />
      </div>
      <div style={{ display: page === "hitl" ? "block" : "none" }}>
        <HitlQueue />
      </div>
      <div style={{ display: page === "chat" ? "block" : "none" }}>
        <ChatBot />
      </div>
    </div>
  );
}

function NavBtn({ active, onClick, children }: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "6px 14px",
        borderRadius: 8,
        border: "none",
        background: active ? "#6366f1" : "transparent",
        color: active ? "#fff" : "#6b7280",
        fontWeight: active ? 600 : 400,
        fontSize: 14,
        cursor: "pointer",
      }}
    >
      {children}
    </button>
  );
}
