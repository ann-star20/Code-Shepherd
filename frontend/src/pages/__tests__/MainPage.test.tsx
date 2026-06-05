import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MainPage } from "@/pages/MainPage";
import { DashboardLayout } from "@/components/templates/DashboardLayout";
import { pipelineService } from "@/services/pipelineService";
import { stagingService } from "@/services/stagingService";
import { graphService } from "@/services/graphService";
import type { GraphNode } from "@/types/graph";

vi.mock("react-force-graph-2d", () => ({
  default: ({
    graphData,
    onNodeClick,
  }: {
    graphData: { nodes: Array<{ id: string; name: string }> };
    onNodeClick: (n: unknown) => void;
  }) => (
    <div data-testid="force-graph">
      {graphData.nodes.map((n) => (
        <button key={n.id} data-testid={`node-btn-${n.id}`} onClick={() => onNodeClick(n)}>
          {n.name}
        </button>
      ))}
    </div>
  ),
}));

vi.mock("@/services/pipelineService", () => ({
  pipelineService: {
    prescan: vi.fn(),
    trigger: vi.fn(),
  },
}));
vi.mock("@/services/stagingService", () => ({
  stagingService: {
    getDraft: vi.fn(),
    getDiff: vi.fn(),
    approveAll: vi.fn(),
    rejectAll: vi.fn(),
    patchNode: vi.fn(),
  },
}));
vi.mock("@/services/graphService", () => ({
  graphService: { getTopology: vi.fn() },
}));

class MockEventSource {
  addEventListener = vi.fn();
  close = vi.fn();
  onerror: ((e: Event) => void) | null = null;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("EventSource", MockEventSource);
  vi.mocked(pipelineService.prescan).mockResolvedValue({
    confidence: 0.9,
    framework: "React",
    version: "18",
    lang: "TypeScript",
  });
  vi.mocked(pipelineService.trigger).mockResolvedValue({ session_id: "ses-1" });
  vi.mocked(stagingService.getDraft).mockResolvedValue([]);
  vi.mocked(stagingService.getDiff).mockResolvedValue({ draft: 0, approved: 0, committed: 0 });
  vi.mocked(graphService.getTopology).mockResolvedValue({ nodes: [], edges: [] });
});

describe("DashboardLayout", () => {
  it("T_F12_three_panels: renders all 3 panel slots", () => {
    render(
      <DashboardLayout
        sidebar={<div data-testid="s" />}
        main={<div data-testid="m" />}
        inspector={<div data-testid="i" />}
      />
    );
    expect(screen.getByTestId("s")).toBeTruthy();
    expect(screen.getByTestId("m")).toBeTruthy();
    expect(screen.getByTestId("i")).toBeTruthy();
  });
});

describe("MainPage", () => {
  it("T_F12_layout_renders: renders without error", async () => {
    render(<MainPage />);
    await waitFor(() => expect(screen.getByTestId("force-graph")).toBeTruthy());
  });

  it("T_F12_trigger_flow: trigger pipeline after adding URL and confirming", async () => {
    const user = userEvent.setup();
    render(<MainPage />);

    const urlInput = screen.getByPlaceholderText("URL 입력");
    await user.type(urlInput, "https://example.com/docs");
    await user.click(screen.getByRole("button", { name: "URL 추가" }));

    await waitFor(() =>
      expect(pipelineService.prescan).toHaveBeenCalledWith("https://example.com/docs")
    );

    await user.click(screen.getByRole("button", { name: "확인" }));
    await user.click(screen.getByRole("button", { name: "파이프라인 시작" }));

    await waitFor(() => expect(pipelineService.trigger).toHaveBeenCalledTimes(1));
  });

  it("T_F12_node_select: clicking node hides guide text (inspector activated)", async () => {
    const node: GraphNode = {
      id: "n1",
      name: "Buffer Overflow",
      domain: "security",
      status: "COMMITTED",
    };
    vi.mocked(graphService.getTopology).mockResolvedValue({ nodes: [node], edges: [] });

    render(<MainPage />);
    expect(screen.getByText("노드를 클릭하세요")).toBeTruthy();

    await waitFor(() => screen.getByTestId("node-btn-n1"));
    await userEvent.click(screen.getByTestId("node-btn-n1"));

    expect(screen.queryByText("노드를 클릭하세요")).toBeNull();
  });
});
