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

// m3 리뷰 결과 조회용 클라이언트 — m3는 별도 포트(8004). 로컬은 vite proxy '/m3-api'로 접근.
// (api-core(/api)와 분리. m3 /review 는 인증 불필요하지만 토큰이 있으면 첨부.)
const M3_BASE_URL = import.meta.env.VITE_M3_API_URL ?? "/m3-api";

export const m3Client = axios.create({
  baseURL: M3_BASE_URL,
  headers: { "Content-Type": "application/json" },
});

m3Client.interceptors.request.use((config) => {
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

// ── PR 리뷰 (SESSION 5) ──────────────────────────────────────────────────────
// PR 목록은 api-core(/api), 리뷰 상세는 m3(/m3-api). 기존 fetch 래퍼 패턴 재사용.

export const reviewApi = {
  // 팀의 PR 목록 — api-core GET /teams/{teamId}/prs → { scope, prs: [...] }
  getTeamPRs: (teamId: string) => apiClient.get(`/teams/${teamId}/prs`),
  // PR 리뷰 결과 — m3 GET /review/{owner}/{repo}/{pr_number}
  //   → { found, verdict, comment, issues: [{severity,file,line,message,rule_id,suggestion}] }
  getReview: (owner: string, repo: string, prNumber: number | string) =>
    m3Client.get(`/review/${owner}/${repo}/${prNumber}`),
};
