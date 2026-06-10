type DuplicateDocumentModalProps = {
  url: string;
  onConfirm: () => void;
};

/** flow-ui-V4 §1: (original_url, etag) 중복 시 노출되는 안내 팝업. */
export function DuplicateDocumentModal({ url, onConfirm }: DuplicateDocumentModalProps) {
  return (
    <div role="dialog" aria-label="중복 문서 안내" className="fixed inset-0 z-50 flex items-center justify-center">
      <div data-testid="duplicate-document-overlay" className="absolute inset-0 bg-black/40" />
      <div className="relative w-[440px] max-w-[90vw] bg-white rounded-2xl shadow-2xl p-6 flex flex-col gap-4">
        <div>
          <h3 className="font-serif text-lg font-bold text-stone-900">중복 문서 안내</h3>
          <p className="text-sm text-stone-600 mt-2 break-all">
            <span className="font-mono text-stone-800">{url}</span>는 이미 지식화된 문서입니다.
          </p>
        </div>
        <div className="flex justify-end">
          <button
            type="button"
            onClick={onConfirm}
            className="px-3.5 py-1.5 text-sm bg-stone-900 text-white font-semibold rounded-lg hover:bg-stone-800 transition-all"
          >
            확인
          </button>
        </div>
      </div>
    </div>
  );
}
