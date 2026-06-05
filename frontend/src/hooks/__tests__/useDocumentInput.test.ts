import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { useDocumentInput } from "@/hooks/useDocumentInput";
import { pipelineService } from "@/services/pipelineService";

vi.mock("@/services/pipelineService", () => ({
  pipelineService: {
    prescan: vi.fn(),
    trigger: vi.fn(),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
});

describe("useDocumentInput", () => {
  it("T_F6_add_url: addUrl appends to urls", async () => {
    vi.mocked(pipelineService.prescan).mockResolvedValue({ confidence: 0.9 });
    const { result } = renderHook(() => useDocumentInput());

    await act(async () => {
      result.current.addUrl("https://test.com");
    });

    expect(result.current.urls).toHaveLength(1);
  });

  it("T_F6_max_5_urls: addUrl beyond 5 is ignored", async () => {
    vi.mocked(pipelineService.prescan).mockResolvedValue({ confidence: 0.9 });
    const { result } = renderHook(() => useDocumentInput());

    await act(async () => {
      for (let i = 0; i < 6; i++) {
        result.current.addUrl(`https://example.com/${i}`);
      }
    });

    expect(result.current.urls).toHaveLength(5);
  });

  it("T_F6_prescan_auto: high confidence sets prescanResult and clears interlock", async () => {
    vi.mocked(pipelineService.prescan).mockResolvedValue({ framework: "Django", confidence: 0.9 });
    const { result } = renderHook(() => useDocumentInput());

    await act(async () => {
      result.current.addUrl("https://docs.djangoproject.com");
    });

    expect(result.current.prescanResult?.framework).toBe("Django");
    expect(result.current.isPending).toBe(false);
  });

  it("T_F6_interlock: low confidence sets isPending=true", async () => {
    vi.mocked(pipelineService.prescan).mockResolvedValue({ confidence: 0.3 });
    const { result } = renderHook(() => useDocumentInput());

    await act(async () => {
      result.current.addUrl("https://example.com");
    });

    expect(result.current.isPending).toBe(true);
  });

  it("T_F6_trigger: calls trigger once and returns session_id", async () => {
    vi.mocked(pipelineService.prescan).mockResolvedValue({ confidence: 0.9 });
    vi.mocked(pipelineService.trigger).mockResolvedValue({ session_id: "test-session" });

    const { result } = renderHook(() => useDocumentInput());

    await act(async () => {
      result.current.addUrl("https://example.com");
    });

    let sessionId = "";
    await act(async () => {
      sessionId = await result.current.triggerPipeline();
    });

    expect(pipelineService.trigger).toHaveBeenCalledTimes(1);
    expect(sessionId).toBe("test-session");
  });
});
