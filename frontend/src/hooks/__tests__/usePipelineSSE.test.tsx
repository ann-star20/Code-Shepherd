import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { usePipelineSSE } from "@/hooks/usePipelineSSE";

class MockEventSource {
  static registry: MockEventSource[] = [];
  url: string;
  private handlers = new Map<string, ((e: Event) => void)[]>();
  closeCalled = false;

  constructor(url: string) {
    this.url = url;
    MockEventSource.registry.push(this);
  }

  addEventListener(type: string, handler: (e: Event) => void) {
    if (!this.handlers.has(type)) this.handlers.set(type, []);
    this.handlers.get(type)!.push(handler);
  }

  fire(type: string, data: string) {
    const event = new MessageEvent(type, { data });
    this.handlers.get(type)?.forEach((h) => h(event));
  }

  close() {
    this.closeCalled = true;
  }
}

beforeEach(() => {
  MockEventSource.registry = [];
  vi.stubGlobal("EventSource", MockEventSource);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("usePipelineSSE", () => {
  it("T_F5_no_session: null sessionId → not connected, empty logs", () => {
    const { result } = renderHook(() => usePipelineSSE(null));
    expect(result.current.isConnected).toBe(false);
    expect(result.current.logs).toHaveLength(0);
  });

  it("T_F5_log_appended: log event appends to logs array", async () => {
    const { result } = renderHook(() => usePipelineSSE("session-1"));
    const src = MockEventSource.registry[0];
    await act(() => {
      src.fire("log", "[Crawler] 완료");
    });
    expect(result.current.logs).toContain("[Crawler] 완료");
  });

  it("T_F5_step_update: step_update event updates steps", async () => {
    const { result } = renderHook(() => usePipelineSSE("session-1"));
    const src = MockEventSource.registry[0];
    await act(() => {
      src.fire("step_update", JSON.stringify({ agent: "Crawler", status: "DONE" }));
    });
    const crawler = result.current.steps.find((s) => s.agent === "Crawler");
    expect(crawler?.status).toBe("DONE");
  });

  it("T_F5_cleanup: sessionId change closes previous EventSource", () => {
    const { rerender } = renderHook(
      ({ sessionId }: { sessionId: string }) => usePipelineSSE(sessionId),
      { initialProps: { sessionId: "old" } }
    );
    const first = MockEventSource.registry[0];
    act(() => {
      rerender({ sessionId: "new" });
    });
    expect(first.closeCalled).toBe(true);
  });
});
