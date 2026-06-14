interface GraphDiffSummaryCardProps {
  newCount: number;
  updateCount: number;
  mergeCount: number;
}

export function GraphDiffSummaryCard({ newCount, updateCount, mergeCount }: GraphDiffSummaryCardProps) {
  return (
    <div className="flex gap-4 rounded-lg border bg-white px-4 py-3 text-sm shadow-sm">
      <span>신규 <strong className="text-sky-700">{newCount}</strong>개</span>
      <span className="text-gray-300">·</span>
      <span>업데이트 <strong className="text-violet-700">{updateCount}</strong>개</span>
      <span className="text-gray-300">·</span>
      <span>병합 <strong className="text-amber-700">{mergeCount}</strong>개</span>
    </div>
  );
}
