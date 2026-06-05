import type { GraphNode, GraphEdge } from "@/types/graph";
import type { StagingRecord } from "@/services/stagingService";

export function mergeVirtualGraph(
  confirmed: GraphNode[],
  draft: StagingRecord[]
): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const draftNodes: GraphNode[] = draft.map((r) => ({
    id: r.id,
    name: r.concept_json.name,
    domain: r.concept_json.domain,
    status: "DRAFT",
  }));

  const edges: GraphEdge[] = [];

  for (const d of draft) {
    const aliases = d.concept_json.aliases ?? [];
    for (const c of confirmed) {
      if (aliases.includes(c.name)) {
        edges.push({ source: c.id, target: d.id, type: "SAME_AS_CANDIDATE" });
      }
    }
  }

  return { nodes: [...confirmed, ...draftNodes], edges };
}
