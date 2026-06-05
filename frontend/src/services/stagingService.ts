import type { NodeStatus } from "@/types/concept";
import { apiClient } from "./api";

export interface DiffSummary {
  draft: number;
  approved: number;
  committed: number;
}

export interface StagingItem {
  id: string;
  state: NodeStatus;
  [key: string]: unknown;
}

export const stagingService = {
  getDraft: async (sessionId: string): Promise<StagingItem[]> => {
    const { data } = await apiClient.get(`/staging/${sessionId}`);
    return data.items ?? data;
  },
  getDiff: async (sessionId: string): Promise<DiffSummary> => {
    const { data } = await apiClient.get(`/staging/${sessionId}/diff`);
    return data;
  },
  approveAll: async (sessionId: string): Promise<{ approved: number }> => {
    const { data } = await apiClient.post(`/staging/${sessionId}/approve`);
    return data;
  },
  rejectAll: async (sessionId: string): Promise<{ rejected: number }> => {
    const { data } = await apiClient.post(`/staging/${sessionId}/reject`);
    return data;
  },
  patchNode: async (sessionId: string, nodeId: string, state: "APPROVED" | "REJECTED"): Promise<void> => {
    await apiClient.patch(`/staging/${sessionId}/nodes/${nodeId}`, { state });
  },
};
