/**
 * 브라우저 Web Crypto API를 사용해 File의 SHA256 hex digest를 계산한다.
 * 업로드 전 /kms/check-duplicate 호출에 사용.
 */
export async function computeFileHash(file: File): Promise<string> {
  const raw = await file.arrayBuffer();
  // Pass Uint8Array (TypedArray) instead of ArrayBuffer —
  // jsdom 24's SubtleCrypto.digest rejects ArrayBuffer but accepts TypedArray
  const hashBuffer = await crypto.subtle.digest("SHA-256", new Uint8Array(raw));
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}
