/**
 * PR 코드 리뷰 페이지.
 * 좌: 팀 PR 목록(api-core /teams/{id}/prs) · 우: 선택 PR 의 리뷰 결과(m3 /review/...).
 * 데이터 없을 때 가짜로 채우지 않고 정직한 빈/처리중 상태를 보여준다.
 */

import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Circle,
  ExternalLink,
  GitPullRequest,
  Loader2,
  ShieldAlert,
} from "lucide-react";
import { reviewApi } from "../../lib/api";
import { useTeamContext } from "../../contexts/TeamContext";

interface TeamPR {
  id: string;
  user_id: string;
  author_login: string;
  github_pr_number: number;
  github_pr_url: string | null;
  status: string;
  submitted_at: string;
  is_lgtm: boolean;
}

type Verdict = "lgtm" | "rework" | "escalate";

interface ReviewIssue {
  severity: "Critical" | "Major" | "Minor";
  file: string | null;
  line: number | null;
  message: string;
  rule_id: string | null;
  suggestion: string | null;
  rag_context?: string | null;
}

interface TraceNode {
  node: string;
  label: string;
  ms: number;
  summary: string;
  ok: boolean;
}

interface ReviewResult {
  found: boolean;
  verdict: Verdict | null;
  comment: string;
  issues: ReviewIssue[];
  trace?: TraceNode[];
}

const VERDICT_STYLE: Record<
  Verdict,
  { label: string; cls: string; icon: React.ReactNode }
> = {
  lgtm: {
    label: "LGTM",
    cls: "bg-green-50 text-green-700 border-green-200",
    icon: <CheckCircle2 size={14} />,
  },
  rework: {
    label: "REWORK",
    cls: "bg-yellow-50 text-yellow-700 border-yellow-200",
    icon: <AlertTriangle size={14} />,
  },
  escalate: {
    label: "ESCALATE",
    cls: "bg-red-50 text-red-700 border-red-200",
    icon: <ShieldAlert size={14} />,
  },
};

const SEVERITY_CLS: Record<ReviewIssue["severity"], string> = {
  Critical: "bg-red-50 text-red-700 border-red-200",
  Major: "bg-yellow-50 text-yellow-700 border-yellow-200",
  Minor: "bg-blue-50 text-blue-700 border-blue-200",
};

function formatDate(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  return d.toLocaleDateString();
}

function VerdictBadge({ verdict }: { verdict: Verdict }) {
  const s = VERDICT_STYLE[verdict];
  return (
    <span
      data-testid="review-verdict"
      className={`inline-flex items-center gap-1 text-xs font-semibold px-2 py-1 rounded border ${s.cls}`}
    >
      {s.icon}
      {s.label}
    </span>
  );
}

// ── RAG 파이프라인 trace 타임라인 ─────────────────────────────────────────────

function TraceTimeline({ trace }: { trace: TraceNode[] }) {
  if (!trace || trace.length === 0) return null;
  return (
    <div className="bg-white border border-notion-border rounded-lg overflow-hidden">
      <div className="px-4 py-2.5 border-b border-notion-border">
        <h3 className="text-sm font-medium text-notion-text">
          RAG 파이프라인 실행 흐름
        </h3>
      </div>
      <ol className="px-4 py-3 space-y-2">
        {trace.map((step, i) => (
          <li key={step.node} className="flex items-start gap-3">
            {/* 인덱스 뱃지 */}
            <span
              className={`mt-0.5 flex-shrink-0 w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold
                ${step.ok
                  ? "bg-green-100 text-green-700"
                  : "bg-red-100 text-red-700"
                }`}
            >
              {i}
            </span>

            {/* 라인 커넥터 */}
            <div className="flex-1 min-w-0">
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <span className="text-xs font-medium text-notion-text">
                  {step.label}
                </span>
                <span className="text-[10px] text-notion-text-secondary whitespace-nowrap">
                  {step.ms > 0 ? `${step.ms}ms` : "—"}
                </span>
              </div>
              <p className="text-[11px] text-notion-text-secondary mt-0.5 truncate">
                {step.summary}
              </p>
            </div>

            {/* 성공/실패 아이콘 */}
            {step.ok ? (
              <CheckCircle2 size={14} className="mt-0.5 flex-shrink-0 text-green-500" />
            ) : (
              <Circle size={14} className="mt-0.5 flex-shrink-0 text-red-400" />
            )}
          </li>
        ))}
      </ol>
    </div>
  );
}

