import type { ConceptDomain } from "@/types/concept";

interface BadgeProps {
  domain: ConceptDomain;
  label?: string;
  size?: "sm" | "md";
}

const DOMAIN_CLASS: Record<ConceptDomain, string> = {
  security: "bg-teal-100 text-teal-800",
  performance: "bg-orange-100 text-orange-800",
  both: "bg-purple-100 text-purple-800",
};

const SIZE_CLASS = { sm: "px-1.5 py-0.5 text-xs", md: "px-2.5 py-1 text-sm" };

export function Badge({ domain, label, size = "md" }: BadgeProps) {
  return (
    <span className={`inline-flex items-center rounded-full font-medium ${DOMAIN_CLASS[domain]} ${SIZE_CLASS[size]}`}>
      {label ?? domain}
    </span>
  );
}
