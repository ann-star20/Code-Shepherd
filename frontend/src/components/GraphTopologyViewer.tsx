import { useCallback, useRef } from "react";
import ForceGraph2D, { type ForceGraphMethods } from "react-force-graph-2d";
import type { GraphNode, GraphEdge } from "@/types/graphPipeline";
import { getNodeStyle, DOMAIN_COLOR } from "@/lib/graphFormatters";

interface GraphTopologyViewerProps {
  nodes: GraphNode[];
  edges: GraphEdge[];
  onNodeClick?: (node: GraphNode) => void;
}

const LEGEND = [
  { label: "security",     color: DOMAIN_COLOR.security },
  { label: "performance",  color: DOMAIN_COLOR.performance },
  { label: "both",         color: DOMAIN_COLOR.both },
  { label: "draft (점선)", color: DOMAIN_COLOR.default },
];

export function GraphTopologyViewer({ nodes, edges, onNodeClick }: GraphTopologyViewerProps) {
  const fgRef = useRef<ForceGraphMethods>();

  const paintNode = useCallback(
    (node: object, ctx: CanvasRenderingContext2D) => {
      const n = node as GraphNode & { x: number; y: number };
      const domain = n.domains?.[0] ?? "default";
      const style  = getNodeStyle(n.status ?? "COMMITTED", domain);
      const radius = 6;

      ctx.globalAlpha = style.opacity;

      if (style.dashed) {
        ctx.setLineDash([5, 3]);
        ctx.strokeStyle = style.color;
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.arc(n.x, n.y, radius, 0, 2 * Math.PI);
        ctx.stroke();
        ctx.fillStyle = style.color + "40";
        ctx.fill();
        ctx.setLineDash([]);
      } else {
        ctx.fillStyle = style.color;
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

      ctx.globalAlpha = 1;
      ctx.fillStyle = "#374151";
      ctx.font = "4px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(n.name.slice(0, 12), n.x, n.y + radius + 5);
    },
    []
  );

  const graphData = {
    nodes: nodes.map((n) => ({ ...n })),
    links: edges.map((e) => ({ source: e.source, target: e.target, type: e.type })),
  };

  return (
    <div className="relative w-full h-full rounded-lg border bg-gray-50 overflow-hidden">
      <ForceGraph2D
        ref={fgRef}
        graphData={graphData}
        nodeCanvasObject={paintNode}
        nodeCanvasObjectMode={() => "replace"}
        onNodeClick={(node) => onNodeClick?.(node as unknown as GraphNode)}
        linkColor={() => "#d1d5db"}
        linkWidth={1}
        backgroundColor="#f9fafb"
        width={undefined}
        height={undefined}
      />
      <div className="absolute bottom-3 left-3 z-10 flex gap-3
                      rounded bg-white/80 px-2 py-1 text-xs shadow">
        {LEGEND.map(({ label, color }) => (
          <span key={label} className="flex items-center gap-1">
            <span className="inline-block h-3 w-3 rounded-full" style={{ background: color }} />
            {label}
          </span>
        ))}
      </div>
    </div>
  );
}