// ── issue 행 (펼침 가능) ──────────────────────────────────────────────────────

function IssueRow({ issue, index }: { issue: ReviewIssue; index: number }) {
  const [expanded, setExpanded] = useState(false);
  const hasDetail = !!(issue.rag_context || issue.suggestion);

  return (
    <>
      <tr
        key={index}
        data-testid={`issue-row-${index}`}
        className={`align-top ${hasDetail ? "cursor-pointer hover:bg-notion-bg-secondary" : ""}`}
        onClick={() => hasDetail && setExpanded((v) => !v)}
      >
        <td className="px-4 py-2.5 whitespace-nowrap">
          <span
            className={`inline-block text-xs font-medium px-2 py-0.5 rounded border ${SEVERITY_CLS[issue.severity]}`}
          >
            {issue.severity}
          </span>
        </td>
        <td className="px-4 py-2.5 whitespace-nowrap font-mono text-xs text-notion-text-secondary">
          {issue.file ?? "(전체)"}
          {issue.line != null ? `:${issue.line}` : ""}
        </td>
        <td className="px-4 py-2.5 whitespace-nowrap text-xs text-notion-text-secondary">
          {issue.rule_id ?? "-"}
        </td>
        <td className="px-4 py-2.5 text-notion-text">
          <div className="flex items-start gap-1">
            {hasDetail && (
              <span className="mt-0.5 flex-shrink-0 text-notion-text-secondary">
                {expanded ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
              </span>
            )}
            <p className="text-sm">{issue.message}</p>
          </div>
        </td>
      </tr>

      {/* 펼침 상세 — rule_quote(rag_context) + 수정 제안 */}
      {expanded && hasDetail && (
        <tr data-testid={`issue-detail-${index}`}>
          <td colSpan={4} className="px-4 pb-3 bg-notion-bg-secondary">
            <div className="space-y-2 pt-1">
              {issue.rag_context && (
                <div>
                  <p className="text-[10px] font-semibold text-notion-text-secondary uppercase tracking-wide mb-1">
                    📖 KMS 규칙 인용
                  </p>
                  <blockquote className="border-l-2 border-yellow-400 pl-3 text-xs text-notion-text leading-relaxed whitespace-pre-wrap">
                    {issue.rag_context}
                  </blockquote>
                </div>
              )}
              {issue.suggestion && (
                <div>
                  <p className="text-[10px] font-semibold text-notion-text-secondary uppercase tracking-wide mb-1">
                    💡 수정 제안
                  </p>
                  <p className="text-xs text-notion-text leading-relaxed">
                    {issue.suggestion}
                  </p>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

// ── 우측 패널: 선택된 PR 상세 ─────────────────────────────────────────────────

function ReviewDetail({
  pr,
  owner,
  repo,
}: {
  pr: TeamPR;
  owner: string;
  repo: string;
}) {
  const {
    data: review,
    isLoading,
    isError,
  } = useQuery<ReviewResult>({
    queryKey: ["review", owner, repo, pr.github_pr_number],
    queryFn: () =>
      reviewApi.getReview(owner, repo, pr.github_pr_number).then((r) => r.data),
    enabled: !!owner && !!repo,
  });

  const header = (
    <div className="flex items-center justify-between gap-3 mb-4">
      <h2 className="text-base font-semibold text-notion-text">
        PR #{pr.github_pr_number}{" "}
        <span className="font-normal text-notion-text-secondary">
          · @{pr.author_login}
        </span>
      </h2>
      {pr.github_pr_url && (
        <a
          href={pr.github_pr_url}
          target="_blank"
          rel="noopener noreferrer"
          data-testid="review-github-link"
          className="inline-flex items-center gap-1 text-xs text-notion-text-secondary hover:text-notion-text"
        >
          <ExternalLink size={13} />
          GitHub에서 보기
        </a>
      )}
    </div>
  );

  if (isError) {
    return (
      <div data-testid="review-detail">
        {header}
        <div
          data-testid="review-error"
          className="flex items-center gap-2 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-4 py-3"
        >
          <AlertTriangle size={15} />
          리뷰 결과를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.
        </div>
      </div>
    );
  }

  if (isLoading) {
    return (
      <div data-testid="review-detail">
        {header}
        <div
          data-testid="review-loading"
          className="flex items-center gap-2 text-sm text-notion-text-secondary px-4 py-8 justify-center"
        >
          <Loader2 size={15} className="animate-spin" />
          리뷰 결과 불러오는 중...
        </div>
      </div>
    );
  }

  if (!review || !review.found) {
    return (
      <div data-testid="review-detail">
        {header}
        <div
          data-testid="review-empty"
          className="text-center text-sm text-notion-text-secondary px-4 py-10 border border-dashed border-notion-border rounded-lg"
        >
          아직 분석 결과가 없습니다.
          <br />
          PR 분석이 끝나면 판정과 코멘트가 여기에 표시됩니다 (처리 중일 수 있어요).
        </div>
      </div>
    );
  }

  return (
    <div data-testid="review-detail" className="space-y-5">
      {/* verdict + GitHub 링크 */}
      <div className="flex items-center justify-between gap-3">
        <h2 className="text-base font-semibold text-notion-text">
          PR #{pr.github_pr_number}{" "}
          <span className="font-normal text-notion-text-secondary">
            · @{pr.author_login}
          </span>
        </h2>
        <div className="flex items-center gap-2">
          {review.verdict && <VerdictBadge verdict={review.verdict} />}
          {pr.github_pr_url && (
            <a
              href={pr.github_pr_url}
              target="_blank"
              rel="noopener noreferrer"
              data-testid="review-github-link"
              className="inline-flex items-center gap-1 text-xs text-notion-text-secondary hover:text-notion-text"
            >
              <ExternalLink size={13} />
              GitHub에서 보기
            </a>
          )}
        </div>
      </div>

      {/* RAG 파이프라인 타임라인 */}
      {review.trace && review.trace.length > 0 && (
        <TraceTimeline trace={review.trace} />
      )}

      {/* 이슈 테이블 (행 클릭 → rule_quote + 제안 펼침) */}
      <div className="bg-white border border-notion-border rounded-lg overflow-hidden">
        <div className="px-4 py-2.5 border-b border-notion-border">
          <h3 className="text-sm font-medium text-notion-text">
            발견된 이슈 {review.issues.length}건
          </h3>
        </div>
        {review.issues.length === 0 ? (
          <p className="px-4 py-6 text-center text-sm text-notion-text-secondary">
            지적된 이슈가 없습니다.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table
              data-testid="review-issues"
              className="w-full text-sm text-left"
            >
              <thead className="text-xs text-notion-text-secondary bg-notion-bg-secondary">
                <tr>
                  <th className="px-4 py-2 font-medium">심각도</th>
                  <th className="px-4 py-2 font-medium">위치</th>
                  <th className="px-4 py-2 font-medium">규칙</th>
                  <th className="px-4 py-2 font-medium">설명 · 제안</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-notion-border">
                {review.issues.map((issue, i) => (
                  <IssueRow key={i} issue={issue} index={i} />
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* LLM 코멘트 본문 */}
      {review.comment && (
        <div className="bg-white border border-notion-border rounded-lg">
          <div className="px-4 py-2.5 border-b border-notion-border">
            <h3 className="text-sm font-medium text-notion-text">자동 리뷰 코멘트</h3>
          </div>
          <div
            data-testid="review-comment"
            className="px-4 py-3 text-sm text-notion-text whitespace-pre-wrap leading-relaxed"
          >
            {review.comment}
          </div>
        </div>
      )}
    </div>
  );
}

// ── 페이지 루트 ───────────────────────────────────────────────────────────────

export default function ReviewPage() {
  const { currentTeamId, currentTeam, teamsLoading } = useTeamContext();
  const [selectedPr, setSelectedPr] = useState<TeamPR | null>(null);

  const {
    data: prsData,
    isLoading: prsLoading,
    isError: prsError,
  } = useQuery<{ scope?: string; prs: TeamPR[] }>({
    queryKey: ["review-prs", currentTeamId],
    queryFn: () =>
      reviewApi.getTeamPRs(currentTeamId as string).then((r) => r.data),
    enabled: !!currentTeamId,
  });

  const prs: TeamPR[] = prsData?.prs ?? [];

  // 팀/목록이 바뀌면 선택 초기화 (사라진 PR 을 가리키지 않도록)
  useEffect(() => {
    setSelectedPr(null);
  }, [currentTeamId]);

  const [owner, repo] = (currentTeam?.github_repo ?? "").split("/");

  if (!teamsLoading && !currentTeamId) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-8" data-testid="review-page">
        <h1 className="text-2xl font-semibold text-notion-text mb-2">PR 코드 리뷰</h1>
        <p className="text-sm text-notion-text-secondary">
          사이드바에서 팀을 먼저 선택해 주세요.
        </p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-8" data-testid="review-page">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-notion-text">PR 코드 리뷰</h1>
        <p className="text-sm text-notion-text-secondary mt-1">
          {currentTeam?.name ? `${currentTeam.name} · ` : ""}
          {currentTeam?.github_repo ?? ""}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* 좌: PR 목록 */}
        <div className="lg:col-span-1 bg-white border border-notion-border rounded-lg overflow-hidden h-fit">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-notion-border">
            <GitPullRequest size={16} className="text-notion-text-secondary" />
            <h2 className="text-sm font-medium text-notion-text">PR 목록</h2>
          </div>

          {prsLoading ? (
            <p className="px-4 py-8 text-center text-sm text-notion-text-secondary">
              불러오는 중...
            </p>
          ) : prsError ? (
            <p
              data-testid="review-pr-error"
              className="px-4 py-8 text-center text-sm text-red-600"
            >
              PR 목록을 불러오지 못했습니다.
            </p>
          ) : prs.length === 0 ? (
            <p
              data-testid="review-pr-empty"
              className="px-4 py-8 text-center text-sm text-notion-text-secondary"
            >
              아직 수집된 PR이 없습니다.
              <br />
              GitHub 웹훅을 팀 repo에 연결하세요.
            </p>
          ) : (
            <ul className="divide-y divide-notion-border" data-testid="review-pr-list">
              {prs.map((pr) => {
                const active = selectedPr?.id === pr.id;
                return (
                  <li key={pr.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedPr(pr)}
                      data-testid={`review-pr-${pr.github_pr_number}`}
                      aria-pressed={active}
                      className={`w-full text-left px-4 py-3 transition-colors ${
                        active ? "bg-sidebar-active" : "hover:bg-sidebar-hover"
                      }`}
                    >
                      <div className="flex items-center justify-between gap-2">
                        <span className="text-sm font-medium text-notion-text">
                          #{pr.github_pr_number}
                        </span>
                        {pr.is_lgtm && (
                          <span className="text-[10px] font-medium px-1.5 py-0.5 rounded border bg-green-50 text-green-700 border-green-200">
                            LGTM
                          </span>
                        )}
                      </div>
                      <div className="text-xs text-notion-text-secondary mt-0.5">
                        @{pr.author_login} · <span className="capitalize">{pr.status}</span>
                        {" · "}
                        {formatDate(pr.submitted_at)}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* 우: 선택 PR 상세 */}
        <div className="lg:col-span-2">
          {selectedPr && owner && repo ? (
            <ReviewDetail pr={selectedPr} owner={owner} repo={repo} />
          ) : (
            <div
              data-testid="review-no-selection"
              className="bg-white border border-dashed border-notion-border rounded-lg px-4 py-16 text-center text-sm text-notion-text-secondary"
            >
              왼쪽에서 PR을 선택하면 판정·이슈·코멘트가 여기에 표시됩니다.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
