import { useState } from "react";
import type { LearnMetadataPayload, PrescanResult } from "@/services/pipelineOrchestrator";

const NOT_LISTED = "__NOT_LISTED__";

type MetadataLearnModalProps = {
  prescanResult: PrescanResult;
  onSubmit: (payload: LearnMetadataPayload) => void;
  onCancel: () => void;
  isSubmitting?: boolean;
};

export function MetadataLearnModal({
  prescanResult,
  onSubmit,
  onCancel,
  isSubmitting = false,
}: MetadataLearnModalProps) {
  const suggestions = prescanResult.suggested_frameworks ?? [];
  const [selectedFramework, setSelectedFramework] = useState(suggestions[0] ?? NOT_LISTED);
  const [customFramework, setCustomFramework] = useState("");
  const [pattern, setPattern] = useState("");
  const [supportedLangs, setSupportedLangs] = useState("");
  const [defaultLang, setDefaultLang] = useState("");

  const isCustomFramework = selectedFramework === NOT_LISTED;
  const canSubmit =
    (isCustomFramework ? customFramework.trim() !== "" : selectedFramework.trim() !== "") &&
    pattern.trim() !== "" &&
    supportedLangs.trim() !== "";

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!canSubmit) return;

    const langs = supportedLangs
      .split(",")
      .map((l) => l.trim())
      .filter(Boolean);

    onSubmit({
      framework: isCustomFramework ? customFramework.trim() : selectedFramework,
      pattern: pattern.trim(),
      supported_langs: langs,
      default_lang: defaultLang.trim() || undefined,
    });
  }

  return (
    <div role="dialog" aria-label="메타데이터 보정" className="fixed inset-0 z-50 flex items-center justify-center">
      <div data-testid="metadata-learn-overlay" className="absolute inset-0 bg-black/40" />
      <div className="relative w-[480px] max-w-[90vw] bg-white rounded-2xl shadow-2xl p-6 flex flex-col gap-4">
        <div>
          <h3 className="font-serif text-lg font-bold text-stone-900">메타데이터 자동 추론 실패 — 수동 보정 필요</h3>
          <p className="text-sm text-stone-500 mt-1 truncate">{prescanResult.original_url}</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-4">
          <div className="flex flex-col gap-1">
            <label htmlFor="metadata-learn-framework" className="text-xs font-semibold text-stone-600">
              프레임워크
            </label>
            <select
              id="metadata-learn-framework"
              value={selectedFramework}
              onChange={(e) => setSelectedFramework(e.target.value)}
              className="rounded border border-stone-300 px-2 py-1.5 text-sm"
            >
              {suggestions.map((fw) => (
                <option key={fw} value={fw}>
                  {fw}
                </option>
              ))}
              <option value={NOT_LISTED}>[목록에 없음 (직접 입력 활성화)]</option>
            </select>
          </div>

          {isCustomFramework && (
            <div className="flex flex-col gap-1">
              <label htmlFor="metadata-learn-custom-framework" className="text-xs font-semibold text-stone-600">
                신규 프레임워크명
              </label>
              <input
                id="metadata-learn-custom-framework"
                value={customFramework}
                onChange={(e) => setCustomFramework(e.target.value)}
                placeholder="예: Astro"
                className="rounded border border-stone-300 px-2 py-1.5 text-sm"
              />
            </div>
          )}

          <div className="flex flex-col gap-1">
            <label htmlFor="metadata-learn-pattern" className="text-xs font-semibold text-stone-600">
              URL 패턴 (정규식)
            </label>
            <input
              id="metadata-learn-pattern"
              value={pattern}
              onChange={(e) => setPattern(e.target.value)}
              placeholder="예: docs\.astro\.build"
              className="rounded border border-stone-300 px-2 py-1.5 text-sm font-mono"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="metadata-learn-langs" className="text-xs font-semibold text-stone-600">
              지원 언어 (쉼표 구분)
            </label>
            <input
              id="metadata-learn-langs"
              value={supportedLangs}
              onChange={(e) => setSupportedLangs(e.target.value)}
              placeholder="예: TypeScript, JavaScript"
              className="rounded border border-stone-300 px-2 py-1.5 text-sm"
            />
          </div>

          <div className="flex flex-col gap-1">
            <label htmlFor="metadata-learn-default-lang" className="text-xs font-semibold text-stone-600">
              기본 언어 (선택)
            </label>
            <input
              id="metadata-learn-default-lang"
              value={defaultLang}
              onChange={(e) => setDefaultLang(e.target.value)}
              placeholder="예: TypeScript"
              className="rounded border border-stone-300 px-2 py-1.5 text-sm"
            />
          </div>

          <div className="flex justify-end gap-2 mt-2">
            <button
              type="button"
              onClick={onCancel}
              className="px-3.5 py-1.5 text-sm border border-stone-300 text-stone-700 font-semibold rounded-lg hover:bg-stone-100 transition-all"
            >
              취소
            </button>
            <button
              type="submit"
              disabled={!canSubmit || isSubmitting}
              className="px-3.5 py-1.5 text-sm bg-blue-600 text-white font-semibold rounded-lg hover:bg-blue-700 disabled:opacity-40 transition-all"
            >
              {isSubmitting ? "학습 중..." : "학습 및 계속"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
