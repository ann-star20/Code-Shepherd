import type { StepStatuses, StepName } from "@/types/graphPipeline";
import { GraphStatusDot } from "./GraphStatusDot";

const STEPS: { agent: StepName; desc: string }[] = [
  { agent: "Input",     desc: "링크 유효성 및 ETag 캐싱 분석" },
  { agent: "Crawler",   desc: "DOM 파싱 및 텍스트 블록 정제" },
  { agent: "Extractor", desc: "Gemini 구조화 의미 스키마 추출" },
  { agent: "Writer",    desc: "PostgreSQL / Neo4j 스테이징 적재" },
  { agent: "Resolver",  desc: "하이브리드 유사도 판정 및 동의어 수렴" },
];

interface GraphPipelineStepIndicatorProps {
  statuses: Partial<StepStatuses>;
}

export function GraphPipelineStepIndicator({ statuses }: GraphPipelineStepIndicatorProps) {
  return (
    <ol className="flex flex-col gap-2">
      {STEPS.map(({ agent, desc }) => {
        const status    = statuses[agent] ?? "PENDING";
        const isRunning = status === "RUNNING";
        return (
          <li
            key={agent}
            className={`flex items-start gap-2 rounded px-2 py-1.5 transition
              ${isRunning ? "bg-blue-50 font-bold text-blue-700" : "text-gray-600"}`}
          >
            <GraphStatusDot status={status} />
            <div>
              <p className="text-sm font-medium">{agent}</p>
              <p className="text-xs text-gray-400">{desc}</p>
            </div>
          </li>
        );
      })}
    </ol>
  );
}
