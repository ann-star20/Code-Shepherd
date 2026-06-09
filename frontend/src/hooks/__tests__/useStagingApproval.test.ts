import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useStagingApproval } from "@/hooks/useStagingApproval";
import { stagingService } from "@/services/stagingService";

vi.mock("@/services/stagingService", () => ({
  stagingService: {
    getDraft:    vi.fn(),
    getDiff:     vi.fn(),
    approveAll:  vi.fn(),
    rejectAll:   vi.fn(),
    patchNode:   vi.fn(),
  },
}));

const makeDraftRecord = (id: string) => ({
  id,
  state: "DRAFT" as const,
  concept_json: {
    concept_name: `Concept_${id}`,
    domains: ["security"],
    aliases: [],
  },
});

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(stagingService.getDraft).mockResolvedValue([]);
  vi.mocked(stagingService.getDiff).mockResolvedValue({ draft: 0, approved: 0, committed: 0 });
  vi.mocked(stagingService.approveAll).mockResolvedValue({ approved: 3 });
  vi.mocked(stagingService.rejectAll).mockResolvedValue({ rejected: 2 });
  vi.mocked(stagingService.patchNode).mockResolvedValue(undefined);
});

describe("useStagingApproval", () => {
  it("T_F8_load_records: getDraft returns 3 records → records.length === 3", async () => {
    vi.mocked(stagingService.getDraft).mockResolvedValue([
      makeDraftRecord("1"), makeDraftRecord("2"), makeDraftRecord("3"),
    ]);
    const { result } = renderHook(() => useStagingApproval("sess1"));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.records).toHaveLength(3);
  });

  it("T_F8_approve_all: approveAll calls stagingService.approveAll once", async () => {
    const { result } = renderHook(() => useStagingApproval("sess1"));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => { await result.current.approveAll(); });
    expect(stagingService.approveAll).toHaveBeenCalledTimes(1);
    expect(stagingService.approveAll).toHaveBeenCalledWith("sess1");
  });

  it("T_F8_reject_all: rejectAll calls stagingService.rejectAll once", async () => {
    const { result } = renderHook(() => useStagingApproval("sess1"));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => { await result.current.rejectAll(); });
    expect(stagingService.rejectAll).toHaveBeenCalledTimes(1);
    expect(stagingService.rejectAll).toHaveBeenCalledWith("sess1");
  });

  it("T_F8_patch_node: patchNode calls stagingService.patchNode with correct args", async () => {
    const { result } = renderHook(() => useStagingApproval("sess1"));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    await act(async () => { await result.current.patchNode("id1", "APPROVED"); });
    expect(stagingService.patchNode).toHaveBeenCalledWith("sess1", "id1", "APPROVED");
  });

  it("T_F8_null_session: null → empty records, no service calls", async () => {
    const { result } = renderHook(() => useStagingApproval(null));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.records).toHaveLength(0);
    expect(stagingService.getDraft).not.toHaveBeenCalled();
  });
});
