import type { Domain, GraphEdgeType, GraphLayer, InferAction, NodeStatus, NodeStyle } from "@/types/graphPipeline";

export const DOMAIN_COLOR: Record<Domain | "rejected" | "default", string> = {
  security:    "#1D9E75",
  performance: "#BA7517",
  both:        "#534AB7",
  rejected:    "#E24B4A",
  default:     "#94a3b8",
};

export const DOMAIN_BADGE_CLASS: Record<Domain, string> = {
  security:    "bg-teal-100 text-teal-800",
  performance: "bg-orange-100 text-orange-800",
  both:        "bg-purple-100 text-purple-800",
};

export const ACTION_CLASS: Record<InferAction, string> = {
  NEW:        "bg-sky-100 text-sky-800",
  MERGE:      "bg-violet-100 text-violet-800",
  RELATED_TO: "bg-amber-100 text-amber-800",
};

export const SEVERITY_CLASS: Record<string, string> = {
  critical: "text-red-600 font-semibold",
  high:     "text-orange-500 font-semibold",
  medium:   "text-yellow-500",
  low:      "text-green-600",
};

export function getNodeStyle(status: NodeStatus, color: string): NodeStyle {
  switch (status) {
    case "COMMITTED":
      return { opacity: 1,    dashed: false, color };
    case "DRAFT":
      return { opacity: 0.65, dashed: true,  color };
    case "MERGE_PENDING":
      return { opacity: 1,    dashed: false, color, ring: "#8B5CF6" };
    case "REJECTED":
      return { opacity: 0.3,  dashed: false, color: "#E24B4A" };
    default:
      return { opacity: 0.5,  dashed: true,  color: DOMAIN_COLOR.default };
  }
}

export function formatConfidence(score: number): string {
  return `${(score * 100).toFixed(1)}%`;
}

export const LAYER_RADIUS: Record<GraphLayer, number> = {
  L1: 10,
  L2: 6,
  L3: 3.5,
  L4: 2.5,
};

export const EDGE_STYLE: Record<GraphEdgeType, { color: string; dashed: boolean; width: number }> = {
  BELONGS_TO:   { color: "#94a3b8", dashed: false, width: 1.5 },
  MITIGATED_BY: { color: "#1D9E75", dashed: false, width: 1 },
  CAUSED_BY:    { color: "#E24B4A", dashed: false, width: 1 },
  AFFECTS:      { color: "#BA7517", dashed: false, width: 1 },
  HAS_EXAMPLE:  { color: "#534AB7", dashed: true,  width: 1 },
  RELATED_TO:   { color: "#94a3b8", dashed: true,  width: 1 },
};
