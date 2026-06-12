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

interface UseGraphPipelineSSEOptions {
  sessionId: string | null;
  onLog: (line: string) => void;
  onFinished: () => void;
  onError: (msg: string) => void;
}

export function useGraphPipelineSSE({
  sessionId,
  onLog,
  onFinished,
  onError,
}: UseGraphPipelineSSEOptions) {
  const [stepStatuses, setStepStatuses] = useState<StepStatuses>(DEFAULT_STATUSES);
  const [isConnected, setIsConnected]   = useState(false);
  const esRef = useRef<EventSource | null>(null);

  const reset = useCallback(() => {
    setStepStatuses({ ...DEFAULT_STATUSES });
    setIsConnected(false);
  }, []);

  useEffect(() => {
    if (!sessionId) return;

    const es = graphPipelineApi.subscribeSSE(sessionId);
    esRef.current = es;

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
          break;
        case "log":
          if (payload.message) {
            const ts = payload.ts ? `[${payload.ts}] ` : "";
            const agent = payload.agent ? `[${payload.agent}] ` : "";
            onLog(`${ts}${agent}${payload.message}`);
          }
          break;
        case "finished":
          setIsConnected(false);
          onFinished();
          es.close();
          break;
        case "heartbeat":
          break;
        default:
          break;
      }
    };

    es.onerror = () => {
      setIsConnected(false);
      onError("SSE 연결 오류가 발생했습니다.");
      es.close();
    };

    return () => {
      es.close();
      esRef.current = null;
    };
  }, [sessionId, onLog, onFinished, onError]);

  return { stepStatuses, isConnected, reset };
}
