/**
 * Phase 1 TDD — ChatBot 3패널 레이아웃
 * RED: 구현 전 실패해야 하는 테스트들
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ChatBot } from "../components/ChatBot";

vi.mock("../lib/chatApi", () => ({
  fetchChat: vi.fn().mockResolvedValue({
    answer: "테스트 답변입니다.",
    intent: "general",
    storages: ["pgvector"],
    sources: [
      {
        source_type: "pgvector",
        doc_title: "테스트 문서",
        content: "내용 일부",
        score: 0.92,
      },
    ],
  }),
}));

describe("ChatBot — 3패널 레이아웃", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("최근 질문 사이드바가 렌더링된다", () => {
    render(<ChatBot />);
    expect(screen.getByTestId("recent-questions-panel")).toBeInTheDocument();
  });

  it("채팅 영역이 렌더링된다", () => {
    render(<ChatBot />);
    expect(screen.getByTestId("chat-panel")).toBeInTheDocument();
  });

  it("참고 문서 사이드바가 렌더링된다", () => {
    render(<ChatBot />);
    expect(screen.getByTestId("source-docs-panel")).toBeInTheDocument();
  });

  it("최근 질문이 없을 때 빈 상태 메시지를 보여준다", () => {
    render(<ChatBot />);
    expect(screen.getByText(/최근 질문이 없습니다/)).toBeInTheDocument();
  });

  it("질문 전송 후 최근 질문 패널에 추가된다", async () => {
    render(<ChatBot />);

    const textarea = screen.getByPlaceholderText(/질문을 입력하세요/);
    fireEvent.change(textarea, { target: { value: "N+1 쿼리란?" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });

    await waitFor(() => {
      expect(screen.getByTestId("recent-question-item")).toBeInTheDocument();
    });
  });

  it("최근 질문을 클릭하면 입력창에 채워진다", async () => {
    localStorage.setItem(
      "chatbot-recent-questions",
      JSON.stringify(["N+1 쿼리 방지 방법은?"])
    );

    render(<ChatBot />);

    const questionItem = screen.getByTestId("recent-question-item");
    fireEvent.click(questionItem);

    const textarea = screen.getByPlaceholderText(/질문을 입력하세요/);
    expect((textarea as HTMLTextAreaElement).value).toBe("N+1 쿼리 방지 방법은?");
  });

  it("답변에 소스가 있으면 참고 문서 패널에 표시된다", async () => {
    render(<ChatBot />);

    const textarea = screen.getByPlaceholderText(/질문을 입력하세요/);
    fireEvent.change(textarea, { target: { value: "테스트 질문" } });
    fireEvent.keyDown(textarea, { key: "Enter", shiftKey: false });

    await waitFor(() => {
      const panel = screen.getByTestId("source-docs-panel");
      expect(panel).toHaveTextContent("테스트 문서");
    });
  });
});
