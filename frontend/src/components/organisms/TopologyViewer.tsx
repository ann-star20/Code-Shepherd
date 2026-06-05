import ForceGraph2D from "react-force-graph-2d";
import type { GraphNode } from "@/types/graph";
import { useGraphMerge } from "@/hooks/useGraphMerge";
import { getDomainColor, getNodeStyle } from "@/utils/nodeStyler";
import { Spinner } from "@/components/atoms/Spinner";

interface TopologyViewerProps {
  sessionId: string | null;
  onNodeClick: (node: GraphNode) => void;
}

const LEGEND = [
  { label: "Security",     color: "#1D9E75" },
  { label: "Performance",  color: "#BA7517" },
  { label: "Both",         color: "#534AB7" },
  { label: "Draft (점선)", color: "#94a3b8" },
];

export function TopologyViewer({ sessionId, onNodeClick }: TopologyViewerProps) {
  const { nodes, edges, isLoading } = useGraphMerge(sessionId);

  if (isLoading) {
    return (
      <div className="flex h-96 items-center justify-center">
        <Spinner size="lg" />
      </div>
    );
  }

  const graphData = {
    nodes: nodes.map((n) => ({
      ...n,
      color: getDomainColor(n.domain),
      opacity: getNodeStyle(n.status, n.domain).opacity,
    })),
    links: edges.map((e) => ({
      source: e.source,
      target: e.target,
      type: e.type,
    })),
  };

  return (
    <div className="relative rounded-lg border bg-gray-50">
      <ForceGraph2D
        graphData={graphData}
        nodeColor={(n: Record<string, unknown>) => n.color as string}
        onNodeClick={(n) => onNodeClick(n as unknown as GraphNode)}
        width={800}
        height={500}
      />
      <div className="absolute bottom-3 left-3 flex gap-3 rounded bg-white/80 px-2 py-1 text-xs shadow">
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
