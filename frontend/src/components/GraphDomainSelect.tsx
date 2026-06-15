import type { Domain } from "@/types/graphPipeline";

interface GraphDomainSelectProps {
  value: Domain | "all";
  onChange: (value: Domain | "all") => void;
}

const OPTIONS: { value: Domain | "all"; label: string }[] = [
  { value: "all",         label: "전체" },
  { value: "security",    label: "security" },
  { value: "performance", label: "performance" },
  { value: "both",        label: "both" },
];

export function GraphDomainSelect({ value, onChange }: GraphDomainSelectProps) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value as Domain | "all")}
      aria-label="도메인 선택"
      className="w-full rounded-lg border border-gray-300 px-2 py-1.5 text-sm
                 focus:outline-none focus:ring-2 focus:ring-blue-500"
    >
      {OPTIONS.map((opt) => (
        <option key={opt.value} value={opt.value}>
          {opt.label}
        </option>
      ))}
    </select>
  );
}
