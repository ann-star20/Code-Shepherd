import { Component, type ReactNode } from "react";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { MainPage } from "@/pages/MainPage";

class ErrorBoundary extends Component<{ children: ReactNode }, { error: Error | null }> {
  state = { error: null };
  static getDerivedStateFromError(error: Error) { return { error }; }
  render() {
    if (this.state.error) {
      const e = this.state.error as Error;
      return (
        <div style={{ padding: 32, fontFamily: "monospace", background: "#1C1917", color: "#F5F5F4", minHeight: "100vh" }}>
          <h2 style={{ color: "#F87171", marginBottom: 12 }}>React Render Error</h2>
          <pre style={{ color: "#FCA5A5", whiteSpace: "pre-wrap", marginBottom: 16 }}>{e.message}</pre>
          <pre style={{ color: "#78716C", fontSize: 11, whiteSpace: "pre-wrap" }}>{e.stack}</pre>
          <button
            onClick={() => this.setState({ error: null })}
            style={{ marginTop: 24, padding: "8px 16px", background: "#115E59", color: "#FFF", border: "none", borderRadius: 8, cursor: "pointer" }}
          >
            재시도
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export default function App() {
  return (
    <ErrorBoundary>
      <BrowserRouter>
        <Routes>
          <Route path="/knowledge-pipe" element={<MainPage />} />
          <Route path="*" element={<Navigate to="/knowledge-pipe" replace />} />
        </Routes>
      </BrowserRouter>
    </ErrorBoundary>
  );
}
