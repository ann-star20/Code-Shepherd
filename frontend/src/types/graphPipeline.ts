export type PipelineState =
  | "IDLE"
  | "RUNNING"
  | "WAITING_APPROVAL"
  | "COMMITTING"
  | "FINISHED"
  | "ERROR";

export type StepStatus = "PENDING" | "RUNNING" | "DONE" | "FAILED";
export type StepName = "Input" | "Crawler" | "Extractor" | "Writer" | "Resolver";
export type StepStatuses = Record<StepName, StepStatus>;

export type Domain = "security" | "performance" | "both";
export type InferAction = "NEW" | "MERGE" | "RELATED_TO";
export type NodeStatus = "COMMITTED" | "DRAFT" | "MERGE_PENDING" | "REJECTED";
export type ToastKind = "info" | "success" | "warning" | "error";

export interface MechanismInfo {
  mechanism_name: string;
  code_examples: CodeExampleInfo[];
}

export interface CodeExampleInfo {
  lang: string;
  lang_version: string;
  framework: string;
  code: string;
  description: string;
}

export interface GraphNode {
  id: string;
  name: string;
  status: NodeStatus;
  domains: Domain[];
  infer_action?: InferAction;
  infer_confidence?: number;
  target_concept_name?: string;
  cwe_id?: string;
  owasp_id?: string;
  severity?: string;
  description_ko?: string;
  aliases?: string[];
  mechanisms?: MechanismInfo[];
  x?: number;
  y?: number;
}

export interface GraphEdge {
  source: string;
  target: string;
  type: string;
}

export interface DiffSummary {
  draft: number;
  approved: number;
  committed: number;
}

export interface StagingConcept extends GraphNode {
  staging_id: number;
  state: "DRAFT" | "APPROVED" | "REJECTED";
}

export interface ToastItem {
  id: string;
  kind: ToastKind;
  message: string;
}

export interface SSEPayload {
  type: "connected" | "log" | "step_update" | "heartbeat" | "finished";
  step?: StepName;
  status?: StepStatus;
  agent?: string;
  message?: string;
  ts?: string;
}

export interface PrescanResult {
  original_url: string;
  framework?: string;
  infer_confidence?: number;
  suggestions?: string[];
}

export interface MetadataLearnPayload {
  framework: string;
  pattern: string;
  supported_langs: string[];
  default_lang?: string;
}

export interface NodeStyle {
  opacity: number;
  dashed: boolean;
  color: string;
  ring?: string;
}
