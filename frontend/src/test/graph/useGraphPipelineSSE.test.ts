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

  it("metadata_required 이벤트 수신 시 onMetadataRequired 콜백에 doc_id/url/suggestions 전달", async () => {
    // Arrange
    const onMetadataRequired = vi.fn();
    renderHook(() =>
      useGraphPipelineSSE({
        sessionId: "sess-meta",
        onLog: vi.fn(),
        onFinished: vi.fn(),
        onError: vi.fn(),
        onMetadataRequired,
      })
    );
    // Act
    act(() => {
      MockEventSource.instance.emit({
        type: "metadata_required",
        doc_id: "doc_new123",
        url: "https://docs.astro.build/",
        suggestions: ["Astro", "NestJS"],
      });
    });
    // Assert
    await waitFor(() => {
      expect(onMetadataRequired).toHaveBeenCalledWith({
        doc_id: "doc_new123",
        url: "https://docs.astro.build/",
        suggestions: ["Astro", "NestJS"],
      });
    });
  });

  it("step_update SKIPPED 이벤트 수신 시 onSkipped 콜백에 reason 전달", async () => {
    // Arrange
    const onSkipped = vi.fn();
    const { result } = renderHook(() =>
      useGraphPipelineSSE({
        sessionId: "sess-skip",
        onLog: vi.fn(),
        onFinished: vi.fn(),
        onError: vi.fn(),
        onSkipped,
      })
    );
    // Act
    act(() => {
      MockEventSource.instance.emit({
        type: "step_update",
        agent: "Prescan",
        status: "SKIPPED",
        reason: "이미 처리된 문서입니다 (doc_id=doc_dup123, state=COMMITTED) - 파이프라인을 건너뜁니다.",
      });
    });
    // Assert
    await waitFor(() => {
      expect(result.current.stepStatuses.Input).toBe("PENDING");
      expect(onSkipped).toHaveBeenCalledWith(
        "이미 처리된 문서입니다 (doc_id=doc_dup123, state=COMMITTED) - 파이프라인을 건너뜁니다."
      );
    });
  });

  it("step_update FAILED 이벤트 수신 시 stepStatuses를 FAILED로 갱신하고 onStepFailed에 step/reason 전달", async () => {
    // Arrange
    const onStepFailed = vi.fn();
    const { result } = renderHook(() =>
      useGraphPipelineSSE({
        sessionId: "sess-noconcepts",
        onLog: vi.fn(),
        onFinished: vi.fn(),
        onError: vi.fn(),
        onStepFailed,
      })
    );
    // Act
    act(() => {
      MockEventSource.instance.emit({
        type: "step_update",
        step: "Extractor",
        status: "FAILED",
        reason: "해당 페이지의 본문에서 분석 가능한 핵심 개념(안티패턴/약점)을 찾지 못했습니다.",
      });
    });
    // Assert
    await waitFor(() => {
      expect(result.current.stepStatuses.Extractor).toBe("FAILED");
      expect(onStepFailed).toHaveBeenCalledWith(
        "Extractor",
        "해당 페이지의 본문에서 분석 가능한 핵심 개념(안티패턴/약점)을 찾지 못했습니다."
      );
    });
  });
});
