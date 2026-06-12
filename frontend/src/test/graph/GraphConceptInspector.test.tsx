import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { GraphConceptInspector } from "@/components/GraphConceptInspector";
import type { GraphNode } from "@/types/graphPipeline";

const mockNode: GraphNode = {
  id: "node-1",
  name: "SQL Injection",
  status: "COMMITTED",
  domains: ["security"],
  cwe_id: "CWE-89",
  owasp_id: "A03:2021",
  severity: "critical",
  description_ko: "SQL 삽입 공격은 악의적인 SQL 구문을 실행합니다.",
  aliases: ["SQLi"],
  infer_confidence: 0.95,
  mechanisms: [],
};

describe("GraphConceptInspector", () => {
  it("node가 null이면 '노드를 클릭하세요' 가이드 텍스트 표시", () => {
    // Arrange / Act
    render(
      <GraphConceptInspector
        node={null}
        isDraft={false}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onClose={vi.fn()}
      />
    );
    // Assert
    expect(screen.getByText("노드를 클릭하세요")).toBeInTheDocument();
  });

  it("노드 정보 렌더링 — 이름, CWE, OWASP, 설명", () => {
    // Arrange / Act
    render(
      <GraphConceptInspector
        node={mockNode}
        isDraft={false}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onClose={vi.fn()}
      />
    );
    // Assert
    expect(screen.getByText("SQL Injection")).toBeInTheDocument();
    expect(screen.getByText("CWE-89")).toBeInTheDocument();
    expect(screen.getByText("A03:2021")).toBeInTheDocument();
    expect(screen.getByText(/SQL 삽입 공격/)).toBeInTheDocument();
  });

  it("신뢰도 바가 infer_confidence * 100 % 너비로 렌더링", () => {
    // Arrange / Act
    render(
      <GraphConceptInspector
        node={mockNode}
        isDraft={false}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onClose={vi.fn()}
      />
    );
    // Assert
    expect(screen.getByText("95.0%")).toBeInTheDocument();
  });

  it("isDraft=true일 때 승인/거부 버튼 노출", () => {
    // Arrange / Act
    render(
      <GraphConceptInspector
        node={mockNode}
        isDraft={true}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onClose={vi.fn()}
      />
    );
    // Assert
    expect(screen.getByText("승인")).toBeInTheDocument();
    expect(screen.getByText("거부")).toBeInTheDocument();
  });

  it("닫기 버튼 클릭 시 onClose 호출", async () => {
    // Arrange
    const onClose = vi.fn();
    render(
      <GraphConceptInspector
        node={mockNode}
        isDraft={false}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onClose={onClose}
      />
    );
    // Act
    await userEvent.click(screen.getByLabelText("닫기"));
    // Assert
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("mechanisms가 빈 배열이면 '코드 예제 없음' 표시", () => {
    // Arrange / Act
    render(
      <GraphConceptInspector
        node={{ ...mockNode, mechanisms: [] }}
        isDraft={false}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onClose={vi.fn()}
      />
    );
    // Assert
    expect(screen.getByText("코드 예제 없음")).toBeInTheDocument();
  });
});
