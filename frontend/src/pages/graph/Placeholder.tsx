import type { ToastItem, ToastKind } from "@/types/graphPipeline";
import { useGraphToast } from "@/hooks/useGraphToast";
import { GraphPipelineContainer } from "@/components/GraphPipelineContainer";

const KIND_CLASS: Record<ToastKind, string> = {
  success: "bg-emerald-50 border-emerald-200 text-emerald-800",
  error:   "bg-rose-50 border-rose-200 text-rose-800",
  warning: "bg-amber-50 border-amber-200 text-amber-800",
  info:    "bg-white border-stone-200 text-stone-800",
};
const KIND_ICON: Record<ToastKind, string> = {
  success: "✓",
  error:   "✗",
  warning: "⚠",
  info:    "ℹ",
};

function ToastContainer({
  toasts,
  onDismiss,
}: {
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}) {
  return (
    <div
      className="fixed top-4 right-4 z-50 space-y-2 pointer-events-none"
      role="status"
      aria-live="polite"
    >
      {toasts.map((t) => (
        <div
          key={t.id}
          className={`pointer-events-auto flex items-center gap-2 rounded-xl border
            px-4 py-3 shadow-lg text-sm font-medium max-w-sm ${KIND_CLASS[t.kind]}`}
        >
          <span className="shrink-0">{KIND_ICON[t.kind]}</span>
          <span className="flex-1">{t.message}</span>
          <button
            onClick={() => onDismiss(t.id)}
            className="shrink-0 text-stone-400 hover:text-stone-600"
            aria-label="닫기"
          >
            ×
          </button>
        </div>
      ))}
    </div>
  );
}

export default function GraphPage() {
  const { toasts, addToast, dismiss } = useGraphToast();

  return (
    <div className="flex h-full flex-col" data-testid="graph-page">
      <ToastContainer toasts={toasts} onDismiss={dismiss} />
      <GraphPipelineContainer onToast={addToast} />
    </div>
  );
}
