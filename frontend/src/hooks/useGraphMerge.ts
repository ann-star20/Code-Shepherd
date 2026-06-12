import { useState, useCallback } from "react";
import type { GraphNode, GraphEdge, StagingConcept } from "@/types/graphPipeline";

interface UseGraphMergeResult {
  draftNodes: GraphNode[];
  draftEdges: GraphEdge[];
  applyDraftNodes: (items: StagingConcept[], baseNodes: GraphNode[]) => void;
  clearDraft: () => void;
}

export function useGraphMerge(): UseGraphMergeResult {
  const [draftNodes, setDraftNodes] = useState<GraphNode[]>([]);
  const [draftEdges, setDraftEdges] = useState<GraphEdge[]>([]);

  const applyDraftNodes = useCallback(
    (items: StagingConcept[], baseNodes: GraphNode[]) => {
      const existingIds = new Set(baseNodes.map((n) => n.id));
      const newNodes: GraphNode[] = [];
      const newEdges: GraphEdge[] = [];

      for (const item of items) {
        if (item.state === "REJECTED") continue;

        switch (item.infer_action) {
          case "MERGE": {
            // Mark existing node as MERGE_PENDING, no new node
            const target = baseNodes.find(
              (n) => n.name === item.target_concept_name
            );
            if (target) {
              newNodes.push({ ...target, status: "MERGE_PENDING" });
            }
            break;
          }
          case "RELATED_TO": {
            // New DRAFT node + RELATED_TO_CANDIDATE edge
            const draftNode: GraphNode = { ...item, status: "DRAFT" };
            newNodes.push(draftNode);
            if (item.target_concept_name) {
              const targetNode = baseNodes.find(
                (n) => n.name === item.target_concept_name
              );
              if (targetNode) {
                newEdges.push({
                  source: item.id,
                  target: targetNode.id,
                  type: "RELATED_TO_CANDIDATE",
                });
              }
            }
            break;
          }
          case "NEW":
          default:
            if (!existingIds.has(item.id)) {
              newNodes.push({ ...item, status: "DRAFT" });
            }
            break;
        }
      }

      setDraftNodes(newNodes);
      setDraftEdges(newEdges);
    },
    []
  );

  const clearDraft = useCallback(() => {
    setDraftNodes([]);
    setDraftEdges([]);
  }, []);

  return { draftNodes, draftEdges, applyDraftNodes, clearDraft };
}
