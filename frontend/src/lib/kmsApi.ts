import axios, { type InternalAxiosRequestConfig } from "axios";
import type { DocDetailsResponse, DocListResponse, DocStats, RelatedDoc, SearchResponse, StatusResponse, UploadResponse } from "../types/kms";
import type { PageImage } from "./hitlApi";

// m0 전용 클라이언트 — baseURL 없음, /kms/* 요청이 vite proxy → m0:8002로 라우팅됨
const m0Client = axios.create({ baseURL: "" });
m0Client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const token = localStorage.getItem("access_token");
  if (token) config.headers.Authorization = `Bearer ${token}`;
  return config;
});

function extractDetail(error: unknown, fallback: string): Error {
  const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  return new Error(typeof detail === "string" ? detail : fallback);
}

export async function uploadDocument(file: File, source = "upload", fileHash?: string): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("source", source);
  if (fileHash) form.append("file_hash", fileHash);
  try {
    const { data } = await m0Client.post<UploadResponse>("/kms/upload", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  } catch (e) {
    throw extractDetail(e, "업로드 실패");
  }
}

export async function getDocumentStatus(docId: string): Promise<StatusResponse> {
  try {
    const { data } = await m0Client.get<StatusResponse>(`/kms/status/${docId}`);
    return data;
  } catch (e) {
    throw extractDetail(e, `상태 조회 실패`);
  }
}

export async function getDocDetails(docId: string): Promise<DocDetailsResponse> {
  try {
    const { data } = await m0Client.get<DocDetailsResponse>(`/kms/docs/${docId}/details`);
    return data;
  } catch (e) {
    throw extractDetail(e, "상세 조회 실패");
  }
}

export async function listDocuments(
  status?: string,
  limit = 20,
  offset = 0,
): Promise<DocListResponse> {
  try {
    const { data } = await m0Client.get<DocListResponse>("/kms/docs", {
      params: { ...(status ? { status } : {}), limit, offset },
    });
    return data;
  } catch (e) {
    throw extractDetail(e, "문서 목록 조회 실패");
  }
}

export async function searchKms(query: string, limit = 5, category?: string): Promise<SearchResponse> {
  try {
    const { data } = await m0Client.get<SearchResponse>("/kms/search", {
      params: { q: query, limit, ...(category ? { category } : {}) },
    });
    return data;
  } catch (e) {
    throw extractDetail(e, "검색 실패");
  }
}

export async function getDocPageImages(docId: string): Promise<PageImage[]> {
  try {
    const { data } = await m0Client.get<PageImage[]>(`/kms/docs/${docId}/page-images`);
    return data;
  } catch (e) {
    throw extractDetail(e, "페이지 이미지 조회 실패");
  }
}

export type { PageImage };

// ── 중복 감지 ─────────────────────────────────────────────────────────────────

export interface ExistingDocInfo {
  doc_id: string;
  original_filename: string | null;
  upload_status: string | null;
  created_at: string | null;
}

export interface CheckDuplicateResult {
  status: "identical" | "modified" | "new";
  existing_doc: ExistingDocInfo | null;
}

export async function checkDuplicate(
  fileHash: string,
  originalFilename: string,
): Promise<CheckDuplicateResult> {
  const form = new FormData();
  form.append("file_hash", fileHash);
  form.append("original_filename", originalFilename);
  try {
    const { data } = await m0Client.post<CheckDuplicateResult>("/kms/check-duplicate", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  } catch (e) {
    throw extractDetail(e, "중복 확인 실패");
  }
}

export interface ReplaceDocumentResult {
  new_doc_id: string;
  old_doc_id: string;
  status: string;
  message: string;
}

export async function getDocStats(docId: string): Promise<DocStats> {
  try {
    const { data } = await m0Client.get<DocStats>(`/kms/docs/${docId}/stats`);
    return data;
  } catch (e) {
    throw extractDetail(e, "활용 통계 조회 실패");
  }
}

export async function getDocRelated(docId: string): Promise<RelatedDoc[]> {
  try {
    const { data } = await m0Client.get<{ doc_id: string; related: RelatedDoc[]; total: number }>(`/kms/docs/${docId}/related`);
    return data.related;
  } catch (e) {
    throw extractDetail(e, "연관 문서 조회 실패");
  }
}

export async function deleteDocument(docId: string): Promise<void> {
  try {
    await m0Client.delete(`/kms/docs/${docId}`);
  } catch (e) {
    throw extractDetail(e, "문서 삭제 실패");
  }
}

export async function replaceDocument(
  oldDocId: string,
  file: File,
  fileHash?: string | null,
  source = "upload",
): Promise<ReplaceDocumentResult> {
  const form = new FormData();
  form.append("old_doc_id", oldDocId);
  form.append("file", file);
  form.append("source", source);
  if (fileHash) form.append("file_hash", fileHash);
  try {
    const { data } = await m0Client.post<ReplaceDocumentResult>("/kms/replace-document", form, {
      headers: { "Content-Type": "multipart/form-data" },
    });
    return data;
  } catch (e) {
    throw extractDetail(e, "문서 교체 실패");
  }
}
