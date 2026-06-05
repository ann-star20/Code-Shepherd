import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useGraphMerge } from "@/hooks/useGraphMerge";
import { graphService } from "@/services/graphService";
import { stagingService } from "@/services/stagingService";

vi.mock("@/services/graphService", () => ({
  graphService: { getTopology: vi.fn() },
}));
vi.mock("@/services/stagingService", () => ({
  stagingService: { getDraft: vi.fn() },
}));

const CONFIRMED_NODES = [
  { id: "1", name: "SQLi", domain: "security" as const, status: "COMMITTED" as const },
];

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(graphService.getTopology).mockResolvedValue({ nodes: CONFIRMED_NODES, edges: [] });
  vi.mocked(stagingService.getDraft).mockResolvedValue([]);
});

describe("useGraphMerge", () => {
  it("T_F7_no_session: null sessionId → only confirmed nodes", async () => {
    const { result } = renderHook(() => useGraphMerge(null));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.nodes).toHaveLength(1);
    expect(result.current.nodes[0].name).toBe("SQLi");
  });
});
