/**
 * useUploadStatus 단위 테스트
 *
 * 핵심 검증:
 *   TERMINAL_STATUSES 에 속하는 상태가 오면 폴링이 중단되어야 한다.
 *   버그(세션 29): "rejected", "reprocess_failed" 가 누락 → 폴링 무한 지속.
 */
import { renderHook, act } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import * as kmsApi from "../api/kmsApi";
import { useUploadStatus } from "./useUploadStatus";

function makeStatus(status: string) {
  return {
    doc_id: "test-doc",
    status,
    current_stage: null,
    error: null,
    agent_traces: [],
  };
}

describe("useUploadStatus — 폴링 중단 조건", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.useRealTimers();
  });

  // ── 기존 동작 회귀 테스트 ──────────────────────────────────────────────────

  it("stored 상태 수신 시 폴링을 중단한다", async () => {
    const spy = vi
      .spyOn(kmsApi, "getDocumentStatus")
      .mockResolvedValue(makeStatus("stored") as any);

    renderHook(() => useUploadStatus("doc-1", 0));
    await act(async () => { await Promise.resolve(); });

    expect(spy).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(3000);
    await act(async () => { await Promise.resolve(); });

    expect(spy).toHaveBeenCalledTimes(1); // 추가 호출 없음
  });

  it("stored_partial 상태 수신 시 폴링을 중단한다", async () => {
    const spy = vi
      .spyOn(kmsApi, "getDocumentStatus")
      .mockResolvedValue(makeStatus("stored_partial") as any);

    renderHook(() => useUploadStatus("doc-2", 0));
    await act(async () => { await Promise.resolve(); });

    vi.advanceTimersByTime(3000);
    await act(async () => { await Promise.resolve(); });

    expect(spy).toHaveBeenCalledTimes(1);
  });

  it("failed 상태 수신 시 폴링을 중단한다", async () => {
    const spy = vi
      .spyOn(kmsApi, "getDocumentStatus")
      .mockResolvedValue(makeStatus("failed") as any);

    renderHook(() => useUploadStatus("doc-3", 0));
    await act(async () => { await Promise.resolve(); });

    vi.advanceTimersByTime(3000);
    await act(async () => { await Promise.resolve(); });

    expect(spy).toHaveBeenCalledTimes(1);
  });

  // ── 비종료 상태 → 폴링 지속 (기대 동작) ──────────────────────────────────

  it("hitl_pending 상태에서는 폴링이 계속된다", async () => {
    const spy = vi
      .spyOn(kmsApi, "getDocumentStatus")
      .mockResolvedValue(makeStatus("hitl_pending") as any);

    renderHook(() => useUploadStatus("doc-4", 0));
    await act(async () => { await Promise.resolve(); });

    expect(spy).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(1100);
    await act(async () => { await Promise.resolve(); });

    expect(spy).toHaveBeenCalledTimes(2); // 폴링 계속
  });

  it("processing 상태에서는 폴링이 계속된다", async () => {
    const spy = vi
      .spyOn(kmsApi, "getDocumentStatus")
      .mockResolvedValue(makeStatus("processing") as any);

    renderHook(() => useUploadStatus("doc-5", 0));
    await act(async () => { await Promise.resolve(); });

    vi.advanceTimersByTime(1100);
    await act(async () => { await Promise.resolve(); });

    expect(spy).toHaveBeenCalledTimes(2);
  });

  // ── 버그 재현 (REGRESSION): rejected / reprocess_failed ───────────────────

  it("[BUG] rejected 상태 수신 시 폴링을 중단해야 한다 (현재 계속됨)", async () => {
    const spy = vi
      .spyOn(kmsApi, "getDocumentStatus")
      .mockResolvedValue(makeStatus("rejected") as any);

    renderHook(() => useUploadStatus("doc-6", 0));
    await act(async () => { await Promise.resolve(); });

    expect(spy).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(3000); // 3초 경과 — 현재 코드는 3번 더 호출함
    await act(async () => { await Promise.resolve(); });

    expect(spy).toHaveBeenCalledTimes(1); // 고쳐야 통과
  });

  it("[BUG] reprocess_failed 상태 수신 시 폴링을 중단해야 한다 (현재 계속됨)", async () => {
    const spy = vi
      .spyOn(kmsApi, "getDocumentStatus")
      .mockResolvedValue(makeStatus("reprocess_failed") as any);

    renderHook(() => useUploadStatus("doc-7", 0));
    await act(async () => { await Promise.resolve(); });

    expect(spy).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(3000);
    await act(async () => { await Promise.resolve(); });

    expect(spy).toHaveBeenCalledTimes(1); // 고쳐야 통과
  });

  // ── 에러 재시도 동작 ───────────────────────────────────────────────────────

  it("네트워크 오류 2회 연속 시 폴링을 재시도한다 (즉시 에러 전환 X)", async () => {
    const spy = vi
      .spyOn(kmsApi, "getDocumentStatus")
      .mockRejectedValue(new Error("ECONNREFUSED"));

    renderHook(() => useUploadStatus("doc-8", 0));
    await act(async () => { await Promise.resolve(); });

    // 1회 실패 → error 미설정
    expect(spy).toHaveBeenCalledTimes(1);

    vi.advanceTimersByTime(2100); // 2초 후 재시도
    await act(async () => { await Promise.resolve(); });

    expect(spy).toHaveBeenCalledTimes(2); // 2번째 시도
  });

  // ── docId null 시 폴링 시작 안 함 ────────────────────────────────────────

  it("docId가 null이면 API를 호출하지 않는다", async () => {
    const spy = vi
      .spyOn(kmsApi, "getDocumentStatus")
      .mockResolvedValue(makeStatus("stored") as any);

    renderHook(() => useUploadStatus(null, 0));
    await act(async () => { await Promise.resolve(); });

    expect(spy).not.toHaveBeenCalled();
  });
});
