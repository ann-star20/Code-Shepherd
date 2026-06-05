import type { ConceptDomain, NodeStatus } from "./concept";

export interface GraphNode {
  id: string;
  name: string;
  domain: ConceptDomain;
  status: NodeStatus;
  x?: number;
  y?: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface VirtualNodeStyle {
  opacity: number;
  strokeDasharray: string;
  color: string;
}
