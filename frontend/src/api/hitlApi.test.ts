/**
 * hitlApi — suggestCategory / applyCategory 엔드포인트 호출 검증
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

// ── fetch mock helpers ──────────────────────────────────────────────────────

function mockFetch(body: unknown, status = 200) {
  return vi.fn(async () =>
    new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

describe("hitlApi — suggestCategory", () => {
  const originalFetch = globalThis.fetch;
  let capturedUrl: string;
  let capturedInit: RequestInit | undefined;

  beforeEach(() => {
    capturedUrl = "";
    capturedInit = undefined;
    globalThis.fetch = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      capturedUrl = String(url);
      capturedInit = init;
      return new Response(
        JSON.stringify({
          suggested: ["NCS교육", "아키텍처"],
          reasoning: "NCS 기반 자료",
          alternatives: ["온보딩"],
        }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }) as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("올바른 URL 호출 — /hitl/queue/{id}/suggest-category", async () => {
    const { suggestCategory } = await import("./hitlApi");
    await suggestCategory("test-queue-id");
    expect(capturedUrl).toContain("/hitl/queue/test-queue-id/suggest-category");
  });

  it("GET 메서드 (body 없음)", async () => {
    const { suggestCategory } = await import("./hitlApi");
    await suggestCategory("test-queue-id");
    expect(capturedInit?.method?.toUpperCase() ?? "GET").toBe("GET");
  });

  it("응답 구조 — suggested / reasoning / alternatives 포함", async () => {
    const { suggestCategory } = await import("./hitlApi");
    const result = await suggestCategory("test-queue-id");
    expect(result).toHaveProperty("suggested");
    expect(result).toHaveProperty("reasoning");
    expect(result).toHaveProperty("alternatives");
    expect(Array.isArray(result.suggested)).toBe(true);
  });

  it("HTTP 오류 시 Error throw", async () => {
    globalThis.fetch = mockFetch({ detail: "Not found" }, 404);
    const { suggestCategory } = await import("./hitlApi");
    await expect(suggestCategory("bad-id")).rejects.toThrow();
  });
});

describe("hitlApi — applyCategory", () => {
  const originalFetch = globalThis.fetch;
  let capturedUrl: string;
  let capturedInit: RequestInit | undefined;

  beforeEach(() => {
    capturedUrl = "";
    capturedInit = undefined;
    globalThis.fetch = vi.fn(async (url: RequestInfo | URL, init?: RequestInit) => {
      capturedUrl = String(url);
      capturedInit = init;
      return new Response(
        JSON.stringify({ status: "ok", message: "카테고리 적용 완료" }),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }) as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("올바른 URL 호출 — /hitl/queue/{id}/apply-category", async () => {
    const { applyCategory } = await import("./hitlApi");
    await applyCategory("test-queue-id", "NCS교육");
    expect(capturedUrl).toContain("/hitl/queue/test-queue-id/apply-category");
  });

  it("POST 메서드 사용", async () => {
    const { applyCategory } = await import("./hitlApi");
    await applyCategory("test-queue-id", "NCS교육");
    expect(capturedInit?.method?.toUpperCase()).toBe("POST");
  });

  it("body에 category 포함", async () => {
    const { applyCategory } = await import("./hitlApi");
    await applyCategory("test-queue-id", "NCS교육", "설명");
    const body = JSON.parse(capturedInit?.body as string);
    expect(body.category).toBe("NCS교육");
  });

  it("HTTP 오류 시 Error throw", async () => {
    globalThis.fetch = mockFetch({ detail: "서버 오류" }, 500);
    const { applyCategory } = await import("./hitlApi");
    await expect(applyCategory("bad-id", "x")).rejects.toThrow();
  });
});
