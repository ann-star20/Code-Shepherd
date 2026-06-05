export interface ChatRequest {
  question: string;
  top_k?: number;
}

export interface ChatSource {
  chunk_id: string;
  content: string;
  score: number;
  doc_title: string | null;
  source_type: "pgvector" | "postgresql" | "neo4j" | "gcs";
}

export interface ChatResponse {
  question: string;
  answer: string;
  sources: ChatSource[];
  model: string;
  intent: string;
  storages: string[];
}
