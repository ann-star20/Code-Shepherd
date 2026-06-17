import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useGraphStagingApproval } from "@/hooks/useGraphStagingApproval";
import { graphPipelineApi } from "@/lib/graphPipelineApi";
import type { StagingConcept } from "@/types/graphPipeline";

vi.mock("@/lib/graphPipelineApi", () => ({
  graphPipelineApi: {
    getStaging: vi.fn(),
    getDiff: vi.fn(),
    approveAll: vi.fn(),
    rejectAll: vi.fn(),
    approveSingle: vi.fn(),
    rejectSingle: vi.fn(),
    commit: vi.fn(),
  },
}));

const mockItems: StagingConcept[] = [
  {
    id: "concept-1",
    name: "New Concept",
    status: "DRAFT",
    domains: ["security"],
    staging_id: 42,
    state: "DRAFT",
    infer_action: "NEW",
  },
];

function makeAxiosError(status: number) {
  return Object.assign(new Error("request failed"), {
    isAxiosError: true,
    response: { status },
  });
}

describe("useGraphStagingApproval", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  async function setupWithStagingItems() {
    vi.mocked(graphPipelineApi.getStaging).mockResolvedValue({
      data: { items: mockItems },
    } as never);
    vi.mocked(graphPipelineApi.getDiff).mockResolvedValue({
      data: { draft: 1, approved: 0, committed: 0 },
    } as never);

    const onToast = vi.fn();
    const { result } = renderHook(() =>
      useGraphStagingApproval({ sessionId: "sess-1", onToast })
    );
    await act(async () => {
      await result.current.fetchStaging();
    });
    return { result, onToast };
  }

  it("approveSingle 호출 시 즉시 stagingItems의 해당 항목 state가 APPROVED로 변경", async () => {
    // Arrange
    vi.mocked(graphPipelineApi.approveSingle).mockResolvedValue({} as never);
    const { result } = await setupWithStagingItems();

    // Act
    await act(async () => {
      await result.current.approveSingle(42);
    });

    // Assert
    expect(result.current.stagingItems[0].state).toBe("APPROVED");
  });

  it("approveSingle 성공 시 onToast('success', ...) 호출", async () => {
    // Arrange
    vi.mocked(graphPipelineApi.approveSingle).mockResolvedValue({} as never);
    const { result, onToast } = await setupWithStagingItems();

    // Act
    await act(async () => {
      await result.current.approveSingle(42);
    });

    // Assert
    expect(onToast).toHaveBeenCalledWith("success", "개념을 승인했습니다.");
  });

  it("approveSingle 409 에러 시 롤백 + onToast('warning', ...) 호출", async () => {
    // Arrange
    vi.mocked(graphPipelineApi.approveSingle).mockRejectedValue(makeAxiosError(409));
    const { result, onToast } = await setupWithStagingItems();

    // Act
    await act(async () => {
      await result.current.approveSingle(42);
    });

    // Assert
    expect(result.current.stagingItems[0].state).toBe("DRAFT");
    expect(onToast).toHaveBeenCalledWith(
      "warning",
      "다른 사용자가 처리 중입니다. 잠시 후 다시 시도해 주세요."
    );
  });

  it("approveSingle 일반 에러 시 롤백 + onToast('error', ...) 호출", async () => {
    // Arrange
    vi.mocked(graphPipelineApi.approveSingle).mockRejectedValue(new Error("network error"));
    const { result, onToast } = await setupWithStagingItems();

    // Act
    await act(async () => {
      await result.current.approveSingle(42);
    });

    // Assert
    expect(result.current.stagingItems[0].state).toBe("DRAFT");
    expect(onToast).toHaveBeenCalledWith("error", "승인 처리에 실패했습니다.");
  });

  it("rejectSingle 호출 시 즉시 stagingItems의 해당 항목 state가 REJECTED로 변경", async () => {
    // Arrange
    vi.mocked(graphPipelineApi.rejectSingle).mockResolvedValue({} as never);
    const { result } = await setupWithStagingItems();

    // Act
    await act(async () => {
      await result.current.rejectSingle(42);
    });

    // Assert
    expect(result.current.stagingItems[0].state).toBe("REJECTED");
  });

  it("rejectSingle 성공 시 onToast('info', ...) 호출", async () => {
    // Arrange
    vi.mocked(graphPipelineApi.rejectSingle).mockResolvedValue({} as never);
    const { result, onToast } = await setupWithStagingItems();

    // Act
    await act(async () => {
      await result.current.rejectSingle(42);
    });

    // Assert
    expect(onToast).toHaveBeenCalledWith("info", "개념을 거부했습니다.");
  });

  it("rejectSingle 409 에러 시 롤백 + onToast('warning', ...) 호출", async () => {
    // Arrange
    vi.mocked(graphPipelineApi.rejectSingle).mockRejectedValue(makeAxiosError(409));
    const { result, onToast } = await setupWithStagingItems();

    // Act
    await act(async () => {
      await result.current.rejectSingle(42);
    });

    // Assert
    expect(result.current.stagingItems[0].state).toBe("DRAFT");
    expect(onToast).toHaveBeenCalledWith(
      "warning",
      "다른 사용자가 처리 중입니다. 잠시 후 다시 시도해 주세요."
    );
  });

  it("rejectSingle 일반 에러 시 롤백 + onToast('error', ...) 호출", async () => {
    // Arrange
    vi.mocked(graphPipelineApi.rejectSingle).mockRejectedValue(new Error("network error"));
    const { result, onToast } = await setupWithStagingItems();

    // Act
    await act(async () => {
      await result.current.rejectSingle(42);
    });

    // Assert
    expect(result.current.stagingItems[0].state).toBe("DRAFT");
    expect(onToast).toHaveBeenCalledWith("error", "거부 처리에 실패했습니다.");
  });
});
