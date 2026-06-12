import { useState } from "react";
import type { MetadataLearnPayload, PrescanResult } from "@/types/graphPipeline";
import { GraphButton } from "./GraphBadge";

const NOT_LISTED = "__not_listed__";

interface GraphMetadataLearnModalProps {
  prescanResult: PrescanResult;
  suggestions: string[];
  onSubmit: (payload: MetadataLearnPayload) => Promise<void>;
  onCancel: () => void;
}

export function GraphMetadataLearnModal({
  prescanResult,
  suggestions,
  onSubmit,
  onCancel,
}: GraphMetadataLearnModalProps) {
  const [selectedFramework, setSelectedFramework] = useState(suggestions[0] ?? "");
  const [customFramework, setCustomFramework]     = useState("");
  const [pattern, setPattern]                     = useState("");
  const [supportedLangs, setSupportedLangs]       = useState("");
  const [defaultLang, setDefaultLang]             = useState("");
  const [isSubmitting, setIsSubmitting]           = useState(false);
  const [errorMessage, setErrorMessage]           = useState("");

  const isCustom  = selectedFramework === NOT_LISTED;
  const canSubmit = Boolean(
    (isCustom ? customFramework.trim() : selectedFramework.trim()) &&
    pattern.trim() &&
    supportedLangs.trim()
  );

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setErrorMessage("");
    try {
      await onSubmit({
        framework:       isCustom ? customFramework : selectedFramework,
        pattern,
        supported_langs: supportedLangs.split(",").map((s) => s.trim()),
        default_lang:    defaultLang.trim() || undefined,
      });
    } catch {
      setErrorMessage("학습 요청에 실패했습니다. 다시 시도해주세요.");
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div role="dialog" className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" />
      <div className="relative w-[480px] max-w-[90vw] bg-white rounded-2xl shadow-2xl p-6 flex flex-col gap-4">
        <div>
          <h3 className="font-serif text-lg font-bold text-stone-900">
            메타데이터 자동 추론 실패 — 수동 보정 필요
          </h3>
          <p className="text-sm text-stone-500 mt-1 truncate">{prescanResult.original_url}</p>
        </div>

        <form onSubmit={handleSubmit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-stone-600">프레임워크</span>
            <select
              value={selectedFramework}
              onChange={(e) => setSelectedFramework(e.target.value)}
              className="rounded border border-stone-300 px-2 py-1.5 text-sm"
            >
              {suggestions.map((fw) => (
                <option key={fw}>{fw}</option>
              ))}
              <option value={NOT_LISTED}>[목록에 없음 — 직접 입력]</option>
            </select>
          </label>

          {isCustom && (
            <label className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-stone-600">신규 프레임워크명</span>
              <input
                value={customFramework}
                onChange={(e) => setCustomFramework(e.target.value)}
                placeholder="예: Astro"
                className="rounded border border-stone-300 px-2 py-1.5 text-sm"
              />
            </label>
          )}

          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-stone-600">URL 패턴 (정규식)</span>
            <input
              value={pattern}
              onChange={(e) => setPattern(e.target.value)}
              placeholder="예: docs\.astro\.build"
              className="rounded border border-stone-300 px-2 py-1.5 text-sm font-mono"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-stone-600">지원 언어 (쉼표 구분)</span>
            <input
              value={supportedLangs}
              onChange={(e) => setSupportedLangs(e.target.value)}
              placeholder="예: TypeScript, JavaScript"
              className="rounded border border-stone-300 px-2 py-1.5 text-sm"
            />
          </label>

          <label className="flex flex-col gap-1">
            <span className="text-xs font-semibold text-stone-600">기본 언어 (선택)</span>
            <input
              value={defaultLang}
              onChange={(e) => setDefaultLang(e.target.value)}
              placeholder="예: TypeScript"
              className="rounded border border-stone-300 px-2 py-1.5 text-sm"
            />
          </label>

          {errorMessage && (
            <p role="alert" className="text-xs text-red-600 bg-red-50 border border-red-200 rounded px-2 py-1.5">
              {errorMessage}
            </p>
          )}

          <div className="flex justify-end gap-2 pt-1">
            <GraphButton variant="outline" onClick={onCancel}>취소</GraphButton>
            <GraphButton
              variant="primary"
              type="submit"
              disabled={!canSubmit || isSubmitting}
            >
              {isSubmitting ? "학습 중..." : "학습 및 계속"}
            </GraphButton>
          </div>
        </form>
      </div>
    </div>
  );
}
