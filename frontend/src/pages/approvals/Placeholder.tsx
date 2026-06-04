export default function ApprovalsPlaceholder() {
  return (
    <div
      className="flex flex-col items-center justify-center h-full py-24"
      data-testid="placeholder-approvals"
    >
      <p className="text-4xl mb-4">✅</p>
      <h2 className="text-lg font-semibold text-notion-text mb-2">승인 대기</h2>
      <p className="text-sm text-notion-text-secondary">
        준비 중입니다 — m4 평가·HITL 승인 API 연동 후 활성화됩니다.
      </p>
    </div>
  );
}
