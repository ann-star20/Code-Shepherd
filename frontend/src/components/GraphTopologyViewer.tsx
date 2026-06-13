import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";
import type { GraphEdge, GraphEdgeType, GraphNode } from "@/types/graphPipeline";
import { DOMAIN_COLOR, EDGE_STYLE, LAYER_RADIUS, getNodeStyle } from "@/lib/graphFormatters";

interface GraphTopologyViewerProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick?: (node: GraphNode) => void;
  focusNodeId?: string | null;
}

const DAG_LEVEL_DISTANCE = 160;
const CHARGE_STRENGTH = -180;
const CHARGE_DISTANCE_MAX = 600;
const FORCE_X_STRENGTH = 0.02;
const DIMMED_OPACITY = 0.2;
const HOVER_DIMMED_OPACITY = 0.1;
const LABEL_GAP = 5;

const LINK_DISTANCE: Partial<Record<GraphEdgeType, number>> = {
  BELONGS_TO: 50,
  MITIGATED_BY: 90,
  CAUSED_BY: 90,
  AFFECTS: 90,
  HAS_EXAMPLE: 110,
  RELATED_TO: 70,
};
const DEFAULT_LINK_DISTANCE = 60;

const LEGEND_DOMAINS = [
  { label: "security",     color: DOMAIN_COLOR.security },
  { label: "performance",  color: DOMAIN_COLOR.performance },
  { label: "both",         color: DOMAIN_COLOR.both },
  { label: "draft (점선)", color: DOMAIN_COLOR.default },
];

const LEGEND_EDGES = [
  { label: "BELONGS_TO",   color: EDGE_STYLE.BELONGS_TO.color },
  { label: "MITIGATED_BY", color: EDGE_STYLE.MITIGATED_BY.color },
  { label: "CAUSED_BY",    color: EDGE_STYLE.CAUSED_BY.color },
  { label: "AFFECTS",      color: EDGE_STYLE.AFFECTS.color },
  { label: "RELATED_TO",   color: EDGE_STYLE.RELATED_TO.color },
];

function nodeColor(node: GraphNode): string {
  if (node.node_type === "Domain") {
    return DOMAIN_COLOR[node.name as keyof typeof DOMAIN_COLOR] ?? DOMAIN_COLOR.default;
  }
  if (node.node_type === "Concept") {
    return DOMAIN_COLOR[node.domains?.[0] as keyof typeof DOMAIN_COLOR] ?? DOMAIN_COLOR.default;
  }
  return DOMAIN_COLOR.default;
}

/**
 * focusNodeId에서 BFS로 연결된 노드 id 집합을 구한다.
 * Domain 노드는 도착 시 포함만 하고 더 확장하지 않는다 —
 * 같은 도메인의 무관한 다른 Concept까지 켜지는 것을 방지.
 */
function buildFocusSet(
  focusNodeId: string | null | undefined,
  edges: GraphEdge[],
  nodesById: Map<string, GraphNode>
): Set<string> | null {
  if (!focusNodeId) return null;

  const visited = new Set<string>([focusNodeId]);
  const queue: string[] = [focusNodeId];

  while (queue.length > 0) {
    const current = queue.shift() as string;
    const currentNode = nodesById.get(current);
    if (currentNode?.node_type === "Domain" && current !== focusNodeId) continue;

    for (const e of edges) {
      if (e.source === current && !visited.has(e.target)) {
        visited.add(e.target);
        queue.push(e.target);
      }
      if (e.target === current && !visited.has(e.source)) {
        visited.add(e.source);
        queue.push(e.source);
      }
    }
  }

  return visited;
}

/**
 * charge 힘만으로는 노드가 원형으로 뭉치는 경향이 있어,
 * x=0 방향으로 약하게 끌어당기는 보조 힘을 추가해 가로로 넓게 퍼지도록 한다.
 */
interface SimNode {
  x?: number;
  vx?: number;
  [key: string]: unknown;
}

type XForce = ((alpha: number) => void) & {
  initialize: (nodes: SimNode[], ...args: unknown[]) => void;
};

function createForceX(strength: number): XForce {
  let simNodes: SimNode[] = [];
  const force = ((alpha: number) => {
    for (const n of simNodes) {
      n.vx = (n.vx ?? 0) - (n.x ?? 0) * strength * alpha;
    }
  }) as XForce;
  force.initialize = (nodes) => {
    simNodes = nodes;
  };
  return force;
}

