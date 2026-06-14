import type { GraphEdge, GraphLayer, GraphNode } from "@/types/graphPipeline";

export interface LayoutPosition {
  x: number;
  y: number;
}

const LAYER_ORDER: GraphLayer[] = ["L1", "L2", "L3", "L4"];
const LAYER_HEIGHT = 140;
const ROOT_SPACING = 220;
const CHILD_SPACING = 40;
const STAGGER_OFFSET = 18;
const CLUSTER_THRESHOLD = 10;
const CLUSTER_SIZE = 5;
const CLUSTER_SPACING = 220;

function layerDepth(layer?: GraphLayer): number {
  const index = LAYER_ORDER.indexOf(layer ?? "L2");
  return index < 0 ? 1 : index;
}

/**
 * 자식 노드들을 부모 x 중심으로 깊이/인덱스에 따라 미세하게 엇갈리게(staggered) 배치한다.
 */
function layoutStaggeredChildren(
  parentX: number,
  childY: number,
  children: GraphNode[],
  positions: Map<string, LayoutPosition>
): void {
  const totalWidth = (children.length - 1) * CHILD_SPACING;
  children.forEach((child, idx) => {
    const x = parentX - totalWidth / 2 + idx * CHILD_SPACING;
    const stagger = idx % 2 === 0 ? -STAGGER_OFFSET : STAGGER_OFFSET;
    positions.set(child.id, { x, y: childY + stagger });
  });
}

/**
 * 자식 수가 많을 때, 부모 기준 여러 소그룹(cluster)의 중심점으로 나눠 분산 배치한다.
 */
function layoutClusteredChildren(
  parentX: number,
  childY: number,
  children: GraphNode[],
  positions: Map<string, LayoutPosition>
): void {
  const clusterCount = Math.ceil(children.length / CLUSTER_SIZE);
  const totalClusterWidth = (clusterCount - 1) * CLUSTER_SPACING;

  children.forEach((child, idx) => {
    const clusterIndex = Math.floor(idx / CLUSTER_SIZE);
    const indexInCluster = idx % CLUSTER_SIZE;
    const itemsInThisCluster = Math.min(CLUSTER_SIZE, children.length - clusterIndex * CLUSTER_SIZE);
    const clusterCenterX = parentX - totalClusterWidth / 2 + clusterIndex * CLUSTER_SPACING;
    const offsetX = (indexInCluster - (itemsInThisCluster - 1) / 2) * CHILD_SPACING;
    const stagger = indexInCluster % 2 === 0 ? -STAGGER_OFFSET : STAGGER_OFFSET;
    positions.set(child.id, { x: clusterCenterX + offsetX, y: childY + stagger });
  });
}

/**
 * 노드의 layer(깊이)와 edges로부터 추론한 부모-자식 관계를 바탕으로
 * 계층형(Hierarchical) 좌표를 1회성으로 계산한다.
 *
 * - 같은 부모를 공유하는 자식이 적으면 지그재그(staggered) 배치
 * - 자식이 많으면(CLUSTER_THRESHOLD 초과) 여러 소그룹 중심점(cluster)으로 분산 배치
 * - 부모-자식 관계가 없는 고아 노드는 깊이에 맞춰 그리드로 배치
 */
export function computeHierarchicalLayout(
  nodes: GraphNode[],
  edges: GraphEdge[]
): Map<string, LayoutPosition> {
  const positions = new Map<string, LayoutPosition>();
  if (nodes.length === 0) return positions;

  const nodesById = new Map(nodes.map((n) => [n.id, n]));
  const childrenOf = new Map<string, string[]>();

  for (const e of edges) {
    const a = nodesById.get(e.source);
    const b = nodesById.get(e.target);
    if (!a || !b) continue;

    const depthA = layerDepth(a.layer);
    const depthB = layerDepth(b.layer);
    if (depthB - depthA === 1) {
      const list = childrenOf.get(a.id) ?? [];
      if (!list.includes(b.id)) list.push(b.id);
      childrenOf.set(a.id, list);
    } else if (depthA - depthB === 1) {
      const list = childrenOf.get(b.id) ?? [];
      if (!list.includes(a.id)) list.push(a.id);
      childrenOf.set(b.id, list);
    }
  }

  const depths = nodes.map((n) => layerDepth(n.layer));
  const minDepth = Math.min(...depths);
  const maxDepth = Math.max(...depths);

  const roots = nodes.filter((n) => layerDepth(n.layer) === minDepth);
  roots.forEach((root, i) => {
    positions.set(root.id, { x: (i - (roots.length - 1) / 2) * ROOT_SPACING, y: 0 });
  });

  for (let depth = minDepth; depth < maxDepth; depth++) {
    const parents = nodes.filter((n) => layerDepth(n.layer) === depth && positions.has(n.id));
    for (const parent of parents) {
      const parentPos = positions.get(parent.id);
      if (!parentPos) continue;

      const children = (childrenOf.get(parent.id) ?? [])
        .map((id) => nodesById.get(id))
        .filter((n): n is GraphNode => Boolean(n));
      if (children.length === 0) continue;

      const childY = (depth + 1 - minDepth) * LAYER_HEIGHT;
      if (children.length > CLUSTER_THRESHOLD) {
        layoutClusteredChildren(parentPos.x, childY, children, positions);
      } else {
        layoutStaggeredChildren(parentPos.x, childY, children, positions);
      }
    }
  }

  let orphanIndex = 0;
  for (const n of nodes) {
    if (positions.has(n.id)) continue;
    const y = (layerDepth(n.layer) - minDepth) * LAYER_HEIGHT;
    const stagger = orphanIndex % 2 === 0 ? -STAGGER_OFFSET : STAGGER_OFFSET;
    positions.set(n.id, { x: orphanIndex * CHILD_SPACING, y: y + stagger });
    orphanIndex += 1;
  }

  return positions;
}
