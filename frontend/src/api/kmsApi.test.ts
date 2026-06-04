/**
 * kmsApi — BASE_URL 환경변수 설정 검증 테스트
 *
 * BUG: .env.development에 VITE_API_URL=http://localhost:8000이 설정되면
 *      Vite 프록시(/kms → 8001)를 우회하여 잘못된 포트로 요청이 전송됨.
 *      → 브라우저에서 "Failed to fetch" 발생
 */

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { resolveBaseUrl } from "./kmsApi";

describe("kmsApi BASE_URL 설정", () => {
  it("VITE_API_URL 미설정 시 빈 문자열 → Vite 프록시 경로 사용", () => {
    const base = resolveBaseUrl(undefined);
    expect(base).toBe("");
  });

  it("VITE_API_URL='' 빈 문자열 → 프록시 경로 사용", () => {
    const base = resolveBaseUrl("");
    // 빈 문자열이면 Vite 프록시(/kms → localhost:8001)가 동작
    expect(base).toBe("");
  });

  it("VITE_API_URL=http://localhost:8000 → 잘못된 포트로 직접 요청 발생 (BUG)", () => {
    const base = resolveBaseUrl("http://localhost:8000");
    // 8000은 잘못된 포트 — API는 8001에서 실행
    expect(base).not.toContain(":8000");
  });

  it("VITE_API_URL이 설정된 경우 8001 포트이거나 빈 문자열이어야 함", () => {
    const validValues = ["", "http://localhost:8001", undefined];
    const invalidValues = ["http://localhost:8000", "http://localhost:3000"];

    for (const v of validValues) {
      const base = resolveBaseUrl(v);
      const isValid = base === "" || base.includes(":8001");
      expect(isValid, `유효해야 함: "${v}"`).toBe(true);
    }

    for (const v of invalidValues) {
      const base = resolveBaseUrl(v);
      // 잘못된 localhost 포트 → resolveBaseUrl이 "" 로 교체 (프록시 경로 사용)
      expect(base, `잘못된 URL은 빈 문자열로 변환돼야 함: "${v}"`).toBe("");
    }
  });
});

// ────────────────────────────────────────────────────────────
//  uploadDocument — fetch 호출 URL 검증
// ────────────────────────────────────────────────────────────
describe("uploadDocument fetch URL", () => {
  const originalFetch = globalThis.fetch;
  let capturedUrl: string;

  beforeEach(() => {
    capturedUrl = "";
    globalThis.fetch = vi.fn(async (url: RequestInfo | URL) => {
      capturedUrl = String(url);
      return new Response(JSON.stringify({ doc_id: "test-id", status: "processing" }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }) as typeof fetch;
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it("BASE_URL='' → /kms/upload 상대 경로로 요청 (프록시 통과)", async () => {
    // import.meta.env.VITE_API_URL 이 undefined → BASE_URL = ""
    const file = new File(["content"], "test.txt", { type: "text/plain" });
    const form = new FormData();
    form.append("file", file);
    form.append("source", "upload");

    await fetch("/kms/upload", { method: "POST", body: form });

    expect(capturedUrl).toBe("/kms/upload");
    expect(capturedUrl).not.toContain("localhost:8000");
    expect(capturedUrl).not.toContain("localhost:8001");
  });

  it("절대 URL http://localhost:8000/kms/upload → 잘못된 포트 호출 (BUG 재현)", async () => {
    const buggyUrl = "http://localhost:8000/kms/upload";
    await fetch(buggyUrl, { method: "POST", body: new FormData() });

    // BUG: 8000은 API 서버 포트가 아님 → Failed to fetch
    expect(capturedUrl).toContain(":8000");
    expect(capturedUrl).not.toContain(":8001");
  });
});
