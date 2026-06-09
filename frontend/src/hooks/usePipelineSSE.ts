import { useEffect, useState } from "react";
import type { PipelineStep } from "@/types/pipeline";

export interface PipelineSSEState {
  steps: PipelineStep[];
  logs: string[];
  isConnected: boolean;
}

const INITIAL_STEPS: PipelineStep[] = [
  { agent: "Input",     status: "PENDING" },
  { agent: "Crawler",   status: "PENDING" },
  { agent: "Extractor", status: "PENDING" },
  { agent: "Writer",    status: "PENDING" },
  { agent: "Resolver",  status: "PENDING" },
];

export function usePipelineSSE(sessionId: string | null): PipelineSSEState {
  const [steps, setSteps] = useState<PipelineStep[]>(INITIAL_STEPS);
  const [logs, setLogs] = useState<string[]>([]);
  const [isConnected, setIsConnected] = useState(false);

  useEffect(() => {
    if (!sessionId) return;

    const source = new EventSource(`/api/pipeline/stream/${sessionId}`);
    setIsConnected(true);

    source.onmessage = (e: MessageEvent) => {
      const payload = JSON.parse(e.data) as { type: string; [key: string]: unknown };
      if (payload.type === "step_update") {
        const { agent, status } = payload as { type: string; agent: string; status: PipelineStep["status"] };
        setSteps((prev) => prev.map((s) => (s.agent === agent ? { ...s, status } : s)));
      } else if (payload.type === "log") {
        const { message } = payload as { type: string; message: string };
        setLogs((prev) => [...prev, message]);
      }
    };

    source.onerror = () => setIsConnected(false);

    return () => {
      source.close();
      setIsConnected(false);
    };
  }, [sessionId]);

  return { steps, logs, isConnected };
}
