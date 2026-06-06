import { useState, useRef, useEffect } from "react";
import { fetchChat } from "../lib/chatApi";
import type { ChatResponse, ChatSource } from "../types/chat";

const RECENT_QUESTIONS_KEY = "chatbot-recent-questions";
const MAX_RECENT = 10;

interface Message {
  role: "user" | "bot";
  text: string;
  response?: ChatResponse;
  error?: string;
}

const STORAGE_COLORS: Record<string, string> = {
  pgvector:   "#6366f1",
  postgresql: "#0ea5e9",
  neo4j:      "#22c55e",
  gcs:        "#f59e0b",
};

const STORAGE_LABELS: Record<string, string> = {
  pgvector:   "pgVector",
  postgresql: "PostgreSQL",
  neo4j:      "Neo4j",
  gcs:        "GCS",
};

function loadRecentQuestions(): string[] {
  try {
    return JSON.parse(localStorage.getItem(RECENT_QUESTIONS_KEY) ?? "[]");
  } catch {
    return [];
  }
}

function saveRecentQuestions(questions: string[]) {
  localStorage.setItem(RECENT_QUESTIONS_KEY, JSON.stringify(questions));
}

export function ChatBot() {
  const [messages, setMessages]               = useState<Message[]>([]);
  const [input, setInput]                     = useState("");
  const [loading, setLoading]                 = useState(false);
  const [recentQuestions, setRecentQuestions] = useState<string[]>(loadRecentQuestions);
  const [latestSources, setLatestSources]     = useState<ChatSource[]>([]);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const addRecentQuestion = (q: string) => {
    setRecentQuestions(prev => {
      const filtered = prev.filter(r => r !== q);
      const updated = [q, ...filtered].slice(0, MAX_RECENT);
      saveRecentQuestions(updated);
      return updated;
    });
  };

  const handleSubmit = async () => {
    const q = input.trim();
    if (!q || loading) return;

    setInput("");
    addRecentQuestion(q);
    setMessages(prev => [...prev, { role: "user", text: q }]);
    setLoading(true);

    try {
      const res = await fetchChat({ question: q });
      setMessages(prev => [...prev, { role: "bot", text: res.answer, response: res }]);
      setLatestSources(res.sources ?? []);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "알 수 없는 오류";
      setMessages(prev => [...prev, { role: "bot", text: "", error: msg }]);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSubmit();
    }
  };

  return (
    <div style={{ display: "flex", gap: 0, height: "calc(100vh - 140px)", overflow: "hidden" }}>
      {/* Left panel: recent questions */}
      <div
        data-testid="recent-questions-panel"
        style={{
          width: 260,
          flexShrink: 0,
          borderRight: "1px solid #e2e8f0",
          display: "flex",
          flexDirection: "column",
          background: "#f8fafc",
          overflowY: "auto",
        }}
      >
        <div style={{ padding: "16px 16px 8px", borderBottom: "1px solid #e2e8f0" }}>
          <p style={{ margin: 0, fontSize: 12, fontWeight: 700, color: "#475569", textTransform: "uppercase", letterSpacing: "0.05em" }}>최근 질문</p>
        </div>
        <div style={{ flex: 1, padding: "8px", display: "flex", flexDirection: "column", gap: 4 }}>
          {recentQuestions.length === 0 ? (
            <p style={{ color: "#94a3b8", fontSize: 13, textAlign: "center", padding: "24px 8px" }}>최근 질문이 없습니다</p>
          ) : (
            recentQuestions.map((q, i) => (
              <button
                key={i}
                data-testid="recent-question-item"
                onClick={() => setInput(q)}
                style={{
                  textAlign: "left",
                  background: "none",
                  border: "1px solid transparent",
                  borderRadius: 8,
                  padding: "8px 10px",
                  fontSize: 13,
                  color: "#334155",
                  cursor: "pointer",
                  lineHeight: 1.4,
                  whiteSpace: "nowrap",
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                }}
              >
                {q}
              </button>
            ))
          )}
        </div>
      </div>

      {/* Center panel: chat */}
      <div
        data-testid="chat-panel"
        style={{ flex: 1, display: "flex", flexDirection: "column", overflow: "hidden" }}
      >
        <div style={{ flex: 1, overflowY: "auto", display: "flex", flexDirection: "column", gap: 16, padding: "16px 20px" }}>
          {messages.length === 0 && (
            <div style={{ textAlign: "center", color: "#94a3b8", marginTop: 48, fontSize: 14 }}>
              <p>🤖 질문을 입력하면 KMS 지식 베이스에서 답변을 찾아드립니다.</p>
              <p style={{ marginTop: 8, fontSize: 12 }}>예: "N+1 쿼리 방지 방법은?", "저장된 문서 목록 보여줘"</p>
            </div>
          )}

          {messages.map((msg, i) => (
            <div key={i} style={{ display: "flex", flexDirection: "column", alignItems: msg.role === "user" ? "flex-end" : "flex-start" }}>
              <div style={{
                maxWidth: "80%",
                padding: "10px 14px",
                borderRadius: msg.role === "user" ? "18px 18px 4px 18px" : "18px 18px 18px 4px",
                background: msg.role === "user" ? "#6366f1" : "#fff",
                color: msg.role === "user" ? "#fff" : "#1e293b",
                boxShadow: "0 1px 3px rgba(0,0,0,0.1)",
                fontSize: 14,
                lineHeight: 1.6,
              }}>
                {msg.error ? (
                  <span style={{ color: "#ef4444" }}>⚠ {msg.error}</span>
                ) : (
                  msg.text || (loading && i === messages.length - 1 ? "..." : "")
                )}
              </div>
              {msg.role === "bot" && msg.response && (
                <div style={{ marginTop: 6, maxWidth: "80%" }}>
                  <RouterFlow intent={msg.response.intent} storages={msg.response.storages} />
                </div>
              )}
            </div>
          ))}

          {loading && (
            <div style={{ display: "flex", alignItems: "flex-start" }}>
              <div style={{ padding: "10px 14px", borderRadius: "18px 18px 18px 4px", background: "#fff", boxShadow: "0 1px 3px rgba(0,0,0,0.1)", fontSize: 14, color: "#94a3b8" }}>
                답변 생성 중...
              </div>
            </div>
          )}

          <div ref={bottomRef} />
        </div>

        <div style={{ padding: "12px 20px", borderTop: "1px solid #e2e8f0", display: "flex", gap: 8, alignItems: "flex-end" }}>
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="질문을 입력하세요 (Enter 전송, Shift+Enter 줄바꿈)"
            rows={2}
            style={{ flex: 1, padding: "10px 14px", borderRadius: 12, border: "1px solid #e2e8f0", resize: "none", fontSize: 14, fontFamily: "inherit", outline: "none", background: "#fff" }}
          />
          <button
            onClick={() => void handleSubmit()}
            disabled={!input.trim() || loading}
            style={{ padding: "10px 20px", borderRadius: 12, border: "none", background: input.trim() && !loading ? "#6366f1" : "#e2e8f0", color: input.trim() && !loading ? "#fff" : "#94a3b8", fontWeight: 600, fontSize: 14, cursor: input.trim() && !loading ? "pointer" : "default", transition: "background 0.2s" }}
          >
            전송
          </button>
        </div>
      </div>

      {/* Right panel: reference docs */}
      <div
        data-testid="source-docs-panel"
        style={{
          width: 280,
          flexShrink: 0,
          borderLeft: "1px solid #e2e8f0",
          display: "flex",
          flexDirection: "column",
          background: "#f8fafc",
          overflowY: "auto",
        }}
      >
        <div style={{ padding: "16px 16px 8px", borderBottom: "1px solid #e2e8f0" }}>
          <p style={{ margin: 0, fontSize: 12, fontWeight: 700, color: "#475569", textTransform: "uppercase", letterSpacing: "0.05em" }}>참고 문서</p>
        </div>
        <div style={{ flex: 1, padding: "8px" }}>
          {latestSources.length === 0 ? (
            <p style={{ color: "#94a3b8", fontSize: 13, textAlign: "center", padding: "24px 8px" }}>답변 후 참고 문서가 표시됩니다</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
              {latestSources.map((s, i) => <SourceCard key={i} source={s} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

function RouterFlow({ intent, storages }: { intent: string; storages: string[] }) {
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap", marginBottom: 2 }}>
      <span style={{ fontSize: 11, color: "#94a3b8" }}>라우팅:</span>
      <span style={{ fontSize: 11, padding: "2px 8px", borderRadius: 12, background: "#f1f5f9", color: "#475569", fontWeight: 600 }}>{intent}</span>
      <span style={{ fontSize: 11, color: "#cbd5e1" }}>→</span>
      {storages.map(s => (
        <span key={s} style={{ fontSize: 11, padding: "2px 8px", borderRadius: 12, background: STORAGE_COLORS[s] || "#94a3b8", color: "#fff", fontWeight: 600 }}>
          {STORAGE_LABELS[s] || s}
        </span>
      ))}
    </div>
  );
}

function SourceCard({ source }: { source: ChatSource }) {
  const color = STORAGE_COLORS[source.source_type] || "#94a3b8";
  const label = STORAGE_LABELS[source.source_type] || source.source_type;
  return (
    <div style={{ padding: "8px 12px", borderRadius: 8, background: "#fff", border: `1px solid ${color}30`, fontSize: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
        <span style={{ padding: "1px 6px", borderRadius: 8, background: color, color: "#fff", fontSize: 10, fontWeight: 700 }}>{label}</span>
        {source.doc_title && <span style={{ color: "#475569", fontWeight: 600 }}>{source.doc_title}</span>}
        <span style={{ marginLeft: "auto", color: "#94a3b8" }}>{(source.score * 100).toFixed(0)}%</span>
      </div>
      <p style={{ margin: 0, color: "#64748b", lineHeight: 1.5, display: "-webkit-box", WebkitLineClamp: 2, WebkitBoxOrient: "vertical", overflow: "hidden" }}>
        {source.content}
      </p>
    </div>
  );
}
