import { useState } from "react";
import { DocumentUpload } from "../../components/DocumentUpload";
import { ChatBot } from "../../components/ChatBot";

type Tab = "upload" | "chat";

export default function KmsPage() {
  const [tab, setTab] = useState<Tab>("upload");

  return (
    <div style={{ padding: "24px 32px" }}>
      <div style={{ display: "flex", gap: 0, marginBottom: 24, borderBottom: "2px solid #f1f5f9" }}>
        <TabBtn active={tab === "upload"} onClick={() => setTab("upload")}>📄 문서 업로드</TabBtn>
        <TabBtn active={tab === "chat"}   onClick={() => setTab("chat")}>💬 지식 검색</TabBtn>
      </div>

      {tab === "upload" && <DocumentUpload isVisible={tab === "upload"} />}
      {tab === "chat"   && <ChatBot />}
    </div>
  );
}

function TabBtn({ active, onClick, children }: { active: boolean; onClick: () => void; children: React.ReactNode }) {
  return (
    <button
      onClick={onClick}
      style={{
        padding: "10px 20px",
        fontSize: 14,
        fontWeight: active ? 700 : 500,
        color: active ? "#6366f1" : "#64748b",
        background: "none",
        border: "none",
        borderBottom: active ? "2px solid #6366f1" : "2px solid transparent",
        marginBottom: -2,
        cursor: "pointer",
        transition: "all 0.15s",
      }}
    >
      {children}
    </button>
  );
}
