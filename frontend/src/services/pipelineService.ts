import { apiClient } from "./api";

export interface PreScanResult {
  framework?: string;
  version?: string;
  lang?: string;
  confidence: number;
}

export interface TriggerPipelineRequest {
  urls: string[];
  metadata: { framework?: string; version?: string; lang?: string };
}

export const pipelineService = {
  trigger: async (req: TriggerPipelineRequest): Promise<{ session_id: string }> => {
    const { data } = await apiClient.post("/pipeline/trigger", req);
    return data;
  },
  prescan: async (url: string): Promise<PreScanResult> => {
    const { data } = await apiClient.get("/pipeline/prescan", { params: { url } });
    return data;
  },
  getHealth: async (): Promise<{ status: string; mode: string }> => {
    const { data } = await apiClient.get("/health");
    return data;
  },
};
