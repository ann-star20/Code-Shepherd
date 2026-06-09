/**
 * 가상 그래프 병합 순수 함수 (PRD §2.2).
 *
 * 규칙:
 *   MERGE         → 기존 확정 노드에 status="MERGE_PENDING" 배지 오버레이.
 *                   신규 독립 노드 생성 금지.
 *   RELATED_TO    → 신규 DRAFT 노드 파생 + type="RELATED_TO_CANDIDATE" 가교 엣지.
 *   NEW / 미설정   → 완전 독립 DRAFT 노드, 엣지 없음.
 *
 * 필드명 표준: concept_name, domains: string[] (구형 name/domain 폐기)
 */
import type { GraphNode, GraphEdge } from "@/types/graph";
import type { StagingRecord } from "@/services/stagingService";

export interface MergeResult {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export function mergeVirtualGraph(
  confirmed: GraphNode[],
  draft: StagingRecord[],
): MergeResult {
  const confirmedByName = new Map<string, GraphNode>(
    confirmed.map((n) => [n.name, n]),
  );
  const mergedNodes: GraphNode[] = confirmed.map((n) => ({ ...n }));
  const edges: GraphEdge[] = [];

  for (const record of draft) {
    const cj = record.concept_json;
    const conceptName = cj.concept_name;
    const domains = cj.domains ?? [];
    const domain = (domains[0] ?? "security") as GraphNode["domain"];
    const aliases = cj.aliases ?? [];
    const mergeAction = cj.merge_action;
    const targetConcept = cj.target_concept;

    // ── MERGE: merge_action=MERGE + target_concept 명시 ─────────────────────
    if (mergeAction === "MERGE" && targetConcept) {
      const target = mergedNodes.find((n) => n.name === targetConcept);
      if (target) {
        target.status = "MERGE_PENDING";
        continue;
      }
    }

    // ── MERGE: aliases에 기존 확정 노드명 포함 → 자동 MERGE_PENDING ──────────
    let aliasMatch: GraphNode | undefined;
    for (const alias of aliases) {
      const found = confirmedByName.get(alias);
      if (found) {
        aliasMatch = found;
        break;
      }
    }
    if (aliasMatch) {
      const target = mergedNodes.find((n) => n.name === aliasMatch!.name);
      if (target) target.status = "MERGE_PENDING";
      continue;
    }

    // ── RELATED_TO: 신규 DRAFT 노드 + 가교 엣지 ─────────────────────────────
    if (mergeAction === "RELATED_TO") {
      mergedNodes.push({ id: record.id, name: conceptName, domain, status: "DRAFT" });
      if (targetConcept) {
        const target = confirmedByName.get(targetConcept);
        edges.push({
          source: target?.id ?? targetConcept,
          target: record.id,
          type: "RELATED_TO_CANDIDATE",
        });
      }
      continue;
    }

    // ── NEW / 미설정: 완전 독립 DRAFT 노드 ──────────────────────────────────
    mergedNodes.push({ id: record.id, name: conceptName, domain, status: "DRAFT" });
  }

  return { nodes: mergedNodes, edges };
}
