import axios from "axios";
import type {
  DiffSummary,
  MetadataLearnPayload,
  StagingConcept,
} from "@/types/graphPipeline";

const M6_BASE = import.meta.env.VITE_M6_URL ?? "/m6-api";

export const m6Client = axios.create({
  baseURL: M6_BASE,
  headers: { "Content-Type": "application/json" },
  timeout: 15000,
});

m6Client.interceptors.request.use((config) => {
  const token = localStorage.getItem("access_token");
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

export const graphPipelineApi = {
  checkDuplicate: (url: string) =>
    m6Client.post<{ is_duplicate: boolean; doc_id?: string }>(
      "/documents/check-duplicate",
      { url }
    ),

  triggerPipeline: (doc_id: string) =>
    m6Client.post<{ session_id: string; message: string }>(
      "/pipeline/trigger",
      { doc_id }
    ),

  subscribeSSE: (sessionId: string): EventSource =>
    new EventSource(`${M6_BASE}/pipeline/stream/${sessionId}`),

  getStaging: (sessionId: string) =>
    m6Client.get<{ items: StagingConcept[] }>(`/staging/${sessionId}`),

  getDiff: (sessionId: string) =>
    m6Client.get<DiffSummary>(`/staging/${sessionId}/diff`),

  approveAll: (sessionId: string) =>
    m6Client.post(`/staging/${sessionId}/approve`),

  rejectAll: (sessionId: string) =>
    m6Client.post(`/staging/${sessionId}/reject`),

  commit: (sessionId: string) =>
    m6Client.post(`/staging/${sessionId}/commit`),

  approveSingle: (stagingId: number) =>
    m6Client.post(`/staging/${stagingId}/approve`),

  rejectSingle: (stagingId: number) =>
    m6Client.post(`/staging/${stagingId}/reject`),

  getTopology: () =>
    m6Client.get<{ nodes: unknown[]; edges: unknown[] }>("/graph/topology"),

  learnMetadata: (payload: MetadataLearnPayload) =>
    m6Client.post("/documents/metadata/learn", payload),
};
