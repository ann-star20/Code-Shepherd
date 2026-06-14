import { useCallback, useMemo, useRef, useState } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";
import type { GraphEdge, GraphNode } from "@/types/graphPipeline";
import { DOMAIN_COLOR, EDGE_STYLE, HITL_FOCUS_RING_COLOR, LAYER_RADIUS, NEW_NODE_RING_COLOR, getNodeStyle } from "@/lib/graphFormatters";
import { computeHierarchicalLayout, type LayoutPosition } from "@/lib/graphLayout";
import { GraphButton } from "./GraphBadge";

interface GraphTopologyViewerProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick?: (node: GraphNode) => void;
  focusNodeId?: string | null;
}

const DIMMED_OPACITY = 0.2;
const HOVER_DIMMED_OPACITY = 0.1;
const LABEL_GAP = 5;

const LEGEND_DOMAINS = [
  { label: "security",     color: DOMAIN_COLOR.security },
  { label: "performance",  color: DOMAIN_COLOR.performance },
  { label: "both",         color: DOMAIN_COLOR.both },
  { label: "draft (점선)", color: DOMAIN_COLOR.default },
  { label: "new (주황 링)", color: NEW_NODE_RING_COLOR },
  { label: "HITL 대상 (파란 점선)", color: HITL_FOCUS_RING_COLOR },
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

export function GraphTopologyViewer({ nodes, edges, onNodeClick, focusNodeId }: GraphTopologyViewerProps) {
  const fgRef = useRef<ForceGraphMethods>();
  const [hoverNodeId, setHoverNodeId] = useState<string | null>(null);
  const positionsRef = useRef<Map<string, LayoutPosition>>(new Map());
  const [layoutVersion, setLayoutVersion] = useState(0);

  const graphData = useMemo(() => {
    const visibleNodes = nodes.filter((n) => n.layer !== "L4");
    const visibleIds = new Set(visibleNodes.map((n) => n.id));
    const visibleEdges = edges.filter(
      (e) => visibleIds.has(e.source) && visibleIds.has(e.target)
    );

    const computed = computeHierarchicalLayout(visibleNodes, visibleEdges);
    const positionedNodes = visibleNodes.map((n) => {
      const pos = positionsRef.current.get(n.id) ?? computed.get(n.id) ?? { x: 0, y: 0 };
      positionsRef.current.set(n.id, pos);
      return { ...n, x: pos.x, y: pos.y, fx: pos.x, fy: pos.y };
    });

    return {
      nodes: positionedNodes,
      links: visibleEdges.map((e) => ({ source: e.source, target: e.target, type: e.type })),
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [nodes, edges, layoutVersion]);

  const handleNodeDragEnd = useCallback((node: object) => {
    const n = node as GraphNode & { x: number; y: number };
    positionsRef.current.set(n.id, { x: n.x, y: n.y });
  }, []);

  const handleRelayout = useCallback(() => {
    positionsRef.current.clear();
    setLayoutVersion((v) => v + 1);
  }, []);

  const nodesById = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const focusedIds = useMemo(
    () => buildFocusSet(focusNodeId, edges, nodesById),
    [focusNodeId, edges, nodesById]
  );

  const hoverFocusedIds = useMemo(
    () => buildFocusSet(hoverNodeId, edges, nodesById),
    [hoverNodeId, edges, nodesById]
  );

  const hitlFocusIds = useMemo(
    () =>
      new Set(
        nodes
          .filter((n) => n.status === "DRAFT" || n.status === "MERGE_PENDING")
          .map((n) => n.id)
      ),
    [nodes]
  );

  const activeFocusIds =
    hoverFocusedIds ?? focusedIds ?? (hitlFocusIds.size > 0 ? hitlFocusIds : null);
  const activeDimOpacity = hoverFocusedIds ? HOVER_DIMMED_OPACITY : DIMMED_OPACITY;

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

      if (n.is_new) {
        ctx.setLineDash([2, 2]);
        ctx.strokeStyle = NEW_NODE_RING_COLOR;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(n.x, n.y, radius + 3, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.setLineDash([]);
      }

      if (n.id === focusNodeId) {
        ctx.strokeStyle = "#2563EB";
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(n.x, n.y, radius + 4, 0, 2 * Math.PI);
        ctx.stroke();
      }

      if (hitlFocusIds.has(n.id)) {
        ctx.setLineDash([3, 2]);
        ctx.strokeStyle = HITL_FOCUS_RING_COLOR;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(n.x, n.y, radius + 5, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.setLineDash([]);
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
    [focusNodeId, hoverNodeId, hoverFocusedIds, focusedIds, activeFocusIds, activeDimOpacity, hitlFocusIds]
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
        cooldownTicks={0}
        nodeCanvasObject={paintNode}
        nodeCanvasObjectMode={() => "replace"}
        linkCanvasObject={paintLink}
        linkCanvasObjectMode={() => "replace"}
        enableNodeDrag={true}
        onNodeDragEnd={handleNodeDragEnd}
        onNodeClick={(node) => onNodeClick?.(node as unknown as GraphNode)}
        onNodeHover={(node) => setHoverNodeId(node ? (node as unknown as GraphNode).id : null)}
        backgroundColor="#f9fafb"
        width={undefined}
        height={undefined}
      />
      <div className="absolute top-3 right-3 z-10">
        <GraphButton variant="outline" onClick={handleRelayout} className="bg-white/90 shadow">
          배치 정렬
        </GraphButton>
      </div>
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
