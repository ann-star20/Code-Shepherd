/**
 * Phase 2 TDD — SplitView (PDF 원본 | Markdown 렌더링)
 * RED: 구현 전 실패해야 하는 테스트들
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { SplitView } from "../components/SplitView";

const MOCK_MARKDOWN = `# 테스트 문서\n\n이것은 **마크다운** 내용입니다.\n\n## 섹션 2\n\n- 항목 1\n- 항목 2`;

const MOCK_PAGE_IMAGES = [
  { page: 1, url: "https://example.com/page1.png" },
  { page: 2, url: "https://example.com/page2.png" },
  { page: 3, url: "https://example.com/page3.png" },
];

describe("SplitView — PDF | Markdown 분할 뷰", () => {
  it("split-view 컨테이너가 렌더링된다", () => {
    render(<SplitView markdown={MOCK_MARKDOWN} pageImages={MOCK_PAGE_IMAGES} />);
    expect(screen.getByTestId("split-view")).toBeInTheDocument();
  });

  it("PDF 패널이 렌더링된다", () => {
    render(<SplitView markdown={MOCK_MARKDOWN} pageImages={MOCK_PAGE_IMAGES} />);
    expect(screen.getByTestId("pdf-panel")).toBeInTheDocument();
  });

  it("Markdown 패널이 렌더링된다", () => {
    render(<SplitView markdown={MOCK_MARKDOWN} pageImages={MOCK_PAGE_IMAGES} />);
    expect(screen.getByTestId("markdown-panel")).toBeInTheDocument();
  });

  it("Markdown이 HTML로 렌더링된다 (react-markdown)", () => {
    render(<SplitView markdown={MOCK_MARKDOWN} pageImages={MOCK_PAGE_IMAGES} />);
    const panel = screen.getByTestId("markdown-panel");
    expect(panel.querySelector("h1")).toBeInTheDocument();
    expect(panel.querySelector("strong")).toBeInTheDocument();
  });

  it("첫 번째 페이지 이미지가 표시된다", () => {
    render(<SplitView markdown={MOCK_MARKDOWN} pageImages={MOCK_PAGE_IMAGES} />);
    const img = screen.getByTestId("pdf-page-image");
    expect(img).toHaveAttribute("src", "https://example.com/page1.png");
  });

  it("페이지 번호 버튼이 렌더링된다", () => {
    render(<SplitView markdown={MOCK_MARKDOWN} pageImages={MOCK_PAGE_IMAGES} />);
    expect(screen.getByTestId("page-btn-1")).toBeInTheDocument();
    expect(screen.getByTestId("page-btn-2")).toBeInTheDocument();
    expect(screen.getByTestId("page-btn-3")).toBeInTheDocument();
  });

  it("페이지 버튼 클릭 시 해당 페이지 이미지로 전환된다", () => {
    render(<SplitView markdown={MOCK_MARKDOWN} pageImages={MOCK_PAGE_IMAGES} />);
    fireEvent.click(screen.getByTestId("page-btn-2"));
    const img = screen.getByTestId("pdf-page-image");
    expect(img).toHaveAttribute("src", "https://example.com/page2.png");
  });

  it("pageImages가 없을 때 안내 메시지를 표시한다", () => {
    render(<SplitView markdown={MOCK_MARKDOWN} pageImages={[]} />);
    expect(screen.getByTestId("pdf-panel")).toHaveTextContent(/페이지 이미지가 없습니다/);
  });

  it("현재 페이지 번호가 표시된다", () => {
    render(<SplitView markdown={MOCK_MARKDOWN} pageImages={MOCK_PAGE_IMAGES} />);
    expect(screen.getByTestId("current-page-indicator")).toHaveTextContent("1 / 3");
  });
});

describe("getPageImages API", () => {
  it("hitlApi에서 getPageImages 함수를 export한다", async () => {
    const module = await import("../lib/hitlApi");
    expect(typeof module.getPageImages).toBe("function");
  });
});

describe("SplitView — rawText 폴백 (TXT/MD 원본 표시)", () => {
  const RAW_TEXT = "이것은 원본 텍스트 내용입니다.\n두 번째 줄입니다.";

  it("pageImages가 없고 rawText가 있을 때 raw-text-panel이 렌더링된다", () => {
    render(<SplitView markdown={MOCK_MARKDOWN} pageImages={[]} rawText={RAW_TEXT} />);
    expect(screen.getByTestId("raw-text-panel")).toBeInTheDocument();
  });

  it("rawText 내용이 raw-text-panel에 표시된다", () => {
    render(<SplitView markdown={MOCK_MARKDOWN} pageImages={[]} rawText={RAW_TEXT} />);
    expect(screen.getByTestId("raw-text-panel")).toHaveTextContent("이것은 원본 텍스트 내용입니다.");
  });

  it("pageImages가 있으면 rawText 대신 이미지가 표시된다", () => {
    render(<SplitView markdown={MOCK_MARKDOWN} pageImages={MOCK_PAGE_IMAGES} rawText={RAW_TEXT} />);
    expect(screen.queryByTestId("raw-text-panel")).not.toBeInTheDocument();
    expect(screen.getByTestId("pdf-page-image")).toBeInTheDocument();
  });

  it("pageImages도 rawText도 없으면 안내 메시지가 표시된다", () => {
    render(<SplitView markdown={MOCK_MARKDOWN} pageImages={[]} />);
    expect(screen.getByTestId("pdf-panel")).toHaveTextContent(/페이지 이미지가 없습니다/);
    expect(screen.queryByTestId("raw-text-panel")).not.toBeInTheDocument();
  });
});
