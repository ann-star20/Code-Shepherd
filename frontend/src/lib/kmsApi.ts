import { apiClient } from "./api";
import type { DocDetailsResponse, SearchResponse, StatusResponse, UploadResponse } from "../types/kms";

function extractDetail(error: unknown, fallback: string): Error {
  const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  return new Error(typeof detail === "string" ? detail : fallback);
}

export async function uploadDocument(file: File, source = "upload"): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("source", source);
  try {
    const { data } = await apiClient.post<UploadResponse>("/kms/upload", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  } catch (e) {
    throw extractDetail(e, "업로드 실패");
  }
}

export async function getDocumentStatus(docId: string): Promise<StatusResponse> {
  try {
    const { data } = await apiClient.get<StatusResponse>(`/kms/status/${docId}`);
    return data;
  } catch (e) {
    throw extractDetail(e, `상태 조회 실패`);
  }
}

export async function getDocDetails(docId: string): Promise<DocDetailsResponse> {
  try {
    const { data } = await apiClient.get<DocDetailsResponse>(`/kms/docs/${docId}/details`);
    return data;
  } catch (e) {
    throw extractDetail(e, "상세 조회 실패");
  }
}

export async function searchKms(query: string, limit = 5, category?: string): Promise<SearchResponse> {
  try {
    const { data } = await apiClient.get<SearchResponse>("/kms/search", {
      params: { q: query, limit, ...(category ? { category } : {}) },
    });
    return data;
  } catch (e) {
    throw extractDetail(e, "검색 실패");
  }
}
