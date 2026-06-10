import { apiClient } from "./api";

export interface PrescanResult {
  doc_id?: string;
  original_url?: string;
  framework?: string;
  version?: string;
  lang?: string;
  doc_lang?: string;
  infer_confidence?: number;
  infer_status?: "auto" | "manual_required";
  suggested_frameworks?: string[];
  suggested_versions?: string[];
}

export interface OrchestratorCallbacks {
  onLog: (type: string, message: string) => void;
}

export interface PipelineStartResult {
  docId: string;
  sessionId: string | null;
  needsManualMetadata?: boolean;
  prescanResult?: PrescanResult;
}

export interface LearnMetadataPayload {
  framework: string;
  pattern: string;
  supported_langs: string[];
  default_lang?: string;
}

export async function registerDocument(url: string): Promise<string> {
  const { data } = await apiClient.post("/documents", { urls: [url] });
  return data.documents[0].doc_id;
}

export async function prescanDocument(docId: string): Promise<PrescanResult> {
  const { data } = await apiClient.post(`/documents/${docId}/prescan`);
  return data;
}

export async function triggerPipeline(docId: string): Promise<string> {
  const { data } = await apiClient.post("/pipeline/trigger", { doc_id: docId });
  return data.session_id;
}

export async function learnFrameworkMetadata(payload: LearnMetadataPayload): Promise<void> {
  await apiClient.post("/documents/metadata/learn", payload);
}

/** 프리스캔 완료 이후 단계 (트리거 + 로그). HITL 메타데이터 보정 후 재진입에도 사용. */
export async function continuePipeline(
  docId: string,
  callbacks: OrchestratorCallbacks,
): Promise<PipelineStartResult> {
  const sessionId = await triggerPipeline(docId);
  callbacks.onLog("CRAWLER", `2단계 [Crawler Agent] 개시 — session: ${sessionId.slice(0, 8)}...`);

  return { docId, sessionId };
}

/** 등록 → 프리스캔 → 트리거 순서 보장. existingDocId가 있으면 등록 단계 생략. */
export async function runPipelineStart(
  urls: string[],
  existingDocId: string | null,
  callbacks: OrchestratorCallbacks,
): Promise<PipelineStartResult> {
  let docId = existingDocId;

  if (!docId) {
    docId = await registerDocument(urls[0]);
    callbacks.onLog("INPUT", `[EXT] 문서 등록 완료: ${docId}`);
  }

  const ps = await prescanDocument(docId);
  callbacks.onLog(
    "INPUT",
    `프리스캔 완료: framework=${ps.framework ?? "unknown"}, confidence=${(ps.infer_confidence ?? 0).toFixed(2)}`,
  );

  if (ps.infer_status === "manual_required") {
    return { docId, sessionId: null, needsManualMetadata: true, prescanResult: ps };
  }

  return continuePipeline(docId, callbacks);
}
