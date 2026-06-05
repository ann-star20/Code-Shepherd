export interface UploadResponse {
  doc_id: string;
  status: string;
  message: string;
  quality_score: number | null;
  hitl_required: boolean;
  chunk_count: number | null;
}

export interface StatusResponse {
  doc_id: string;
  status: string;
  current_stage: string | null;
  error: string | null;
  agent_traces: AgentTraceItem[];
}

export interface SearchResultItem {
  chunk_id: string;
  content: string;
  score: number;
  metadata: Record<string, unknown> | null;
  doc_title: string | null;
}

export interface SearchResponse {
  query: string;
  results: SearchResultItem[];
  total: number;
}

export interface AgentTraceItem {
  trace_id: string;
  agent_name: string;
  status: "running" | "success" | "fail";
  started_at: string | null;
  ended_at: string | null;
  execution_ms: number | null;
  error_message: string | null;
}

export interface ChunkItem {
  chunk_id: string;
  chunk_type: "parent" | "child";
  content: string;
  token_count: number | null;
  section_header: string | null;
  page_number: number | null;
}

export interface DocDetailsResponse {
  doc_id: string;
  title: string | null;
  file_type: string | null;
  status: string;
  created_at: string | null;
  agent_traces: AgentTraceItem[];
  chunks: ChunkItem[];
}

// HITL

export interface HitlQueueItem {
  queue_id: string;
  doc_id: string;
  stage: string;
  reason: string;
  quality_score: number | null;
  issues: Record<string, unknown> | unknown[] | null;
  status: "pending" | "approved" | "rejected" | "reprocessing";
  reviewer_id: string | null;
  review_note: string | null;
  created_at: string;
  original_filename?: string | null;
  file_type?: string | null;
  parser_used?: string | null;
}

export interface HitlQueuePageResponse {
  items: HitlQueueItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface ApproveRequest {
  reviewer_id: string;
  review_note?: string;
  auto_reprocess?: boolean;
}

export interface RejectRequest {
  reviewer_id: string;
  review_note: string;
}

export interface ReprocessRequest {
  reviewer_id: string;
  corrected_markdown?: string;
  skip_validation?: boolean;
}
