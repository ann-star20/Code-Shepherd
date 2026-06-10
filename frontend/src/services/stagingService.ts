import type { NodeStatus } from "@/types/concept";
import { apiClient } from "./api";

export interface DiffSummary {
  draft: number;
  approved: number;
  committed: number;
}

/**
 * 백엔드 ConceptExtractionSchema 필드명을 그대로 반영.
 * concept_name / domains[] 는 구형 name / domain 필드 대신 사용한다.
 */
export interface StagingConceptJson {
  concept_name: string;
  domains: string[];
  concept_type?: string;
  severity?: string;
  description_ko?: string;
  aliases?: string[];
  cwe_id?: string;
  owasp_id?: string;
  root_cause?: string;
  affected_components?: string[];
  mechanism?: string[];
  /** 하이브리드 리졸버 판정 결과 (DEV mock 또는 pre-scoring 시 포함) */
  merge_action?: "MERGE" | "RELATED_TO" | "NEW";
  merge_score?: number;
  target_concept?: string;
}

export interface StagingRecord {
  id: string;
  session_id?: string;
  concept_json: StagingConceptJson;
  state: NodeStatus;
}

export const stagingService = {
  getDraft: async (sessionId: string): Promise<StagingRecord[]> => {
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
