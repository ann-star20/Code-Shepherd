/**
 * PR 코드 리뷰 — m2 정적 분석 · 보안 스캔 결과 뷰.
 * 계약: backend/_shared/shared/contracts.py (M2AnalyzeResponse).
 */

import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { AlertTriangle, FileCode, Play, Shield, ShieldCheck } from "lucide-react";
import {
  analyzeApi,
  type IssueItem,
  type IssueSeverity,
  type M2AnalyzeResponse,
} from "../../lib/api";
import { useTeamContext } from "../../contexts/TeamContext";

const SEVERITY_STYLE: Record<IssueSeverity, string> = {
  Critical: "bg-red-50 text-red-700 border-red-200",
  Major: "bg-amber-50 text-amber-700 border-amber-200",
  Minor: "bg-gray-50 text-gray-600 border-gray-200",
};

function SeverityBadge({ severity }: { severity: IssueSeverity }) {
  return (
    <span
      className={`inline-flex items-center rounded px-1.5 py-0.5 text-[11px] font-medium border ${SEVERITY_STYLE[severity]}`}
      data-testid={`severity-${severity}`}
    >
      {severity}
    </span>
  );
}

function SummaryBadges({ summary }: { summary: M2AnalyzeResponse["summary"] }) {
  const items: { label: string; count: number; severity: IssueSeverity }[] = [
    { label: "Critical", count: summary.critical, severity: "Critical" },
    { label: "Major", count: summary.major, severity: "Major" },
    { label: "Minor", count: summary.minor, severity: "Minor" },
  ];
  return (
    <div className="flex items-center gap-2">
      {items.map((it) => (
        <span
          key={it.label}
          className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs border ${SEVERITY_STYLE[it.severity]}`}
        >
          {it.label}
          <span className="font-semibold">{it.count}</span>
        </span>
      ))}
    </div>
  );
}

function IssueCard({ issue }: { issue: IssueItem }) {
  return (
    <li className="px-4 py-3">
      <div className="flex items-start gap-2">
        <SeverityBadge severity={issue.severity} />
        <div className="min-w-0 flex-1">
          <p className="text-sm text-notion-text">{issue.message}</p>
          <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-notion-text-secondary">
            {issue.file && (
              <span className="inline-flex items-center gap-1">
                <FileCode size={12} />
                {issue.file}
                {issue.line != null ? `:${issue.line}` : ""}
              </span>
            )}
            {issue.rule_id && <span>rule: {issue.rule_id}</span>}
          </div>
          {issue.suggestion && (
            <p className="mt-1.5 rounded bg-notion-bg-secondary border border-notion-border px-2 py-1 text-xs text-notion-text-secondary">
              제안: {issue.suggestion}
            </p>
          )}
        </div>
      </div>
    </li>
  );
}

function ResultSection({
  title,
  icon,
  result,
}: {
  title: string;
  icon: React.ReactNode;
  result: M2AnalyzeResponse | undefined;
}) {
  if (!result) return null;
  return (
    <div
      className="bg-white border border-notion-border rounded-lg"
      data-testid={`result-${result.agent}`}
    >
      <div className="flex items-center justify-between gap-2 px-4 py-3 border-b border-notion-border">
        <div className="flex items-center gap-2">
          {icon}
          <h2 className="text-sm font-medium text-notion-text">{title}</h2>
          <span className="text-xs text-notion-text-secondary">
            {result.execution_ms}ms
          </span>
        </div>
        <SummaryBadges summary={result.summary} />
      </div>
      {result.issues.length === 0 ? (
        <div className="px-4 py-8 text-center text-sm text-notion-text-secondary">
          발견된 이슈가 없습니다.
        </div>
      ) : (
        <ul className="divide-y divide-notion-border" data-testid={`issues-${result.agent}`}>
          {result.issues.map((issue, i) => (
            <IssueCard key={`${issue.file ?? "?"}-${issue.line ?? i}-${i}`} issue={issue} />
          ))}
        </ul>
      )}
    </div>
  );
}

export default function ReviewPage() {
  const { currentTeam } = useTeamContext();
  const [prId, setPrId] = useState("");
  const [diff, setDiff] = useState("");

  const staticMutation = useMutation({
    mutationFn: () =>
      analyzeApi
        .static({ task_id: crypto.randomUUID(), pr_id: prId, pr_diff: diff })
        .then((r) => r.data),
  });
  const securityMutation = useMutation({
    mutationFn: () =>
      analyzeApi
        .security({ task_id: crypto.randomUUID(), pr_id: prId, pr_diff: diff })
        .then((r) => r.data),
  });

  const canRun = prId.trim().length > 0 && diff.trim().length > 0;
  const running = staticMutation.isPending || securityMutation.isPending;
  const failed = staticMutation.isError || securityMutation.isError;

  const runAll = () => {
    if (!canRun) return;
    staticMutation.mutate();
    securityMutation.mutate();
  };

  return (
    <div className="max-w-4xl mx-auto px-6 py-8" data-testid="review-page">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-notion-text">PR 코드 리뷰</h1>
        <p className="text-sm text-notion-text-secondary mt-1">
          {currentTeam?.github_repo ? `${currentTeam.github_repo} · ` : ""}
          정적 분석 · 보안 스캔 (m2)
        </p>
      </div>

      <div className="bg-white border border-notion-border rounded-lg p-4 mb-6 space-y-3">
        <div>
          <label
            htmlFor="review-pr-id"
            className="block text-xs font-medium text-notion-text-secondary mb-1"
          >
            PR ID
          </label>
          <input
            id="review-pr-id"
            type="text"
            value={prId}
            onChange={(e) => setPrId(e.target.value)}
            placeholder="예: pr-42"
            className="w-full text-sm border border-notion-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-notion-text"
            data-testid="review-pr-id"
          />
        </div>
        <div>
          <label
            htmlFor="review-diff"
            className="block text-xs font-medium text-notion-text-secondary mb-1"
          >
            PR Diff
          </label>
          <textarea
            id="review-diff"
            value={diff}
            onChange={(e) => setDiff(e.target.value)}
            placeholder="@@ -1,4 +1,4 @@ ..."
            rows={8}
            className="w-full text-sm font-mono border border-notion-border rounded px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-notion-text"
            data-testid="review-diff"
          />
        </div>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={runAll}
            disabled={!canRun || running}
            className="inline-flex items-center gap-1.5 text-sm px-3 py-1.5 rounded bg-notion-text text-white disabled:opacity-50"
            data-testid="review-run"
          >
            <Play size={14} />
            {running ? "분석 중..." : "분석 실행"}
          </button>
          {failed && (
            <span className="inline-flex items-center gap-1 text-xs text-red-600">
              <AlertTriangle size={12} />
              분석에 실패했습니다. 다시 시도해 주세요.
            </span>
          )}
        </div>
      </div>

      <div className="space-y-4">
        <ResultSection
          title="정적 분석"
          icon={<ShieldCheck size={16} className="text-notion-text-secondary" />}
          result={staticMutation.data}
        />
        <ResultSection
          title="보안 스캔"
          icon={<Shield size={16} className="text-notion-text-secondary" />}
          result={securityMutation.data}
        />
      </div>
    </div>
  );
}
