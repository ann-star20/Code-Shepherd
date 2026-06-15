import { useEffect, useRef, useState, useCallback } from "react";
import type { SSEPayload, StepStatuses, StepName, StepStatus } from "@/types/graphPipeline";
import { graphPipelineApi } from "@/lib/graphPipelineApi";

const DEFAULT_STATUSES: StepStatuses = {
  Input:     "PENDING",
  Crawler:   "PENDING",
  Extractor: "PENDING",
  Writer:    "PENDING",
  Resolver:  "PENDING",
};

interface MetadataRequiredPayload {
  doc_id: string;
  url: string;
  suggestions: string[];
}

interface UseGraphPipelineSSEOptions {
  sessionId: string | null;
  onLog: (line: string) => void;
  onFinished: () => void;
  onError: (msg: string) => void;
  onSkipped?: (reason: string) => void;
  onMetadataRequired?: (payload: MetadataRequiredPayload) => void;
  onStepFailed?: (step: StepName, reason: string) => void;
}

export function useGraphPipelineSSE({
  sessionId,
  onLog,
  onFinished,
  onError,
  onSkipped,
  onMetadataRequired,
  onStepFailed,
}: UseGraphPipelineSSEOptions) {
  const [stepStatuses, setStepStatuses] = useState<StepStatuses>(DEFAULT_STATUSES);
  const [isConnected, setIsConnected]   = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const finishedRef = useRef(false);

  const reset = useCallback(() => {
    setStepStatuses({ ...DEFAULT_STATUSES });
    setIsConnected(false);
  }, []);

  const setStepStatus = useCallback((step: StepName, status: StepStatus) => {
    setStepStatuses((prev) => ({ ...prev, [step]: status }));
  }, []);

  useEffect(() => {
    if (!sessionId) return;

    const es = graphPipelineApi.subscribeSSE(sessionId);
    esRef.current = es;
    finishedRef.current = false;

    es.onopen = () => setIsConnected(true);

    es.onmessage = (e: MessageEvent) => {
      let payload: SSEPayload;
      try {
        payload = JSON.parse(e.data as string) as SSEPayload;
      } catch {
        return;
      }

      switch (payload.type) {
        case "step_update":
          if (payload.step && payload.status) {
            setStepStatuses((prev) => ({
              ...prev,
              [payload.step as StepName]: payload.status as StepStatus,
            }));
          }
          if (payload.status === "SKIPPED") {
            onSkipped?.(payload.reason ?? "이미 처리된 문서로 파이프라인을 건너뜁니다.");
          }
          if (payload.status === "FAILED" && payload.step && payload.reason) {
            onStepFailed?.(payload.step as StepName, payload.reason);
          }
          break;
        case "log":
          if (payload.message) {
            const ts = payload.ts ? `[${payload.ts}] ` : "";
            const agent = payload.agent ? `[${payload.agent}] ` : "";
            onLog(`${ts}${agent}${payload.message}`);
          }
          break;
        case "finished":
          finishedRef.current = true;
          setIsConnected(false);
          onFinished();
          es.close();
          break;
        case "heartbeat":
          break;
        case "metadata_required":
          if (payload.doc_id && payload.url) {
            onMetadataRequired?.({
              doc_id: payload.doc_id,
              url: payload.url,
              suggestions: payload.suggestions ?? [],
            });
          }
          break;
        default:
          break;
      }
    };

    es.onerror = () => {
      if (finishedRef.current) return;
      setIsConnected(false);
      onError("SSE 연결 오류가 발생했습니다.");
      es.close();
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [sessionId, onLog, onFinished, onError, onSkipped, onMetadataRequired, onStepFailed]);

  return { stepStatuses, isConnected, reset, setStepStatus };
}
