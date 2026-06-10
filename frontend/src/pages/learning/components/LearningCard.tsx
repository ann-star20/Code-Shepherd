/**
 * 학습 카드 — 완료된 카드 본문을 렌더링하고, 로드 시 자동으로 완료 처리한다
 * (T9, FRONTEND_SPEC Section 4 자동 완료 / Section 5 레이아웃 / Section 6-1 card_content 구조).
 */

import { useEffect } from "react";

import type { IssueWithPlan } from "../hooks/useLearningApi";
import { m4Api } from "../lib/m4Api";
import CodeBlock from "./CodeBlock";

interface LearningCardProps {
  issue: IssueWithPlan;
}

export default function LearningCard({ issue }: LearningCardProps) {
  const { plan } = issue;

  useEffect(() => {
    if (plan.status === "completed") {
      void m4Api.post("/api/complete", { plan_id: plan.id });
    }
  }, [plan.id, plan.status]);

  if (plan.status === "pending" || plan.status === "running") {
    return (
      <div role="status" className="flex items-center gap-3 rounded-xl border border-notion-border bg-white p-6 text-notion-text-secondary">
        <span className="h-5 w-5 shrink-0 rounded-full border-2 border-notion-border border-t-notion-text animate-spin" />
        <div>
          <p className="font-medium text-notion-text">학습 카드 생성 중</p>
          <p className="text-sm">잠시만 기다려주세요...</p>
        </div>
      </div>
    );
  }

  if (plan.status === "failed") {
    // T6 — plan.error_message는 디버깅용 원본 예외 메시지이므로 화면에는 노출하지 않고 콘솔에만 기록한다
    if (plan.error_message) {
      console.error("[learn] plan failed:", plan.error_message);
    }
    return (
      <div className="flex flex-col items-center justify-center gap-1 p-8 text-center text-notion-text-secondary">
        <p>카드를 생성하는 중 문제가 발생했어요</p>
        <p>잠시 후 다시 시도해주세요</p>
      </div>
    );
  }

  const cardContent = plan.card_content;
  if (!cardContent) return null;

  const { header, before_code, after_code, explanation, why_dangerous, core_summary, learning_recommendations } =
    cardContent;

  // framework/framework_version은 입력 데이터에 없을 수 있으므로(예: 프레임워크 없는 스크립트), 있는 값만 이어 붙인다
  const frameworkLabel = [header.framework, header.framework_version].filter(Boolean).join(" ");
  const metaLabel = [header.language, frameworkLabel].filter(Boolean).join(" / ");

  return (
    <article className="bg-white rounded-xl border border-notion-border shadow-sm overflow-hidden">
      <header className="p-4 border-b border-notion-border">
        <p className="font-medium text-notion-text">
          [{header.keyword}] — [{header.name_of_function}]
        </p>
        {metaLabel && <p className="text-sm text-notion-text-secondary">{metaLabel}</p>}
        {plan.llm_fallback && (
          <p className="mt-2 text-xs text-amber-600">사내 문서 기반 아님 (LLM 자체 생성)</p>
        )}
      </header>

      <div className={before_code ? "grid grid-cols-2 gap-px bg-notion-border" : ""}>
        {before_code && (
          <div className="bg-white p-4">
            <p className="text-sm font-medium text-notion-text mb-2">Before (문제 코드)</p>
            <CodeBlock code={before_code} />
          </div>
        )}
        <div className="bg-white p-4">
          <p className="text-sm font-medium text-notion-text mb-2">After (수정 코드)</p>
          <CodeBlock code={after_code} />
        </div>
      </div>

      <div className="p-4 border-t border-notion-border space-y-3">
        <p className="text-notion-text">{explanation}</p>
        <p className="text-sm text-notion-text-secondary">왜 위험한가: {why_dangerous}</p>

        {(learning_recommendations ?? []).length > 0 && (
          <div>
            <p className="text-sm font-medium text-notion-text mb-1">학습 추천</p>
            <ul className="text-sm text-notion-text-secondary list-disc list-inside">
              {(learning_recommendations ?? []).map((rec) => (
                <li key={rec.title}>
                  {rec.title} — {rec.description}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="rounded-lg bg-notion-bg-secondary p-3">
          <p className="text-sm font-medium text-notion-text">{core_summary}</p>
        </div>
      </div>
    </article>
  );
}
