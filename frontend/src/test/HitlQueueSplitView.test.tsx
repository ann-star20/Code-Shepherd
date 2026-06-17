/**
 * HitlQueue ItemDetail — SplitView 연결 TDD
 * RED: "📄 Markdown 미리보기" 클릭 시 SplitView가 렌더링되어야 함 (현재는 <pre> 렌더링)
 */

import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { HitlQueue } from "../components/HitlQueue";
import { listHitlQueue, getHitlMarkdown, getPageImages } from "../lib/hitlApi";

vi.mock("../lib/hitlApi", () => ({
  listHitlQueue:   vi.fn(),
  getHitlMarkdown: vi.fn(),
  getPageImages:   vi.fn(),
  approveHitl:     vi.fn(),
  rejectHitl:      vi.fn(),
  reprocessHitl:   vi.fn(),
  suggestCategory: vi.fn(),
  applyCategory:   vi.fn(),
}));

const MOCK_QUEUE_ITEM = {
  queue_id:          "q-001",
  doc_id:            "d-001",
  stage:             "stage2_validate",
  reason:            "품질 점수 미달",
  quality_score:     0.55,
  issues:            null,
  status:            "pending" as const,
  reviewer_id:       null,
  review_note:       null,
  created_at:        "2026-06-06T00:00:00",
  original_filename: "test.pdf",
  file_type:         "pdf",
  parser_used:       "pymupdf",
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(listHitlQueue).mockResolvedValue({
    items: [MOCK_QUEUE_ITEM],
    total: 1,
    limit: 20,
    offset: 0,
  });
  vi.mocked(getHitlMarkdown).mockResolvedValue({
    markdown: "# 테스트 문서\n\n내용입니다.",
    path:     "/some/path.md",
  });
  vi.mocked(getPageImages).mockResolvedValue([
    { page: 1, url: "/hitl/queue/q-001/page/1" },
    { page: 2, url: "/hitl/queue/q-001/page/2" },
  ]);
});

async function renderAndOpenSplitView() {
  render(<HitlQueue />);
  await screen.findByText("품질 점수 미달");
  fireEvent.click(screen.getByText("품질 점수 미달"));
  fireEvent.click(screen.getByText("📄 Markdown 미리보기"));
}

describe("HitlQueue ItemDetail — SplitView 연결", () => {
  it("Markdown 미리보기 버튼 클릭 시 split-view 컨테이너가 렌더링된다", async () => {
    await renderAndOpenSplitView();
    await screen.findByTestId("split-view");
    expect(screen.getByTestId("split-view")).toBeInTheDocument();
  });

  it("SplitView에 pdf-panel과 markdown-panel이 모두 표시된다", async () => {
    await renderAndOpenSplitView();
    await screen.findByTestId("split-view");
    expect(screen.getByTestId("pdf-panel")).toBeInTheDocument();
    expect(screen.getByTestId("markdown-panel")).toBeInTheDocument();
  });

  it("페이지 이미지가 있으면 페이지 번호 버튼이 표시된다", async () => {
    await renderAndOpenSplitView();
    await screen.findByTestId("page-btn-1");
    expect(screen.getByTestId("page-btn-1")).toBeInTheDocument();
    expect(screen.getByTestId("page-btn-2")).toBeInTheDocument();
  });

  it("Markdown 내용이 ReactMarkdown으로 렌더링된다 (h1 태그)", async () => {
    await renderAndOpenSplitView();
    await screen.findByTestId("split-view");
    await waitFor(() => {
      expect(screen.getByRole("heading", { name: "테스트 문서" })).toBeInTheDocument();
    });
  });

  it("getHitlMarkdown과 getPageImages가 동시에 호출된다", async () => {
    await renderAndOpenSplitView();
    await screen.findByTestId("split-view");
    expect(vi.mocked(getHitlMarkdown)).toHaveBeenCalledWith("q-001");
    expect(vi.mocked(getPageImages)).toHaveBeenCalledWith("q-001");
  });
});
