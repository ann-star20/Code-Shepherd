import type { Domain, InferAction, NodeStatus, NodeStyle } from "@/types/graphPipeline";

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

export function getNodeStyle(status: NodeStatus, domain: string): NodeStyle {
  const color = DOMAIN_COLOR[domain as Domain] ?? DOMAIN_COLOR.default;
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
