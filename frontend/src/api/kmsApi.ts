import type { DocDetailsResponse, SearchResponse, StatusResponse, UploadResponse } from "../types/kms";

// 잘못된 포트(8000, 3000 등)가 설정되면 Vite 프록시를 우회해 "Failed to fetch"가 발생한다.
// localhost URL 중 8001이 아닌 포트는 빈 문자열(프록시 경로)로 대체한다.
export function resolveBaseUrl(envValue: string | undefined): string {
  if (!envValue) return "";
  if (/https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?/.test(envValue) && !envValue.includes(":8001")) {
    return "";
  }
  return envValue;
}

const BASE_URL = resolveBaseUrl(import.meta.env.VITE_API_URL);

export async function uploadDocument(
  file: File,
  source = "upload"
): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("source", source);

  const res = await fetch(`${BASE_URL}/kms/upload`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const detail = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(detail.detail ?? "업로드 실패");
  }

  return res.json() as Promise<UploadResponse>;
}

export async function getDocumentStatus(docId: string): Promise<StatusResponse> {
  const res = await fetch(`${BASE_URL}/kms/status/${docId}`);

  if (!res.ok) {
    throw new Error(`상태 조회 실패: ${res.statusText}`);
  }

  return res.json() as Promise<StatusResponse>;
}

export async function getDocDetails(docId: string): Promise<DocDetailsResponse> {
  const res = await fetch(`${BASE_URL}/kms/docs/${docId}/details`);
  if (!res.ok) {
    throw new Error(`상세 조회 실패: ${res.statusText}`);
  }
  return res.json() as Promise<DocDetailsResponse>;
}

export async function searchKms(
  query: string,
  limit = 5,
  category?: string
): Promise<SearchResponse> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  if (category) params.set("category", category);

  const res = await fetch(`${BASE_URL}/kms/search?${params}`);

  if (!res.ok) {
    throw new Error(`검색 실패: ${res.statusText}`);
  }

  return res.json() as Promise<SearchResponse>;
}
