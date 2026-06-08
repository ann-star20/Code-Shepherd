/**
 * Phase 3 TDD — StoredDocsList 메타데이터 컬럼
 * RED: neo4j_synced, category, doc_complexity 컬럼 추가 전 실패해야 하는 테스트들
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import KmsManagePage from "../pages/kms/KmsManagePage";

const MOCK_STORED_DOCS = [
  {
    doc_id: "doc-001",
    title: "테스트 문서",
    file_type: "pdf",
    status: "stored",
    created_at: "2026-06-02T00:00:00Z",
    neo4j_synced: true,
    category: "온보딩",
    doc_complexity: "HIGH",
  },
  {
    doc_id: "doc-002",
    title: "두 번째 문서",
    file_type: "docx",
    status: "stored",
    created_at: "2026-06-01T00:00:00Z",
    neo4j_synced: false,
    category: "기술 문서",
    doc_complexity: "LOW",
  },
];

vi.mock("../lib/kmsApi", () => ({
  listDocuments: vi.fn().mockImplementation((status: string) => {
    if (status === "stored") {
      return Promise.resolve({ docs: MOCK_STORED_DOCS, total: 2, limit: 20, offset: 0 });
    }
    return Promise.resolve({ docs: [], total: 0, limit: 20, offset: 0 });
  }),
}));

async function renderStoredTab() {
  render(<KmsManagePage />);
  const storedTab = screen.getByText(/적재 완료 문서/);
  fireEvent.click(storedTab);
  await screen.findByText("테스트 문서");
}

describe("StoredDocsList — 메타데이터 컬럼", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("카테고리 컬럼 헤더가 표시된다", async () => {
    await renderStoredTab();
    expect(screen.getByRole("columnheader", { name: "카테고리" })).toBeInTheDocument();
  });

  it("복잡도 컬럼 헤더가 표시된다", async () => {
    await renderStoredTab();
    expect(screen.getByRole("columnheader", { name: "복잡도" })).toBeInTheDocument();
  });

  it("Neo4j 컬럼 헤더가 표시된다", async () => {
    await renderStoredTab();
    expect(screen.getByRole("columnheader", { name: "Neo4j" })).toBeInTheDocument();
  });

  it("문서의 카테고리 값이 표시된다", async () => {
    await renderStoredTab();
    expect(screen.getByText("온보딩")).toBeInTheDocument();
  });

  it("문서의 복잡도 값이 표시된다", async () => {
    await renderStoredTab();
    expect(screen.getByText("HIGH")).toBeInTheDocument();
  });

  it("Neo4j 동기화 여부가 표시된다 (true → checkmark, false → dash)", async () => {
    await renderStoredTab();
    const cells = screen.getAllByTestId("neo4j-sync-cell");
    expect(cells[0]).toHaveTextContent("✓");
    expect(cells[1]).toHaveTextContent("-");
  });
});

describe("DocListItem 타입 — 메타데이터 필드", () => {
  it("DocListItem 타입에 neo4j_synced/category/doc_complexity 필드가 있다", () => {
    const item: import("../types/kms").DocListItem = {
      doc_id: "x",
      title: "T",
      file_type: "pdf",
      status: "stored",
      created_at: "2026-01-01",
      neo4j_synced: true,
      category: "test",
      doc_complexity: "LOW",
    };
    expect(item.neo4j_synced).toBe(true);
    expect(item.category).toBe("test");
    expect(item.doc_complexity).toBe("LOW");
  });
});
