import type { ApproveRequest, HitlQueuePageResponse, RejectRequest, ReprocessRequest } from "../types/kms";

const BASE_URL = import.meta.env.VITE_API_URL ?? "";

function reviewerHeaders(role = "senior"): HeadersInit {
  return {
    "Content-Type": "application/json",
    "X-Reviewer-Role": role,
  };
}

export interface CategorySuggestion {
  suggested: string[];
  reasoning: string;
  alternatives: string[];
}

export async function suggestCategory(queueId: string): Promise<CategorySuggestion> {
  const res = await fetch(`${BASE_URL}/hitl/queue/${queueId}/suggest-category`);
  if (!res.ok) throw new Error(`카테고리 제안 조회 실패: ${res.statusText}`);
  return res.json();
}

export async function applyCategory(
  queueId: string,
  category: string,
  description = "",
): Promise<{ status: string; message: string }> {
  const res = await fetch(`${BASE_URL}/hitl/queue/${queueId}/apply-category`, {
    method: "POST",
    headers: reviewerHeaders(),
    body: JSON.stringify({ category, description, reviewer_id: "admin" }),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "카테고리 적용 실패");
  }
  return res.json();
}

export async function listHitlQueue(
  status: "pending" | "approved" | "rejected" | "reprocessing" = "pending",
  limit = 20,
  offset = 0,
): Promise<HitlQueuePageResponse> {
  const params = new URLSearchParams({ status, limit: String(limit), offset: String(offset) });
  const res = await fetch(`${BASE_URL}/hitl/queue?${params}`);
  if (!res.ok) throw new Error(`HITL 큐 조회 실패: ${res.statusText}`);
  return res.json() as Promise<HitlQueuePageResponse>;
}

export async function approveHitl(
  queueId: string,
  body: ApproveRequest,
): Promise<{ status: string; message: string }> {
  const res = await fetch(`${BASE_URL}/hitl/queue/${queueId}/approve`, {
    method: "POST",
    headers: reviewerHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "승인 실패");
  }
  return res.json();
}

export async function rejectHitl(
  queueId: string,
  body: RejectRequest,
): Promise<{ status: string; message: string }> {
  const res = await fetch(`${BASE_URL}/hitl/queue/${queueId}/reject`, {
    method: "POST",
    headers: reviewerHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "거부 실패");
  }
  return res.json();
}

export async function getHitlMarkdown(
  queueId: string,
): Promise<{ markdown: string; path: string }> {
  const res = await fetch(`${BASE_URL}/hitl/queue/${queueId}/markdown`);
  if (!res.ok) throw new Error(`Markdown 조회 실패: ${res.statusText}`);
  return res.json();
}

export async function reprocessHitl(
  queueId: string,
  body: ReprocessRequest,
): Promise<{ status: string; message: string; doc_id: string }> {
  const res = await fetch(`${BASE_URL}/hitl/queue/${queueId}/reprocess`, {
    method: "POST",
    headers: reviewerHeaders(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail ?? "재처리 실패");
  }
  return res.json();
}
