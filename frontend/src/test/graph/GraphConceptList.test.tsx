import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { GraphConceptList } from "@/components/GraphConceptList";
import type { GraphNode } from "@/types/graphPipeline";

const nodes: GraphNode[] = [
  {
    id: "XSS",
    name: "XSS",
    node_type: "Concept",
    status: "COMMITTED",
    domains: ["security"],
  } as GraphNode,
  {
    id: "SlowQuery",
    name: "SlowQuery",
    node_type: "Concept",
    status: "COMMITTED",
    domains: ["performance"],
  } as GraphNode,
  {
    id: "mechanism:output_encoding",
    name: "output_encoding",
    node_type: "Mechanism",
    status: "COMMITTED",
  } as GraphNode,
];

describe("GraphConceptList", () => {
  it("Concept 타입 노드만 목록에 표시", () => {
    // Arrange / Act
    render(
      <GraphConceptList
        nodes={nodes}
        selectedDomain="all"
        selectedConceptId={null}
        onSelect={vi.fn()}
      />
    );

    // Assert
    expect(screen.getByRole("button", { name: "XSS" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "SlowQuery" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "output_encoding" })).not.toBeInTheDocument();
  });

  it("선택된 도메인으로 목록을 필터링", () => {
    // Arrange / Act
    render(
      <GraphConceptList
        nodes={nodes}
        selectedDomain="performance"
        selectedConceptId={null}
        onSelect={vi.fn()}
      />
    );

    // Assert
    expect(screen.getByRole("button", { name: "SlowQuery" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "XSS" })).not.toBeInTheDocument();
  });

  it("항목 클릭 시 onSelect가 노드 id로 호출됨", async () => {
    // Arrange
    const onSelect = vi.fn();
    render(
      <GraphConceptList
        nodes={nodes}
        selectedDomain="all"
        selectedConceptId={null}
        onSelect={onSelect}
      />
    );

    // Act
    await userEvent.click(screen.getByRole("button", { name: "XSS" }));

    // Assert
    expect(onSelect).toHaveBeenCalledWith("XSS");
  });

  it("일치하는 개념이 없으면 안내 문구를 표시", () => {
    // Arrange / Act
    render(
      <GraphConceptList
        nodes={[]}
        selectedDomain="all"
        selectedConceptId={null}
        onSelect={vi.fn()}
      />
    );

    // Assert
    expect(screen.getByText("개념이 없습니다")).toBeInTheDocument();
  });
});
