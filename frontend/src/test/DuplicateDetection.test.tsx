/**
 * FE TDD — SHA256 중복 감지 + DuplicateModal
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { checkDuplicate } from "../lib/kmsApi";
import { DuplicateModal } from "../components/DuplicateModal";

// ── FE-2: checkDuplicate API 함수 ─────────────────────────────────────────────

describe("checkDuplicate API", () => {
  it("kmsApi에 checkDuplicate 함수가 존재한다", () => {
    expect(typeof checkDuplicate).toBe("function");
  });
});

// ── FE-3: DuplicateModal 컴포넌트 ─────────────────────────────────────────────

describe("DuplicateModal — identical 케이스", () => {
  const identicalDoc = {
    doc_id: "doc-001",
    original_filename: "사내정책.pdf",
    upload_status: "stored",
    created_at: "2026-06-01T00:00:00",
  };

  it("동일 문서 경고 메시지를 표시한다", () => {
    render(
      <DuplicateModal
        type="identical"
        existingDoc={identicalDoc}
        onKeepExisting={vi.fn()}
        onReupload={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.getByText(/이미 동일한 파일/)).toBeInTheDocument();
  });

  it("[기존 문서 보기] 버튼이 존재한다", () => {
    render(
      <DuplicateModal
        type="identical"
        existingDoc={{ ...identicalDoc, created_at: null }}
        onKeepExisting={vi.fn()}
        onReupload={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.getByText(/기존 문서 보기/)).toBeInTheDocument();
  });

  it("[그래도 재업로드] 버튼 클릭 시 onReupload가 호출된다", () => {
    const onReupload = vi.fn();
    render(
      <DuplicateModal
        type="identical"
        existingDoc={{ ...identicalDoc, created_at: null }}
        onKeepExisting={vi.fn()}
        onReupload={onReupload}
        onCancel={vi.fn()}
      />
    );
    fireEvent.click(screen.getByText(/그래도 재업로드/));
    expect(onReupload).toHaveBeenCalledTimes(1);
  });
});

describe("DuplicateModal — modified 케이스", () => {
  const modifiedDoc = {
    doc_id: "doc-002",
    original_filename: "기존_문서.pdf",
    upload_status: "stored",
    created_at: "2026-05-15T00:00:00",
  };

  it("수정본 안내 메시지를 표시한다", () => {
    render(
      <DuplicateModal
        type="modified"
        existingDoc={modifiedDoc}
        onKeepExisting={vi.fn()}
        onReplace={vi.fn()}
        onAddNew={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    expect(screen.getByText(/같은 파일명.*수정된 내용/)).toBeInTheDocument();
  });

  it("[기존 버전 교체] 버튼 클릭 시 onReplace가 호출된다", () => {
    const onReplace = vi.fn();
    render(
      <DuplicateModal
        type="modified"
        existingDoc={{ ...modifiedDoc, created_at: null }}
        onKeepExisting={vi.fn()}
        onReplace={onReplace}
        onAddNew={vi.fn()}
        onCancel={vi.fn()}
      />
    );
    fireEvent.click(screen.getByText(/기존 버전 교체/));
    expect(onReplace).toHaveBeenCalledTimes(1);
  });

  it("[새 버전으로 추가] 버튼 클릭 시 onAddNew가 호출된다", () => {
    const onAddNew = vi.fn();
    render(
      <DuplicateModal
        type="modified"
        existingDoc={{ ...modifiedDoc, created_at: null }}
        onKeepExisting={vi.fn()}
        onReplace={vi.fn()}
        onAddNew={onAddNew}
        onCancel={vi.fn()}
      />
    );
    fireEvent.click(screen.getByText(/새 버전으로 추가/));
    expect(onAddNew).toHaveBeenCalledTimes(1);
  });
});

// ── FE-4: DocumentUpload 분기 ────────────────────────────────────────────────

vi.mock("../lib/kmsApi", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/kmsApi")>();
  return {
    ...actual,
    checkDuplicate: vi.fn().mockResolvedValue({ status: "new", existing_doc: null }),
    uploadDocument: vi.fn().mockResolvedValue({
      doc_id: "new-001", status: "processing", message: "ok", hitl_required: false, chunk_count: 0,
    }),
    listDocuments: vi.fn().mockResolvedValue({ docs: [], total: 0, limit: 20, offset: 0 }),
    replaceDocument: vi.fn().mockResolvedValue({
      new_doc_id: "new-002", old_doc_id: "old-001", status: "processing", message: "ok",
    }),
  };
});

vi.mock("../lib/hitlApi", () => ({
  listHitlQueue: vi.fn().mockResolvedValue({ items: [], total: 0, limit: 20, offset: 0 }),
}));

vi.mock("../lib/fileHash", () => ({
  computeFileHash: vi.fn().mockResolvedValue("abc123" + "0".repeat(58)),
}));

import { DocumentUpload } from "../components/DocumentUpload";

describe("DocumentUpload — duplicate check flow", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("파일 선택 후 new 케이스면 모달 없이 업로드 진행", async () => {
    const { checkDuplicate: mockCheck, uploadDocument: mockUpload } = await import("../lib/kmsApi");
    (mockCheck as ReturnType<typeof vi.fn>).mockResolvedValue({ status: "new", existing_doc: null });

    render(<DocumentUpload />);

    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["content"], "새로운.pdf")] } });

    await waitFor(() => {
      expect(screen.queryByText(/이미 동일한 파일/)).toBeNull();
      expect(screen.queryByText(/같은 파일명/)).toBeNull();
    }, { timeout: 3000 });

    expect(mockUpload).toHaveBeenCalled();
  });

  it("identical 케이스면 DuplicateModal이 표시된다", async () => {
    const { checkDuplicate: mockCheck } = await import("../lib/kmsApi");
    (mockCheck as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: "identical",
      existing_doc: { doc_id: "doc-001", original_filename: "test.pdf", upload_status: "stored", created_at: null },
    });

    render(<DocumentUpload />);

    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["x"], "test.pdf")] } });

    await waitFor(() => {
      expect(screen.getByText(/이미 동일한 파일/)).toBeInTheDocument();
    }, { timeout: 3000 });
  });

  it("modified 케이스면 수정본 모달이 표시된다", async () => {
    const { checkDuplicate: mockCheck } = await import("../lib/kmsApi");
    (mockCheck as ReturnType<typeof vi.fn>).mockResolvedValue({
      status: "modified",
      existing_doc: { doc_id: "doc-002", original_filename: "기존.pdf", upload_status: "stored", created_at: null },
    });

    render(<DocumentUpload />);

    const input = document.querySelector("input[type=file]") as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["changed"], "기존.pdf")] } });

    await waitFor(() => {
      expect(screen.getByText(/같은 파일명.*수정된 내용/)).toBeInTheDocument();
    }, { timeout: 3000 });
  });
});
