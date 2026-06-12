import type { GraphNode } from "@/types/graphPipeline";
import { SEVERITY_CLASS } from "@/lib/graphFormatters";
import { DomainBadge, ActionBadge, GraphButton } from "./GraphBadge";

interface GraphConceptInspectorProps {
  node: GraphNode | null;
  isDraft: boolean;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
  onClose: () => void;
}

export function GraphConceptInspector({
  node,
  isDraft,
  onApprove,
  onReject,
  onClose,
}: GraphConceptInspectorProps) {
  if (!node) {
    return (
      <div className="flex h-48 items-center justify-center rounded-lg border bg-white
                      text-sm text-gray-400">
        노드를 클릭하세요
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-semibold text-gray-900">{node.name}</span>
          {node.domains?.map((d) => (
            <DomainBadge key={d} domain={d} size="sm" />
          ))}
          {node.infer_action && (
            <ActionBadge
              action={node.infer_action}
              confidence={node.infer_confidence}
              target={node.target_concept_name}
            />
          )}
        </div>
        <button
          onClick={onClose}
          className="shrink-0 text-gray-400 hover:text-gray-600 text-sm"
          aria-label="닫기"
        >
          ✕
        </button>
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1.5 text-sm">
        {node.cwe_id && (
          <>
            <dt className="text-gray-400 whitespace-nowrap">CWE</dt>
            <dd className="font-mono text-gray-800">{node.cwe_id}</dd>
          </>
        )}
        {node.owasp_id && (
          <>
            <dt className="text-gray-400 whitespace-nowrap">OWASP</dt>
            <dd className="font-mono text-gray-800">{node.owasp_id}</dd>
          </>
        )}
        {node.severity && (
          <>
            <dt className="text-gray-400">Severity</dt>
            <dd className={SEVERITY_CLASS[node.severity] ?? ""}>{node.severity}</dd>
          </>
        )}
        {node.description_ko && (
          <>
            <dt className="text-gray-400 pt-0.5">설명</dt>
            <dd className="text-gray-800 leading-relaxed">{node.description_ko}</dd>
          </>
        )}
        {node.aliases && node.aliases.length > 0 && (
          <>
            <dt className="text-gray-400 pt-0.5">별칭</dt>
            <dd className="flex flex-wrap gap-1">
              {node.aliases.map((a) => (
                <span key={a} className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-700">
                  {a}
                </span>
              ))}
            </dd>
          </>
        )}
        {node.infer_confidence != null && (
          <>
            <dt className="text-gray-400">신뢰도</dt>
            <dd className="flex items-center gap-2">
              <div className="h-1.5 w-24 rounded-full bg-gray-200">
                <div
                  className="h-full rounded-full bg-blue-500 transition-all"
                  style={{ width: `${node.infer_confidence * 100}%` }}
                />
              </div>
              <span className="text-xs text-gray-500">
                {(node.infer_confidence * 100).toFixed(1)}%
              </span>
            </dd>
          </>
        )}
      </dl>

      {node.mechanisms?.length === 0 && (
        <p className="text-xs text-gray-400 italic">코드 예제 없음</p>
      )}

      {isDraft && (
        <div className="flex gap-2 border-t pt-3">
          <GraphButton variant="primary" onClick={() => onApprove(node.id)}>승인</GraphButton>
          <GraphButton variant="danger" onClick={() => onReject(node.id)}>거부</GraphButton>
        </div>
      )}
    </div>
  );
}
