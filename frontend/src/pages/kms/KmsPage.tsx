import { ChatBot } from "../../components/ChatBot";

export default function KmsPage() {
  return (
    <div style={{ padding: "24px 32px" }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: "0 0 4px", fontSize: 20, fontWeight: 700 }}>KMS 지식 검색</h1>
        <p style={{ margin: 0, fontSize: 14, color: "#6b7280" }}>
          질문을 입력해 관련 문서를 검색하고 AI 답변을 받아보세요.
        </p>
      </div>
      <ChatBot />
    </div>
  );
}