export function GraphTopologyViewer({ nodes, edges, onNodeClick, focusNodeId }: GraphTopologyViewerProps) {
  const fgRef = useRef<ForceGraphMethods>();
  const [hoverNodeId, setHoverNodeId] = useState<string | null>(null);

  const graphData = useMemo(() => {
    const visibleNodes = nodes.filter((n) => n.layer !== "L4");
    const visibleIds = new Set(visibleNodes.map((n) => n.id));
    const visibleEdges = edges.filter(
      (e) => visibleIds.has(e.source) && visibleIds.has(e.target)
    );
    return {
      nodes: visibleNodes.map((n) => ({ ...n })),
      links: visibleEdges.map((e) => ({ source: e.source, target: e.target, type: e.type })),
    };
  }, [nodes, edges]);

  const nodesById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const focusedIds = useMemo(
    () => buildFocusSet(focusNodeId, edges, nodesById),
    [focusNodeId, edges, nodesById]
  );

  const hoverFocusedIds = useMemo(
    () => buildFocusSet(hoverNodeId, edges, nodesById),
    [hoverNodeId, edges, nodesById]
  );

  const activeFocusIds = hoverFocusedIds ?? focusedIds;
  const activeDimOpacity = hoverFocusedIds ? HOVER_DIMMED_OPACITY : DIMMED_OPACITY;

  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;

    const charge = fg.d3Force("charge");
    if (charge) {
      charge.strength(CHARGE_STRENGTH);
      charge.distanceMax(CHARGE_DISTANCE_MAX);
    }

    const link = fg.d3Force("link");
    if (link) {
      link.distance((l: GraphEdge) => LINK_DISTANCE[l.type] ?? DEFAULT_LINK_DISTANCE);
    }

    fg.d3Force("x", createForceX(FORCE_X_STRENGTH));
  }, [graphData]);

  const paintNode = useCallback(
    (node: object, ctx: CanvasRenderingContext2D) => {
      const n = node as GraphNode & { x: number; y: number };
      const style = getNodeStyle(n.status ?? "COMMITTED", nodeColor(n));
      const radius = LAYER_RADIUS[n.layer ?? "L2"];
      const isDimmed = activeFocusIds != null && !activeFocusIds.has(n.id);
      const opacity = isDimmed ? activeDimOpacity : style.opacity;

      ctx.globalAlpha = opacity;

      if (style.dashed) {
        ctx.setLineDash([5, 3]);
        ctx.strokeStyle = nodeColor(n);
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(n.x, n.y, radius, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.fillStyle = nodeColor(n) + "40";
        ctx.fill();
        ctx.setLineDash([]);
      } else {
        ctx.fillStyle = nodeColor(n);
        ctx.beginPath();
        ctx.arc(n.x, n.y, radius, 0, 2 * Math.PI);
        ctx.fill();
      }

      if (style.ring) {
        ctx.strokeStyle = style.ring;
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.arc(n.x, n.y, radius + 3, 0, 2 * Math.PI);
        ctx.stroke();
      }

      if (n.id === focusNodeId) {
        ctx.strokeStyle = "#2563EB";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(n.x, n.y, radius + 4, 0, 2 * Math.PI);
        ctx.stroke();
      }

      ctx.globalAlpha = 1;

      const isHovered = n.id === hoverNodeId;
      const inHoverSubgraph = hoverFocusedIds != null && hoverFocusedIds.has(n.id);
      const showLabel =
        n.layer === "L1" ||
        n.layer === "L2" ||
        isHovered ||
        inHoverSubgraph ||
        (focusedIds != null && focusedIds.has(n.id));

      if (showLabel) {
        ctx.globalAlpha = isDimmed ? activeDimOpacity : 1;
        ctx.fillStyle = "#111827";
        if (isHovered) {
          ctx.font = "bold 7px sans-serif";
        } else if (n.layer === "L1") {
          ctx.font = "bold 5px sans-serif";
        } else {
          ctx.font = "4px sans-serif";
        }
        ctx.textAlign = "center";
        ctx.textBaseline = "bottom";
        ctx.fillText(n.name.slice(0, 16), n.x, n.y - radius - LABEL_GAP);
        ctx.textBaseline = "alphabetic";
        ctx.globalAlpha = 1;
      }
    },
    [focusNodeId, hoverNodeId, hoverFocusedIds, focusedIds, activeFocusIds, activeDimOpacity]
  );

  const paintLink = useCallback(
    (link: object, ctx: CanvasRenderingContext2D) => {
      const l = link as GraphEdge & {
        source: { x: number; y: number; id?: string };
        target: { x: number; y: number; id?: string };
      };
      const style = EDGE_STYLE[l.type] ?? EDGE_STYLE.RELATED_TO;
      const sourceId = l.source.id;
      const targetId = l.target.id;
      const isDimmed =
        activeFocusIds != null &&
        !(sourceId != null && targetId != null && activeFocusIds.has(sourceId) && activeFocusIds.has(targetId));

      ctx.globalAlpha = isDimmed ? activeDimOpacity : 1;
      ctx.strokeStyle = style.color;
      ctx.lineWidth = style.width;
      if (style.dashed) {
        ctx.setLineDash([4, 2]);
      } else {
        ctx.setLineDash([]);
      }
      ctx.beginPath();
      ctx.moveTo(l.source.x, l.source.y);
      ctx.lineTo(l.target.x, l.target.y);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.globalAlpha = 1;
    },
    [activeFocusIds, activeDimOpacity]
  );

  return (
    <div className="relative w-full h-full rounded-lg border bg-gray-50 overflow-hidden">
      <ForceGraph2D
        ref={fgRef}
        graphData={graphData}
        dagMode="td"
        dagLevelDistance={DAG_LEVEL_DISTANCE}
        nodeCanvasObject={paintNode}
        nodeCanvasObjectMode={() => "replace"}
        linkCanvasObject={paintLink}
        linkCanvasObjectMode={() => "replace"}
        enableNodeDrag={false}
        onNodeClick={(node) => onNodeClick?.(node as unknown as GraphNode)}
        onNodeHover={(node) => setHoverNodeId(node ? (node as unknown as GraphNode).id : null)}
        backgroundColor="#f9fafb"
        width={undefined}
        height={undefined}
      />
      <div className="absolute bottom-3 left-3 z-10 flex flex-col gap-1
                      rounded bg-white/80 px-2 py-1 text-xs shadow">
        <div className="flex gap-3">
          {LEGEND_DOMAINS.map(({ label, color }) => (
            <span key={label} className="flex items-center gap-1">
              <span className="inline-block h-3 w-3 rounded-full" style={{ background: color }} />
              {label}
            </span>
          ))}
        </div>
        <div className="flex gap-3 border-t pt-1">
          {LEGEND_EDGES.map(({ label, color }) => (
            <span key={label} className="flex items-center gap-1">
              <span className="inline-block h-0.5 w-4" style={{ background: color }} />
              {label}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
