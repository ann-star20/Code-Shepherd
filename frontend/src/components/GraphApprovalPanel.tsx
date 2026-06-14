import type { DiffSummary, StagingConcept } from "@/types/graphPipeline";
import { GraphDiffSummaryCard } from "./GraphDiffSummaryCard";
import { GraphButton, ActionBadge } from "./GraphBadge";

interface GraphApprovalPanelProps {
  diff: DiffSummary | null;
  isLoading: boolean;
  stagingItems?: StagingConcept[];
  onApproveAll: () => void;
  onRejectAll: () => void;
  onSelectItem?: (item: StagingConcept) => void;
}

export function GraphApprovalPanel({
  diff,
  isLoading,
  stagingItems = [],
  onApproveAll,
  onRejectAll,
  onSelectItem,
}: GraphApprovalPanelProps) {
  return (
    <div className="flex flex-col gap-4 rounded-lg border bg-white p-4 shadow-sm">
      {diff === null ? (
        <p className="text-sm text-gray-500">로딩 중...</p>
      ) : (
        <GraphDiffSummaryCard
          newCount={stagingItems.filter((item) => (item.infer_action ?? "NEW") === "NEW").length}
          updateCount={stagingItems.filter((item) => item.infer_action === "RELATED_TO").length}
          mergeCount={stagingItems.filter((item) => item.infer_action === "MERGE").length}
        />
      )}
      {stagingItems.length > 0 && (
        <ul className="flex max-h-40 flex-col gap-1.5 overflow-y-auto border-t pt-2">
          {stagingItems.map((item) => (
            <li
              key={item.staging_id}
              onClick={() => onSelectItem?.(item)}
              className="flex items-center justify-between gap-2 rounded px-1 text-sm
                         hover:bg-gray-50 cursor-pointer"
            >
              <span className="truncate text-gray-800">{item.name}</span>
              {item.infer_action && (
                <ActionBadge
                  action={item.infer_action}
                  confidence={item.infer_confidence}
                  target={item.target_concept_name}
                />
              )}
            </li>
          ))}
        </ul>
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
