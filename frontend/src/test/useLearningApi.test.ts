/**
 * TDD: useLearningApi 훅 — 학습 시작 후 GET /api/pr/{scan_id} 폴링 (T9 Slice 2, FRONTEND_SPEC Section 3).
 */

import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useLearningApi } from "../pages/learning/hooks/useLearningApi";
import { m4Api } from "../pages/learning/lib/m4Api";

vi.mock("../pages/learning/lib/m4Api", () => ({
  m4Api: { post: vi.fn(), get: vi.fn() },
}));

function makeIssue(id: string, status: "pending" | "running" | "completed" | "failed") {
  return {
    id,
    keyword: "sql-injection",
    severity: "high",
    plan: {
      id,
      status,
      llm_fallback: false,
      error_message: null,
      card_content: null,
      ragas_reason: null,
      attempt_count: 0,
    },
  };
}

describe("useLearningApi — 진행 상태 폴링 (T9 Slice 2)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.mocked(m4Api.post).mockReset();
    vi.mocked(m4Api.get).mockReset();
  });

  it("start() 호출 시 scan_id를 받아 GET /api/pr/{scan_id}를 2초 간격으로 폴링한다", async () => {
    vi.mocked(m4Api.post).mockResolvedValue({
      data: { scan_id: "scan-1", plan_ids: ["p1", "p2", "p3"] },
      status: 202,
    });
    vi.mocked(m4Api.get).mockResolvedValue({
      data: { issues: [makeIssue("p1", "pending"), makeIssue("p2", "pending"), makeIssue("p3", "pending")] },
      status: 200,
    });

    const { result } = renderHook(() => useLearningApi());

    await act(async () => {
      await result.current.start();
    });

    expect(m4Api.get).toHaveBeenCalledWith("/api/pr/scan-1");
    const callsAfterFirstFetch = vi.mocked(m4Api.get).mock.calls.length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    expect(vi.mocked(m4Api.get).mock.calls.length).toBeGreaterThan(callsAfterFirstFetch);
  });

  it("3개 이슈의 plan.status가 모두 종료 상태(completed/failed)가 되면 폴링을 멈춘다", async () => {
    vi.mocked(m4Api.post).mockResolvedValue({
      data: { scan_id: "scan-1", plan_ids: ["p1", "p2", "p3"] },
      status: 202,
    });
    vi.mocked(m4Api.get)
      .mockResolvedValueOnce({
        data: { issues: [makeIssue("p1", "pending"), makeIssue("p2", "running"), makeIssue("p3", "pending")] },
        status: 200,
      })
      .mockResolvedValue({
        data: { issues: [makeIssue("p1", "completed"), makeIssue("p2", "completed"), makeIssue("p3", "failed")] },
        status: 200,
      });

    const { result } = renderHook(() => useLearningApi());

    await act(async () => {
      await result.current.start();
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000);
    });

    const callsWhenAllTerminal = vi.mocked(m4Api.get).mock.calls.length;

    await act(async () => {
      await vi.advanceTimersByTimeAsync(6000);
    });

    expect(vi.mocked(m4Api.get).mock.calls.length).toBe(callsWhenAllTerminal);
    expect(result.current.issues?.every((issue) => issue.plan.status === "completed" || issue.plan.status === "failed")).toBe(true);
  });
});
