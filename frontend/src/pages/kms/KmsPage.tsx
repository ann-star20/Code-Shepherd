import { ChatBot } from "../../components/ChatBot";

export default function KmsPage() {
  return (
    <div style={{ padding: "24px 32px", maxWidth: 960, margin: "0 auto" }}>
      <div style={{ marginBottom: 24 }}>
        <h1 style={{ margin: "0 0 4px", fontSize: 20, fontWeight: 700 }}>KMS 吏??寃??/h1>
        <p style={{ margin: 0, fontSize: 14, color: "#6b7280" }}>
          ?щ궡 臾몄꽌瑜?湲곕컲?쇰줈 吏덈Ц???듬??⑸땲??
        </p>
      </div>
      <ChatBot />
    </div>
  );
}
