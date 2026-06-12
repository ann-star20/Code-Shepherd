import type { DiffSummary } from "@/types/graphPipeline";
import { GraphDiffSummaryCard } from "./GraphDiffSummaryCard";
import { GraphButton } from "./GraphBadge";

interface GraphApprovalPanelProps {
  diff: DiffSummary | null;
  isLoading: boolean;
  onApproveAll: () => void;
  onRejectAll: () => void;
}

export function GraphApprovalPanel({
  diff,
  isLoading,
  onApproveAll,
  onRejectAll,
}: GraphApprovalPanelProps) {
  return (
    <div className="flex flex-col gap-4 rounded-lg border bg-white p-4 shadow-sm">
      {diff === null ? (
        <p className="text-sm text-gray-500">로딩 중...</p>
      ) : (
        <GraphDiffSummaryCard
          newCount={diff.draft}
          updateCount={diff.approved}
          mergeCount={diff.committed}
        />
      )}
      <div className="flex items-center gap-2">
        {isLoading ? (
          <>
            <GraphButton variant="primary" disabled>전체 승인</GraphButton>
            <GraphButton variant="danger" disabled>전체 거부</GraphButton>
            <span className="inline-block h-5 w-5 animate-spin rounded-full
                             border-2 border-blue-500 border-t-transparent" />
          </>
        ) : (
          <>
            <GraphButton variant="primary" onClick={onApproveAll}>전체 승인</GraphButton>
            <GraphButton variant="danger" onClick={onRejectAll}>전체 거부</GraphButton>
          </>
        )}
      </div>
    </div>
  );
}
