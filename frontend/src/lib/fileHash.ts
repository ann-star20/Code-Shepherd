/**
 * 브라우저 Web Crypto API를 사용해 File의 SHA256 hex digest를 계산한다.
 * 업로드 전 /kms/check-duplicate 호출에 사용.
 */
export async function computeFileHash(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map((b) => b.toString(16).padStart(2, "0")).join("");
}
