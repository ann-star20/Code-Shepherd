import type { ConceptDomain, NodeStatus } from "@/types/concept";
import type { VirtualNodeStyle } from "@/types/graph";

const DOMAIN_COLOR: Record<ConceptDomain, string> = {
  security: "#1D9E75",
  performance: "#BA7517",
  both: "#534AB7",
};

const REJECTED_COLOR = "#E24B4A";

export function getDomainColor(domain: ConceptDomain): string {
  return DOMAIN_COLOR[domain];
}

export function getNodeStyle(status: NodeStatus, domain: ConceptDomain): VirtualNodeStyle {
  if (status === "REJECTED") {
    return { opacity: 0.5, strokeDasharray: "3,3", color: REJECTED_COLOR };
  }
  if (status === "DRAFT") {
    return { opacity: 0.65, strokeDasharray: "5,3", color: getDomainColor(domain) };
  }
  return { opacity: 1, strokeDasharray: "none", color: getDomainColor(domain) };
}
