import type { ConceptNode, NodeStatus } from "./concept";

export type AgentStep = "Input" | "Crawler" | "Extractor" | "Writer" | "Resolver";
export type StepStatus = "PENDING" | "RUNNING" | "DONE" | "FAILED";

export interface PipelineStep {
  agent: AgentStep;
  status: StepStatus;
}

export interface StagingRecord {
  id: string;
  session_id: string;
  concept_json: ConceptNode;
  state: NodeStatus;
}
