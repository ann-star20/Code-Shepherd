import { useCallback, useEffect, useState } from "react";
import type { GraphNode, GraphEdge } from "@/types/graph";
import type { StagingRecord } from "@/services/stagingService";
import { graphService } from "@/services/graphService";
import { stagingService } from "@/services/stagingService";
import { mergeVirtualGraph } from "@/utils/mergeVirtualGraph";

interface GraphMergeState {
  nodes: GraphNode[];
  edges: GraphEdge[];
  isLoading: boolean;
  refresh: () => void;
}

export function useGraphMerge(sessionId: string | null): GraphMergeState {
  const [nodes, setNodes] = useState<GraphNode[]>([]);
  const [edges, setEdges] = useState<GraphEdge[]>([]);
  const [isLoading, setIsLoading] = useState(true);

  const load = useCallback(async () => {
    setIsLoading(true);
    try {
      const { nodes: confirmed, edges: confirmedEdges } = await graphService.getTopology();
      const draft: StagingRecord[] = sessionId
        ? await stagingService.getDraft(sessionId)
        : [];
      const merged = mergeVirtualGraph(confirmed, draft);
      setNodes(merged.nodes);
      setEdges([...confirmedEdges, ...merged.edges]);
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  useEffect(() => { void load(); }, [load]);

  return { nodes, edges, isLoading, refresh: load };
}
