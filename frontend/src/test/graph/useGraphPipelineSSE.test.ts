import { renderHook, act, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { useGraphPipelineSSE } from "@/hooks/useGraphPipelineSSE";

class MockEventSource {
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  static instance: MockEventSource;

  constructor() {
    MockEventSource.instance = this;
  }

  close = vi.fn();

  emit(data: object) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }

  open() {
    this.onopen?.();
  }
}

vi.mock("@/lib/graphPipelineApi", () => ({
  graphPipelineApi: {
    subscribeSSE: (_sessionId: string) => {
      return new MockEventSource();
    },
  },
}));

describe("useGraphPipelineSSE", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("sessionId가 null이면 EventSource 생성하지 않음", () => {
    // Arrange / Act
    const { result } = renderHook(() =>
      useGraphPipelineSSE({
        sessionId: null,
        onLog: vi.fn(),
        onFinished: vi.fn(),
        onError: vi.fn(),
      })
    );
    // Assert
    expect(result.current.isConnected).toBe(false);
    expect(MockEventSource.instance).toBeUndefined();
  });

  it("step_update 이벤트 수신 시 stepStatuses 업데이트", async () => {
    // Arrange
    const { result } = renderHook(() =>
      useGraphPipelineSSE({
        sessionId: "sess-123",
        onLog: vi.fn(),
        onFinished: vi.fn(),
        onError: vi.fn(),
      })
    );
    // Act
    act(() => {
      MockEventSource.instance.emit({ type: "step_update", step: "Crawler", status: "DONE" });
    });
    // Assert
    await waitFor(() => {
      expect(result.current.stepStatuses.Crawler).toBe("DONE");
    });
  });

  it("log 이벤트 수신 시 onLog 콜백 호출", async () => {
    // Arrange
    const onLog = vi.fn();
    renderHook(() =>
      useGraphPipelineSSE({
        sessionId: "sess-456",
        onLog,
        onFinished: vi.fn(),
        onError: vi.fn(),
      })
    );
    // Act
    act(() => {
      MockEventSource.instance.emit({ type: "log", agent: "Crawler", message: "크롤링 시작" });
    });
    // Assert
    await waitFor(() => {
      expect(onLog).toHaveBeenCalledWith(expect.stringContaining("크롤링 시작"));
    });
  });

  it("finished 이벤트 수신 시 onFinished 호출 후 EventSource close", async () => {
    // Arrange
    const onFinished = vi.fn();
    renderHook(() =>
      useGraphPipelineSSE({
        sessionId: "sess-789",
        onLog: vi.fn(),
        onFinished,
        onError: vi.fn(),
      })
    );
    // Act
    act(() => {
      MockEventSource.instance.emit({ type: "finished" });
    });
    // Assert
    await waitFor(() => {
      expect(onFinished).toHaveBeenCalledOnce();
      expect(MockEventSource.instance.close).toHaveBeenCalled();
    });
  });
});
