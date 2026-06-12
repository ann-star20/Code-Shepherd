/**
 * Phase 3 TDD — StoredDocsList 메타데이터 컬럼
 * RED: neo4j_synced, category, doc_complexity 컬럼 추가 전 실패해야 하는 테스트들
 */

import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import KmsManagePage from "../pages/kms/KmsManagePage";
import { listDocuments } from "../lib/kmsApi";

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

describe("StoredDocsList — 페이지네이션 (stored + stored_partial 통합)", () => {
  const makeDoc = (id: string, status: "stored" | "stored_partial") => ({
    doc_id: `doc-page-${id}`,
    title: `페이지문서 ${id}`,
    file_type: "pdf",
    status,
    created_at: `2026-01-${String((parseInt(id) || 1) % 28 + 1).padStart(2, "0")}T00:00:00Z`,
    neo4j_synced: null as boolean | null,
    category: null as string | null,
    doc_complexity: null as string | null,
  });

  const STORED_21 = Array.from({ length: 21 }, (_, i) => makeDoc(String(i + 1), "stored"));
  const PARTIAL_2 = [makeDoc("p1", "stored_partial"), makeDoc("p2", "stored_partial")];

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(listDocuments).mockImplementation((status: string) => {
      if (status === "stored") {
        return Promise.resolve({ docs: STORED_21, total: 21, limit: 20, offset: 0 });
      }
      if (status === "stored_partial") {
        return Promise.resolve({ docs: PARTIAL_2, total: 2, limit: 20, offset: 0 });
      }
      return Promise.resolve({ docs: [], total: 0, limit: 20, offset: 0 });
    });
  });

  it("총 건수는 stored + stored_partial 합산이다 (23건)", async () => {
    render(<KmsManagePage />);
    fireEvent.click(screen.getByText(/적재 완료 문서/));
    await screen.findByText("페이지문서 1");
    // 표 헤더의 "총 23건" — getByText는 동일 텍스트 다수 요소 시 실패하므로 getAllByText 사용
    const totalLabels = screen.getAllByText("총 23건");
    expect(totalLabels.length).toBeGreaterThan(0);
  });

  it("첫 페이지에는 최대 STORED_PAGE(20)건만 표시된다", async () => {
    render(<KmsManagePage />);
    fireEvent.click(screen.getByText(/적재 완료 문서/));
    await screen.findByText("페이지문서 1");
    // 제목 셀만 추출 — 21 stored + 2 stored_partial = 23건이지만 첫 페이지는 20건이어야 함
    const titleCells = screen.getAllByText(/^페이지문서 /);
    expect(titleCells.length).toBeLessThanOrEqual(20);
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
