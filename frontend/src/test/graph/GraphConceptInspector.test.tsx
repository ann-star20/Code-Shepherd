import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { GraphConceptInspector } from "@/components/GraphConceptInspector";
import type { GraphEdge, GraphNode } from "@/types/graphPipeline";

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

  it("Concept 노드의 근본 원인, 메커니즘, 코드 예제 뱃지 렌더링", () => {
    // Arrange
    const conceptNode: GraphNode = {
      ...mockNode,
      id: "XSS",
      name: "XSS",
      node_type: "Concept",
      root_cause: "unsanitized_input",
    };
    const allNodes: GraphNode[] = [
      conceptNode,
      {
        id: "mechanism:output_encoding",
        name: "output_encoding",
        node_type: "Mechanism",
        status: "COMMITTED",
      } as GraphNode,
      {
        id: "codeexample:output_encoding_python_3.11_django_4.2",
        name: "output_encoding_python_3.11_django_4.2",
        node_type: "CodeExample",
        status: "COMMITTED",
        lang: "python",
        framework: "django",
      } as GraphNode,
    ];
    const edges: GraphEdge[] = [
      { source: "XSS", target: "mechanism:output_encoding", type: "MITIGATED_BY" },
      {
        source: "mechanism:output_encoding",
        target: "codeexample:output_encoding_python_3.11_django_4.2",
        type: "HAS_EXAMPLE",
      },
    ];

    // Act
    render(
      <GraphConceptInspector
        node={conceptNode}
        allNodes={allNodes}
        edges={edges}
        isDraft={false}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onClose={vi.fn()}
      />
    );

    // Assert
    expect(screen.getByText("unsanitized_input")).toBeInTheDocument();
    expect(screen.getByText("output_encoding")).toBeInTheDocument();
    expect(screen.getByText("python/django")).toBeInTheDocument();
  });

  it("allNodes/edges로 연결된 CodeExample 노드에 code가 있으면 코드 블록으로 렌더링", () => {
    // Arrange
    const conceptNode: GraphNode = {
      ...mockNode,
      id: "XSS",
      name: "XSS",
      node_type: "Concept",
      root_cause: "unsanitized_input",
    };
    const allNodes: GraphNode[] = [
      conceptNode,
      {
        id: "mechanism:output_encoding",
        name: "output_encoding",
        node_type: "Mechanism",
        status: "COMMITTED",
      } as GraphNode,
      {
        id: "codeexample:output_encoding_python_3.11_django_4.2",
        name: "output_encoding_python_3.11_django_4.2",
        node_type: "CodeExample",
        status: "COMMITTED",
        lang: "python",
        framework: "django",
        code: "escape(user_input)",
        description: "사용자 입력을 이스케이프 처리",
      } as GraphNode,
    ];
    const edges: GraphEdge[] = [
      { source: "XSS", target: "mechanism:output_encoding", type: "MITIGATED_BY" },
      {
        source: "mechanism:output_encoding",
        target: "codeexample:output_encoding_python_3.11_django_4.2",
        type: "HAS_EXAMPLE",
      },
    ];

    // Act
    render(
      <GraphConceptInspector
        node={conceptNode}
        allNodes={allNodes}
        edges={edges}
        isDraft={false}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onClose={vi.fn()}
      />
    );

    // Assert
    expect(screen.getByText("output_encoding")).toBeInTheDocument();
    expect(screen.getByText("python/django")).toBeInTheDocument();
    expect(screen.getByText("escape(user_input)")).toBeInTheDocument();
    expect(screen.getByText("사용자 입력을 이스케이프 처리")).toBeInTheDocument();
  });

  it("mechanisms에 code_examples가 있으면 코드 블록으로 렌더링", () => {
    // Arrange
    const nodeWithCode: GraphNode = {
      ...mockNode,
      node_type: "Concept",
      mechanisms: [
        {
          mechanism_name: "output_encoding",
          code_examples: [
            {
              lang: "python",
              lang_version: "3.11",
              framework: "django",
              code: "escape(user_input)",
              description: "사용자 입력을 이스케이프 처리",
            },
          ],
        },
      ],
    };

    // Act
    render(
      <GraphConceptInspector
        node={nodeWithCode}
        isDraft={false}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onClose={vi.fn()}
      />
    );

    // Assert
    expect(screen.getByText("output_encoding")).toBeInTheDocument();
    expect(screen.getByText("escape(user_input)")).toBeInTheDocument();
    expect(screen.getByText("python/django")).toBeInTheDocument();
    expect(screen.getByText("사용자 입력을 이스케이프 처리")).toBeInTheDocument();
  });

  it("node.is_new=true이면 'NEW' 배지 렌더링", () => {
    // Arrange / Act
    render(
      <GraphConceptInspector
        node={{ ...mockNode, is_new: true }}
        isDraft={false}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onClose={vi.fn()}
      />
    );
    // Assert
    expect(screen.getByText("NEW")).toBeInTheDocument();
  });

  it("node.is_new=false/undefined이면 'NEW' 배지 미표시", () => {
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
    expect(screen.queryByText("NEW")).not.toBeInTheDocument();
  });

  it("Concept 노드에 MITIGATED_BY 엣지가 없으면 안내 문구 표시", () => {
    // Arrange
    const conceptNode: GraphNode = {
      ...mockNode,
      id: "XSS",
      name: "XSS",
      node_type: "Concept",
    };

    // Act
    render(
      <GraphConceptInspector
        node={conceptNode}
        allNodes={[conceptNode]}
        edges={[]}
        isDraft={false}
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onClose={vi.fn()}
      />
    );

    // Assert
    expect(screen.getByText("등록된 메커니즘이 없습니다")).toBeInTheDocument();
  });
});
