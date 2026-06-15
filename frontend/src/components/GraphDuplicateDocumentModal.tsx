import { GraphButton } from "./GraphBadge";

interface GraphDuplicateDocumentModalProps {
  url: string;
  onClose: () => void;
}

export function GraphDuplicateDocumentModal({ url, onClose }: GraphDuplicateDocumentModalProps) {
  return (
    <div role="dialog" aria-label="중복 문서 안내"
         className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" onClick={onClose} />
      <div className="relative w-[440px] max-w-[90vw] bg-white rounded-2xl shadow-2xl p-6 flex flex-col gap-4">
        <div className="flex items-start gap-3">
          <span className="flex h-9 w-9 shrink-0 items-center justify-center
                           rounded-full bg-amber-100 text-amber-600 text-lg">
            ⚠
          </span>
          <div>
            <h3 className="font-serif text-lg font-bold text-stone-900">중복 문서 안내</h3>
            <p className="text-sm text-stone-600 mt-1 break-all">
              <span className="font-mono text-stone-800">{url}</span>는
              이미 지식화된 문서입니다.
            </p>
          </div>
        </div>
        <div className="flex justify-end">
          <GraphButton variant="primary" onClick={onClose}>확인</GraphButton>
        </div>
      </div>
    </div>
  );
}
