import type { Domain, InferAction } from "@/types/graphPipeline";
import { DOMAIN_BADGE_CLASS, ACTION_CLASS } from "@/lib/graphFormatters";

interface DomainBadgeProps {
  domain: Domain;
  size?: "sm" | "md";
}

export function DomainBadge({ domain, size = "sm" }: DomainBadgeProps) {
  const colorCls = DOMAIN_BADGE_CLASS[domain] ?? "bg-gray-100 text-gray-800";
  const sizeCls  = size === "sm" ? "px-1.5 py-0.5 text-xs" : "px-2.5 py-1 text-sm";
  return (
    <span className={`inline-flex items-center rounded-full font-medium ${colorCls} ${sizeCls}`}>
      {domain}
    </span>
  );
}

interface ActionBadgeProps {
  action: InferAction;
  confidence?: number;
  target?: string;
}

export function ActionBadge({ action, confidence, target }: ActionBadgeProps) {
  const cls = ACTION_CLASS[action];
  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-xs font-medium ${cls}`}
    >
      {action === "NEW" && `NEW (${((confidence ?? 0) * 100).toFixed(1)}%)`}
      {action === "MERGE" && `MERGE → ${target ?? ""}`}
      {action === "RELATED_TO" && `RELATED_TO ${target ?? ""}`}
    </span>
  );
}

export function NewTagBadge() {
  return (
    <span className="inline-flex items-center rounded-full bg-orange-100 px-1.5 py-0.5 text-xs font-semibold text-orange-700">
      NEW
    </span>
  );
}

interface GraphButtonProps {
  variant?: "primary" | "danger" | "ghost" | "outline";
  disabled?: boolean;
  onClick?: () => void;
  type?: "button" | "submit" | "reset";
  children: React.ReactNode;
  className?: string;
}

const VARIANT_CLASS = {
  primary: "bg-blue-600 text-white hover:bg-blue-700",
  danger:  "bg-red-600 text-white hover:bg-red-700",
  ghost:   "bg-transparent text-gray-700 hover:bg-gray-100",
  outline: "border border-stone-300 text-stone-700 hover:bg-stone-100",
};

export function GraphButton({
  variant = "primary",
  disabled,
  onClick,
  type = "button",
  children,
  className = "",
}: GraphButtonProps) {
  return (
    <button
      type={type}
      onClick={onClick}
      disabled={disabled}
      className={`rounded-lg px-3.5 py-1.5 text-sm font-semibold transition
        ${VARIANT_CLASS[variant]} disabled:opacity-40 disabled:cursor-not-allowed ${className}`}
    >
      {children}
    </button>
  );
}
