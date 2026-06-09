export type ConceptDomain = "security" | "performance" | "both";
export type NodeStatus = "DRAFT" | "APPROVED" | "COMMITTED" | "REJECTED" | "MERGE_PENDING";
export type Severity = "critical" | "high" | "medium" | "low";

export interface ConceptNode {
  id: string;
  name: string;
  domain: ConceptDomain;
  status: NodeStatus;
  cwe_id?: string;
  severity?: Severity;
  description_ko?: string;
  aliases: string[];
  tags: string[];
}
