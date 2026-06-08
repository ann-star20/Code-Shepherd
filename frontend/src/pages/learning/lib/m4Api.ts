/**
 * m4 서비스(포트 8005) 전용 API 클라이언트 — apiClient(api-core 전용, 사용 금지)와 분리됨 (FRONTEND_SPEC Section 0).
 */

import axios from "axios";

const M4_BASE = import.meta.env.VITE_M4_URL ?? "http://localhost:8005";

export const m4Api = axios.create({
  baseURL: M4_BASE,
  headers: { "Content-Type": "application/json" },
});

m4Api.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});
