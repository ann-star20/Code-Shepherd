import { apiClient } from "./api";
import type { ApproveRequest, HitlQueuePageResponse, RejectRequest, ReprocessRequest } from "../types/kms";

export interface CategorySuggestion {
  suggested: string[];
  reasoning: string;
  alternatives: string[];
}

function extractDetail(error: unknown, fallback: string): Error {
  const detail = (error as { response?: { data?: { detail?: string } } }).response?.data?.detail;
  return new Error(typeof detail === "string" ? detail : fallback);
}

const reviewerConfig = (role = "senior") => ({
  headers: { "X-Reviewer-Role": role },
});

export async function suggestCategory(queueId: string): Promise<CategorySuggestion> {
  try {
    const { data } = await apiClient.get<CategorySuggestion>(`/hitl/queue/${queueId}/suggest-category`);
    return data;
  } catch (e) {
    throw extractDetail(e, "카테고리 제안 조회 실패");
  }
}

export async function applyCategory(
  queueId: string,
  category: string,
  description = "",
): Promise<{ status: string; message: string }> {
  try {
    const { data } = await apiClient.post<{ status: string; message: string }>(
      `/hitl/queue/${queueId}/apply-category`,
      { category, description, reviewer_id: "admin" },
      reviewerConfig(),
    );
    return data;
  } catch (e) {
    throw extractDetail(e, "카테고리 적용 실패");
  }
}

export async function listHitlQueue(
  status: "pending" | "approved" | "rejected" | "reprocessing" = "pending",
  limit = 20,
  offset = 0,
): Promise<HitlQueuePageResponse> {
  try {
    const { data } = await apiClient.get<HitlQueuePageResponse>("/hitl/queue", {
      params: { status, limit, offset },
    });
    return data;
  } catch (e) {
    throw extractDetail(e, "HITL 큐 조회 실패");
  }
}

export async function approveHitl(
  queueId: string,
  body: ApproveRequest,
): Promise<{ status: string; message: string }> {
  try {
    const { data } = await apiClient.post<{ status: string; message: string }>(
      `/hitl/queue/${queueId}/approve`,
      body,
      reviewerConfig(),
    );
    return data;
  } catch (e) {
    throw extractDetail(e, "승인 실패");
  }
}

export async function rejectHitl(
  queueId: string,
  body: RejectRequest,
): Promise<{ status: string; message: string }> {
  try {
    const { data } = await apiClient.post<{ status: string; message: string }>(
      `/hitl/queue/${queueId}/reject`,
      body,
      reviewerConfig(),
    );
    return data;
  } catch (e) {
    throw extractDetail(e, "거부 실패");
  }
}

export async function getHitlMarkdown(queueId: string): Promise<{ markdown: string; path: string }> {
  try {
    const { data } = await apiClient.get<{ markdown: string; path: string }>(
      `/hitl/queue/${queueId}/markdown`,
    );
    return data;
  } catch (e) {
    throw extractDetail(e, "Markdown 조회 실패");
  }
}

export async function reprocessHitl(
  queueId: string,
  body: ReprocessRequest,
): Promise<{ status: string; message: string; doc_id: string }> {
  try {
    const { data } = await apiClient.post<{ status: string; message: string; doc_id: string }>(
      `/hitl/queue/${queueId}/reprocess`,
      body,
      reviewerConfig(),
    );
    return data;
  } catch (e) {
    throw extractDetail(e, "재처리 실패");
  }
}
