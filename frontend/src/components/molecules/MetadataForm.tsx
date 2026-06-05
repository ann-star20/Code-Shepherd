import type { PreScanResult } from "@/services/pipelineService";

export interface FormMetadata {
  framework?: string;
  version?: string;
  lang?: string;
}

interface MetadataFormProps {
  urls: string[];
  prescanResult?: PreScanResult;
  confidence?: number;
  onConfirm: (metadata: FormMetadata) => void;
  onAddUrl: () => void;
  onRemoveUrl: (idx: number) => void;
}

export function MetadataForm({
  urls,
  prescanResult,
  confidence,
  onConfirm,
  onAddUrl,
  onRemoveUrl,
}: MetadataFormProps) {
  const isHighConfidence = confidence !== undefined && confidence >= 0.8;
  const maxReached = urls.length >= 5;

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    onConfirm({
      framework: prescanResult?.framework,
      version: prescanResult?.version,
      lang: prescanResult?.lang,
    });
  }

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        {isHighConfidence ? (
          <span className="rounded-full bg-teal-100 px-2 py-0.5 text-xs text-teal-800">
            자동 추론됨 ✓
          </span>
        ) : (
          <span className="rounded-full bg-yellow-100 px-2 py-0.5 text-xs text-yellow-800">
            수동 입력 필요 ⚠
          </span>
        )}
      </div>

      <div className="flex flex-col gap-2">
        {urls.map((url, i) => (
          <div key={i} className="flex gap-2">
            <span className="flex-1 truncate text-sm">{url}</span>
            <button type="button" onClick={() => onRemoveUrl(i)} className="text-xs text-red-500">
              삭제
            </button>
          </div>
        ))}
        <button
          type="button"
          onClick={onAddUrl}
          disabled={maxReached}
          className="rounded border px-2 py-1 text-sm disabled:opacity-40"
        >
          URL 추가
        </button>
      </div>

      <button type="submit" className="rounded bg-blue-600 px-3 py-1.5 text-sm text-white">
        확인
      </button>
    </form>
  );
}
