import type { DiffSummary } from "@/services/stagingService";
import { Button } from "@/components/atoms/Button";
import { Spinner } from "@/components/atoms/Spinner";
import { DiffSummaryCard } from "@/components/molecules/DiffSummaryCard";

interface ApprovalPanelProps {
  sessionId: string | null;
  onApproveAll: () => void;
  onRejectAll: () => void;
  diff: DiffSummary | null;
  isLoading: boolean;
}

export function ApprovalPanel({ onApproveAll, onRejectAll, diff, isLoading }: ApprovalPanelProps) {
  return (
    <div className="flex flex-col gap-4 rounded-lg border bg-white p-4 shadow-sm">
      {diff === null ? (
        <p className="text-sm text-gray-500">로딩 중...</p>
      ) : (
        <DiffSummaryCard newCount={diff.draft} updateCount={diff.approved} mergeCount={diff.committed} />
      )}

      <div className="flex gap-2">
        {isLoading ? (
          <>
            <button type="button" disabled className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white opacity-50">
              전체 승인
            </button>
            <button type="button" disabled className="rounded bg-red-600 px-3 py-1.5 text-sm text-white opacity-50">
              전체 거부
            </button>
            <Spinner size="sm" />
          </>
        ) : (
          <>
            <Button variant="primary" onClick={onApproveAll}>전체 승인</Button>
            <Button variant="danger" onClick={onRejectAll}>전체 거부</Button>
          </>
        )}
      </div>
    </div>
  );
}
