export default function KmsManagePlaceholder() {
  return (
    <div
      className="flex flex-col items-center justify-center h-full py-24"
      data-testid="placeholder-kms-manage"
    >
      <p className="text-4xl mb-4">📄</p>
      <h2 className="text-lg font-semibold text-notion-text mb-2">KMS 문서 관리</h2>
      <p className="text-sm text-notion-text-secondary">
        준비 중입니다 — 문서 등록·제거는 m0 파이프라인 연동 후 활성화됩니다.
      </p>
    </div>
  );
}
