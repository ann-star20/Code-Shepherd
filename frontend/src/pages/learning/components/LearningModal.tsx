/**
 * "학습 시작" 팝업 모달 — open=true일 때만 표시되며, 예/아니오 클릭을 콜백으로 위임한다 (T9, FRONTEND_SPEC Section 1).
 */

interface LearningModalProps {
  open: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function LearningModal({ open, onConfirm, onCancel }: LearningModalProps) {
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" data-testid="learning-modal">
      <div className="w-full max-w-sm bg-white rounded-xl border border-notion-border shadow-sm p-6">
        <p className="text-base font-medium text-notion-text mb-6 text-center">학습을 시작하겠습니까?</p>
        <div className="flex justify-center gap-3">
          <button
            onClick={onConfirm}
            data-testid="learning-modal-confirm"
            className="px-5 py-2 rounded-lg text-sm font-medium text-white bg-notion-text hover:opacity-90 transition-opacity"
          >
            예
          </button>
          <button
            onClick={onCancel}
            data-testid="learning-modal-cancel"
            className="px-5 py-2 rounded-lg text-sm font-medium text-notion-text border border-notion-border hover:bg-notion-bg-secondary transition-colors"
          >
            아니오
          </button>
        </div>
      </div>
    </div>
  );
}
