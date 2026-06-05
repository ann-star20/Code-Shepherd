import type { PipelineStep } from "@/types/pipeline";
import { StatusDot } from "@/components/atoms/StatusDot";

interface PipelineStepIndicatorProps {
  steps: PipelineStep[];
}

export function PipelineStepIndicator({ steps }: PipelineStepIndicatorProps) {
  return (
    <ol className="flex flex-col gap-2">
      {steps.map((step) => {
        const isRunning = step.status === "RUNNING";
        return (
          <li
            key={step.agent}
            data-running={isRunning || undefined}
            className={`flex items-center gap-2 rounded px-2 py-1 ${
              isRunning ? "bg-blue-50 font-bold text-blue-700" : "text-gray-600"
            }`}
          >
            <StatusDot status={step.status} />
            <span>{step.agent}</span>
          </li>
        );
      })}
    </ol>
  );
}
