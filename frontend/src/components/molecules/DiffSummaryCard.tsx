interface DiffSummaryCardProps {
  newCount: number;
  updateCount: number;
  mergeCount: number;
}

export function DiffSummaryCard({ newCount, updateCount, mergeCount }: DiffSummaryCardProps) {
  return (
    <div className="flex gap-4 rounded-lg border bg-white px-4 py-3 text-sm shadow-sm">
      <span>
        신규 <strong>{newCount}</strong>개
      </span>
      <span className="text-gray-300">·</span>
      <span>
        업데이트 <strong>{updateCount}</strong>개
      </span>
      <span className="text-gray-300">·</span>
      <span>
        병합 <strong>{mergeCount}</strong>개
      </span>
    </div>
  );
}
