/**
 * FE-1 — computeFileHash 순수 단위 테스트
 * vi.mock 없이 실제 Web Crypto API 사용
 */

import { describe, it, expect } from "vitest";
import { computeFileHash } from "../lib/fileHash";

describe("computeFileHash (Web Crypto SHA256)", () => {
  it("동일 파일 내용은 동일 hash를 반환한다", async () => {
    const content = new Uint8Array([1, 2, 3, 4, 5]);
    const file1 = new File([content], "a.pdf", { type: "application/pdf" });
    const file2 = new File([content], "b.pdf", { type: "application/pdf" });

    const hash1 = await computeFileHash(file1);
    const hash2 = await computeFileHash(file2);

    expect(hash1).toBe(hash2);
    expect(hash1).toHaveLength(64);
  });

  it("다른 내용이면 다른 hash를 반환한다", async () => {
    const file1 = new File([new Uint8Array([1, 2, 3])], "a.pdf");
    const file2 = new File([new Uint8Array([4, 5, 6])], "b.pdf");

    const hash1 = await computeFileHash(file1);
    const hash2 = await computeFileHash(file2);

    expect(hash1).not.toBe(hash2);
  });

  it("hash는 소문자 16진수 64자 문자열이다", async () => {
    const file = new File(["hello world"], "test.txt");
    const hash = await computeFileHash(file);

    expect(/^[0-9a-f]{64}$/.test(hash)).toBe(true);
  });

  it("'hello world'는 known SHA256 값과 일치한다", async () => {
    const file = new File(["hello world"], "test.txt");
    const hash = await computeFileHash(file);
    // SHA256("hello world") = b94d27b9934d3e08a52e52d7da7dabfac484efe04294e576
    expect(hash).toBe("b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9");
  });
});
