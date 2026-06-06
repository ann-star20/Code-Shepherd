import axios, { type InternalAxiosRequestConfig } from "axios";
import type { DocDetailsResponse, DocListResponse, SearchResponse, StatusResponse, UploadResponse } from "../types/kms";
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

export async function uploadDocument(file: File, source = "upload"): Promise<UploadResponse> {
  const form = new FormData();
  form.append("file", file);
  form.append("source", source);
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
