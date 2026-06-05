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

    source.addEventListener("step_update", (e: Event) => {
      const { agent, status } = JSON.parse((e as MessageEvent).data) as {
        agent: string;
        status: PipelineStep["status"];
      };
      setSteps((prev) => prev.map((s) => (s.agent === agent ? { ...s, status } : s)));
    });

    source.addEventListener("log", (e: Event) => {
      setLogs((prev) => [...prev, (e as MessageEvent).data]);
    });

    source.onerror = () => setIsConnected(false);

    return () => {
      source.close();
      setIsConnected(false);
    };
  }, [sessionId]);

  return { steps, logs, isConnected };
}
