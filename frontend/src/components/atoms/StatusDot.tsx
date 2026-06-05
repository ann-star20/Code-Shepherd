import type { StepStatus } from "@/types/pipeline";

interface StatusDotProps {
  status: StepStatus;
  label?: string;
}

const STATUS_CONFIG: Record<StepStatus, { cls: string; icon: string }> = {
  PENDING:  { cls: "bg-gray-300",               icon: "·" },
  RUNNING:  { cls: "bg-blue-500 animate-pulse",  icon: "·" },
  DONE:     { cls: "bg-green-500 done-check",    icon: "✓" },
  FAILED:   { cls: "bg-red-500",                 icon: "✕" },
};

export function StatusDot({ status, label }: StatusDotProps) {
  const { cls, icon } = STATUS_CONFIG[status];
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className={`inline-block h-2.5 w-2.5 rounded-full ${cls}`} aria-hidden="true" />
      <span className="text-sm">{label ?? icon}</span>
    </span>
  );
}
