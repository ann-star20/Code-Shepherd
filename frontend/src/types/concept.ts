export type ConceptDomain = "security" | "performance" | "both";
export type NodeStatus = "DRAFT" | "APPROVED" | "COMMITTED" | "REJECTED";
export type Severity = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

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
