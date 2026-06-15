import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { GraphApprovalPanel } from "@/components/GraphApprovalPanel";
import type { DiffSummary, StagingConcept } from "@/types/graphPipeline";

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

  it("stagingItems의 infer_action별로 신규/업데이트/병합 수치 렌더링", () => {
    // Arrange
    const stagingItems: StagingConcept[] = [
      { id: "c1", staging_id: 1, name: "A", status: "DRAFT", domains: ["security"], state: "DRAFT", infer_action: "NEW" },
      { id: "c2", staging_id: 2, name: "B", status: "DRAFT", domains: ["security"], state: "DRAFT", infer_action: "NEW" },
      { id: "c3", staging_id: 3, name: "C", status: "DRAFT", domains: ["security"], state: "DRAFT", infer_action: "RELATED_TO", target_concept_name: "X" },
      { id: "c4", staging_id: 4, name: "D", status: "DRAFT", domains: ["security"], state: "DRAFT", infer_action: "MERGE", target_concept_name: "Y" },
      { id: "c5", staging_id: 5, name: "E", status: "DRAFT", domains: ["security"], state: "DRAFT", infer_action: "MERGE", target_concept_name: "Z" },
      { id: "c6", staging_id: 6, name: "F", status: "DRAFT", domains: ["security"], state: "DRAFT", infer_action: "MERGE", target_concept_name: "W" },
    ];

    // Act
    render(
      <GraphApprovalPanel
        diff={mockDiff}
        isLoading={false}
        stagingItems={stagingItems}
        onApproveAll={vi.fn()}
        onRejectAll={vi.fn()}
      />
    );

    // Assert
    expect(screen.getByText("2")).toBeInTheDocument();
    expect(screen.getByText("1")).toBeInTheDocument();
    expect(screen.getByText("3")).toBeInTheDocument();
  });

  it("스테이징 항목 클릭 시 onSelectItem 호출", async () => {
    // Arrange
    const onSelectItem = vi.fn();
    const stagingItems: StagingConcept[] = [
      {
        id: "concept-1",
        staging_id: 1,
        name: "CsrfProtection",
        status: "DRAFT",
        domains: ["security"],
        state: "DRAFT",
        infer_action: "NEW",
        infer_confidence: 0.92,
      },
    ];
    render(
      <GraphApprovalPanel
        diff={mockDiff}
        isLoading={false}
        stagingItems={stagingItems}
        onApproveAll={vi.fn()}
        onRejectAll={vi.fn()}
        onSelectItem={onSelectItem}
      />
    );

    // Act
    await userEvent.click(screen.getByText("CsrfProtection"));

    // Assert
    expect(onSelectItem).toHaveBeenCalledWith(stagingItems[0]);
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

  it("stagingItems가 있으면 개념 이름과 NEW/MERGE/RELATED_TO 뱃지를 미리보기 리스트로 렌더링", () => {
    // Arrange
    const stagingItems: StagingConcept[] = [
      {
        id: "concept-1",
        staging_id: 1,
        name: "CsrfProtection",
        status: "DRAFT",
        domains: ["security"],
        state: "DRAFT",
        infer_action: "NEW",
        infer_confidence: 0.92,
      },
      {
        id: "concept-2",
        staging_id: 2,
        name: "SqlInjection",
        status: "DRAFT",
        domains: ["security"],
        state: "DRAFT",
        infer_action: "MERGE",
        target_concept_name: "InjectionAttack",
      },
    ];
    // Act
    render(
      <GraphApprovalPanel
        diff={mockDiff}
        isLoading={false}
        stagingItems={stagingItems}
        onApproveAll={vi.fn()}
        onRejectAll={vi.fn()}
      />
    );
    // Assert
    expect(screen.getByText("CsrfProtection")).toBeInTheDocument();
    expect(screen.getByText("SqlInjection")).toBeInTheDocument();
    expect(screen.getByText("NEW (92.0%)")).toBeInTheDocument();
    expect(screen.getByText("MERGE → InjectionAttack")).toBeInTheDocument();
  });

  it("stagingItems가 비어있으면 미리보기 리스트를 렌더링하지 않음", () => {
    // Arrange / Act
    render(
      <GraphApprovalPanel
        diff={mockDiff}
        isLoading={false}
        stagingItems={[]}
        onApproveAll={vi.fn()}
        onRejectAll={vi.fn()}
      />
    );
    // Assert
    expect(document.querySelector("ul")).not.toBeInTheDocument();
  });
});
