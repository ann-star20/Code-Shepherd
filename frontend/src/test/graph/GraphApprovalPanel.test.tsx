import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { GraphApprovalPanel } from "@/components/GraphApprovalPanel";
import type { DiffSummary } from "@/types/graphPipeline";

describe("GraphApprovalPanel", () => {
  const mockDiff: DiffSummary = { draft: 3, approved: 1, committed: 5 };

  it("diff가 null이면 '로딩 중...' 표시", () => {
    // Arrange / Act
    render(
      <GraphApprovalPanel
        diff={null}
        isLoading={false}
        onApproveAll={vi.fn()}
        onRejectAll={vi.fn()}
      />
    );
    // Assert
    expect(screen.getByText("로딩 중...")).toBeInTheDocument();
  });

  it("diff 데이터로 신규/업데이트/병합 수치 렌더링", () => {
    // Arrange / Act
    render(
      <GraphApprovalPanel
        diff={mockDiff}
        isLoading={false}
        onApproveAll={vi.fn()}
        onRejectAll={vi.fn()}
      />
    );
    // Assert
    expect(screen.getByText("3")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("5")).toBeInTheDocument();
  });

  it("전체 승인 버튼 클릭 시 onApproveAll 호출", async () => {
    // Arrange
    const onApproveAll = vi.fn();
    render(
      <GraphApprovalPanel
        diff={mockDiff}
        isLoading={false}
        onApproveAll={onApproveAll}
        onRejectAll={vi.fn()}
      />
    );
    // Act
    await userEvent.click(screen.getByText("전체 승인"));
    // Assert
    expect(onApproveAll).toHaveBeenCalledOnce();
  });

  it("isLoading=true일 때 버튼 비활성화 및 스피너 표시", () => {
    // Arrange / Act
    render(
      <GraphApprovalPanel
        diff={mockDiff}
        isLoading={true}
        onApproveAll={vi.fn()}
        onRejectAll={vi.fn()}
      />
    );
    // Assert
    const approveBtn = screen.getByText("전체 승인");
    const rejectBtn  = screen.getByText("전체 거부");
    expect(approveBtn).toBeDisabled();
    expect(rejectBtn).toBeDisabled();
    expect(document.querySelector(".animate-spin")).toBeInTheDocument();
  });
});
