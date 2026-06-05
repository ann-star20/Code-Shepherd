import type { GraphNode, GraphEdge } from "@/types/graph";
import { apiClient } from "./api";

export const graphService = {
  getTopology: async (): Promise<{ nodes: GraphNode[]; edges: GraphEdge[] }> => {
    const { data } = await apiClient.get("/graph/topology");
    return data;
  },
};
