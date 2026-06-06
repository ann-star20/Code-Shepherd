import { ChatBot } from "../../components/ChatBot";

export default function KmsPage() {
  return (
    <div style={{ padding: "24px 32px", maxWidth: 960, margin: "0 auto" }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: "0 0 4px", fontSize: 20, fontWeight: 700 }}>KMS 지식 검색</h1>
        <p style={{ margin: 0, fontSize: 14, color: "#6b7280" }}>
          사내 문서를 기반으로 질문에 답변합니다.
        </p>
      </div>
      <ChatBot />
    </div>
  );
}
