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
        const isApproved = item.state === "APPROVED";

        switch (item.infer_action) {
          case "MERGE": {
            // 승인 전: 대상 노드를 MERGE_PENDING 링 + 병합 후보를 DRAFT 점선으로 표시, 승인 후: 정상 상태로 복귀(노드 추가 없음)
            if (isApproved) break;
            const target = baseNodes.find(
              (n) => n.name === item.target_concept_name
            );
            if (target) {
              newNodes.push({ ...target, status: "MERGE_PENDING" });
              newEdges.push({ source: item.id, target: target.id, type: "RELATED_TO" });
            }
            newNodes.push({ ...item, status: "DRAFT", is_staging: true, is_new: true });
            break;
          }
          case "RELATED_TO": {
            // 승인 전: DRAFT 점선 + 주황 NEW 링, 승인 후: 실선 COMMITTED로 실시간 전환
            const draftNode: GraphNode = isApproved
              ? { ...item, status: "COMMITTED", is_staging: false, is_new: false }
              : { ...item, status: "DRAFT", is_staging: true, is_new: true };
            newNodes.push(draftNode);
            if (item.target_concept_name) {
              const targetNode = baseNodes.find(
                (n) => n.name === item.target_concept_name
              );
              if (targetNode) {
                newEdges.push({
                  source: item.id,
                  target: targetNode.id,
                  type: "RELATED_TO",
                });
              }
            }
            break;
          }
          case "NEW":
          default:
            if (!existingIds.has(item.id)) {
              newNodes.push(
                isApproved
                  ? { ...item, status: "COMMITTED", is_staging: false, is_new: false }
                  : { ...item, status: "DRAFT", is_staging: true, is_new: true }
              );
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
