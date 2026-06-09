import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { TopologyViewer } from "@/components/organisms/TopologyViewer";
import { graphService } from "@/services/graphService";
import { stagingService } from "@/services/stagingService";
import { getNodeStyle } from "@/utils/nodeStyler";
import type { GraphNode } from "@/types/graph";
import type { StagingRecord } from "@/services/stagingService";

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

// 새 스펙: concept_name / domains[] 사용
const makeDraftRecord = (id: string, concept_name: string, domains = ["security"]): StagingRecord => ({
  id,
  state: "DRAFT",
  concept_json: {
    concept_name,
    domains,
    aliases: [],
    concept_type: "vulnerability_root_cause",
    severity: "medium",
  },
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

  it("T_F10_node_count: 3 confirmed + 2 draft(no alias match) = 5 merged nodes", async () => {
    const confirmed = [makeNode("1", "A"), makeNode("2", "B"), makeNode("3", "C")];
    const draft: StagingRecord[] = [
      makeDraftRecord("4", "D"),
      makeDraftRecord("5", "E", ["performance"]),
    ];
    vi.mocked(graphService.getTopology).mockResolvedValue({ nodes: confirmed, edges: [] });
    vi.mocked(stagingService.getDraft).mockResolvedValue(draft);

    render(<TopologyViewer sessionId="sid" onNodeClick={vi.fn()} />);
    await waitFor(() => {
      const fg = screen.getByTestId("force-graph");
      // data-nodes attribute reflects merged count
      expect(Number(fg.getAttribute("data-nodes"))).toBe(5);
    });
  });

  it("T_F10_draft_style: DRAFT opacity === 0.65", () => {
    expect(getNodeStyle("DRAFT", "security").opacity).toBe(0.65);
  });
});
