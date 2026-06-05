import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { TopologyViewer } from "@/components/organisms/TopologyViewer";
import { graphService } from "@/services/graphService";
import { stagingService } from "@/services/stagingService";
import { mergeVirtualGraph } from "@/utils/mergeVirtualGraph";
import { getNodeStyle } from "@/utils/nodeStyler";
import type { GraphNode } from "@/types/graph";

// react-force-graph-2d는 Canvas 기반 — jsdom에서 stub
vi.mock("react-force-graph-2d", () => ({
  default: ({ graphData }: { graphData: { nodes: unknown[]; links: unknown[] } }) => (
    <div data-testid="force-graph" data-nodes={graphData.nodes.length} />
  ),
}));

vi.mock("@/services/graphService", () => ({
  graphService: { getTopology: vi.fn() },
}));
vi.mock("@/services/stagingService", () => ({
  stagingService: { getDraft: vi.fn() },
}));

const makeNode = (id: string, name: string): GraphNode => ({
  id, name, domain: "security", status: "COMMITTED",
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(graphService.getTopology).mockResolvedValue({ nodes: [], edges: [] });
  vi.mocked(stagingService.getDraft).mockResolvedValue([]);
});

describe("TopologyViewer", () => {
  it("T_F10_renders: renders without error", async () => {
    render(<TopologyViewer sessionId="sid" onNodeClick={vi.fn()} />);
    await waitFor(() => expect(screen.getByTestId("force-graph")).toBeTruthy());
  });

  it("T_F10_loading: shows spinner while loading", () => {
    vi.mocked(graphService.getTopology).mockImplementation(
      () => new Promise(() => {})  // never resolves
    );
    render(<TopologyViewer sessionId="sid" onNodeClick={vi.fn()} />);
    expect(document.querySelector("[data-testid='spinner']")).toBeTruthy();
  });

  it("T_F10_node_count: 3 confirmed + 2 draft = 5 merged nodes", () => {
    const confirmed = [makeNode("1","A"), makeNode("2","B"), makeNode("3","C")];
    const draft = [
      { id:"4", state:"DRAFT" as const, concept_json:{ id:"4", name:"D", domain:"security" as const, status:"DRAFT" as const, aliases:[], tags:[] } },
      { id:"5", state:"DRAFT" as const, concept_json:{ id:"5", name:"E", domain:"performance" as const, status:"DRAFT" as const, aliases:[], tags:[] } },
    ];
    const { nodes } = mergeVirtualGraph(confirmed, draft);
    expect(nodes).toHaveLength(5);
  });

  it("T_F10_draft_style: DRAFT opacity === 0.65", () => {
    expect(getNodeStyle("DRAFT", "security").opacity).toBe(0.65);
  });
});
