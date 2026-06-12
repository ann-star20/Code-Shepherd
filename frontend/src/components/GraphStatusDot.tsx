import type { StepStatus } from "@/types/graphPipeline";

interface Config {
  cls: string;
  icon: string;
}

const STATUS_CONFIG: Record<StepStatus, Config> = {
  PENDING: { cls: "bg-gray-300",              icon: "·" },
  RUNNING: { cls: "bg-blue-500 animate-pulse", icon: "·" },
  DONE:    { cls: "bg-green-500",              icon: "✓" },
  FAILED:  { cls: "bg-red-500",               icon: "✕" },
};

interface GraphStatusDotProps {
  status: StepStatus;
  label?: string;
}

export function GraphStatusDot({ status, label }: GraphStatusDotProps) {
  const { cls, icon } = STATUS_CONFIG[status];
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block h-2.5 w-2.5 rounded-full ${cls}`} />
      <span className="text-sm">{label ?? icon}</span>
    </span>
  );
}
