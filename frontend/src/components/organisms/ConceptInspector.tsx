import type { ConceptNode, Severity } from "@/types/concept";
import { Badge } from "@/components/atoms/Badge";
import { Button } from "@/components/atoms/Button";

interface ConceptInspectorProps {
  node: ConceptNode | null;
  sessionId: string | null;
  onApprove: (nodeId: string) => void;
  onReject: (nodeId: string) => void;
  onClose: () => void;
}

const SEVERITY_CLASS: Record<Severity, string> = {
  critical: "text-red-600 font-semibold",
  high: "text-orange-500 font-semibold",
  medium: "text-yellow-500",
  low: "text-green-600",
};

export function ConceptInspector({
  node,
  onApprove,
  onReject,
  onClose,
}: ConceptInspectorProps) {
  if (node === null) {
    return (
      <div className="flex h-48 items-center justify-center rounded-lg border bg-white text-sm text-gray-400">
        노드를 클릭하세요
      </div>
    );
  }

  const isDraft = node.status === "DRAFT";

  return (
    <div className="flex flex-col gap-3 rounded-lg border bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <div className="flex items-center gap-2">
          <span className="font-semibold text-gray-900">{node.name}</span>
          <Badge domain={node.domain} size="sm" />
        </div>
        <button
          type="button"
          className="text-gray-400 hover:text-gray-600"
          onClick={onClose}
          aria-label="닫기"
        >
          ✕
        </button>
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-sm">
        {node.cwe_id && (
          <>
            <dt className="text-gray-500">CWE</dt>
            <dd className="font-mono text-gray-800">{node.cwe_id}</dd>
          </>
        )}

        {node.severity && (
          <>
            <dt className="text-gray-500">Severity</dt>
            <dd className={SEVERITY_CLASS[node.severity]}>{node.severity}</dd>
          </>
        )}

        {node.description_ko && (
          <>
            <dt className="text-gray-500">설명</dt>
            <dd className="text-gray-800">{node.description_ko}</dd>
          </>
        )}

        {node.aliases.length > 0 && (
          <>
            <dt className="text-gray-500">별칭</dt>
            <dd className="flex flex-wrap gap-1">
              {node.aliases.map((a) => (
                <span key={a} className="rounded bg-gray-100 px-1.5 py-0.5 text-xs text-gray-700">
                  {a}
                </span>
              ))}
            </dd>
          </>
        )}

        {node.tags.length > 0 && (
          <>
            <dt className="text-gray-500">태그</dt>
            <dd className="flex flex-wrap gap-1">
              {node.tags.map((t) => (
                <span key={t} className="rounded bg-blue-50 px-1.5 py-0.5 text-xs text-blue-700">
                  {t}
                </span>
              ))}
            </dd>
          </>
        )}
      </dl>

      {isDraft && (
        <div className="flex gap-2 border-t pt-3">
          <Button variant="primary" onClick={() => onApprove(node.id)}>승인</Button>
          <Button variant="danger" onClick={() => onReject(node.id)}>거부</Button>
        </div>
      )}
    </div>
  );
}
