/**
 * API 클라이언트 — JWT 자동 첨부, 401 처리 (로그인 페이지로 리다이렉트).
 */

import axios from "axios";

const BASE_URL = import.meta.env.VITE_API_URL ?? "/api";

export const apiClient = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
});

// 요청 인터셉터 — localStorage에서 access token 첨부
apiClient.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// 응답 인터셉터 — 401 시 토큰 제거 후 로그인 페이지로
apiClient.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      window.location.href = "/login";
    }
    return Promise.reject(error);
  }
);

// ── Auth ──────────────────────────────────────────────────────────────────

export const authApi = {
  getAuthorizeUrl: () => `${BASE_URL}/auth/authorize`,
  exchangeCallback: (code: string) =>
    apiClient.get("/auth/callback", { params: { code } }),
  getMe: () => apiClient.get("/auth/me"),
  logout: () => apiClient.post("/auth/logout"),
  refresh: (refreshToken: string) =>
    apiClient.post("/auth/refresh", { refresh_token: refreshToken }),
};

// ── Users ─────────────────────────────────────────────────────────────────

export const usersApi = {
  search: (query: string) => apiClient.get(`/users?search=${encodeURIComponent(query)}`),
};

// ── Teams ─────────────────────────────────────────────────────────────────

export const teamsApi = {
  list: () => apiClient.get("/teams"),
  create: (name: string, github_repo: string) =>
    apiClient.post("/teams", { name, github_repo }),
  update: (
    id: string,
    data: { name?: string; github_repo?: string }
  ) => apiClient.patch(`/teams/${id}`, data),
  delete: (id: string) => apiClient.delete(`/teams/${id}`),
  getMembers: (id: string) => apiClient.get(`/teams/${id}/members`),
  createInvitation: (
    teamId: string,
    data: { user_id?: string; github_id?: string }
  ) => apiClient.post(`/teams/${teamId}/invitations`, data),
  removeMember: (teamId: string, userId: string) =>
    apiClient.delete(`/teams/${teamId}/members/${userId}`),
  updateMemberRole: (teamId: string, userId: string, role: string) =>
    apiClient.patch(`/teams/${teamId}/members/${userId}`, { role }),
  getPRs: (teamId: string) => apiClient.get(`/teams/${teamId}/prs`),
  approvePR: (prId: string) => apiClient.post(`/prs/${prId}/approve`),
};

export const invitationsApi = {
  listMine: () => apiClient.get("/invitations"),
  accept: (id: string) => apiClient.post(`/invitations/${id}/accept`),
  decline: (id: string) => apiClient.post(`/invitations/${id}/decline`),
};

// ── m2: 정적 분석 · 보안 스캔 ────────────────────────────────────────────────
// 계약: backend/_shared/shared/contracts.py (M2AnalyzeRequest / M2AnalyzeResponse)

export type IssueSeverity = "Critical" | "Major" | "Minor";

export interface IssueItem {
  severity: IssueSeverity;
  line: number | null;
  file: string | null;
  message: string;
  rule_id: string | null;
  suggestion: string | null;
}

export interface IssueSummary {
  critical: number;
  major: number;
  minor: number;
}

export interface M2AnalyzeResponse {
  task_id: string;
  agent: "static_analysis" | "security_scan";
  issues: IssueItem[];
  summary: IssueSummary;
  execution_ms: number;
}

export interface M2AnalyzeRequest {
  task_id: string;
  pr_id: string;
  pr_diff: string;
}

export const analyzeApi = {
  static: (payload: M2AnalyzeRequest) =>
    apiClient.post<M2AnalyzeResponse>("/analyze/static", payload),
  security: (payload: M2AnalyzeRequest) =>
    apiClient.post<M2AnalyzeResponse>("/analyze/security", payload),
};
