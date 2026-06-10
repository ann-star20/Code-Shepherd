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
  // 백엔드(/review)가 이슈마다 함께 주는 사내 규칙 인용. 없으면 비움 — 가짜로 채우지 않는다.
  rag_context?: string | null;
  // 출처 링크. 현재 백엔드는 인용 텍스트(rag_context) 안에 링크를 넣어 주지만,
  // 별도 source_url 이 오면 진짜 링크로 렌더한다. 없으면 텍스트만(가짜 링크 금지).
  source_url?: string | null;
}

interface ReviewResult {
  found: boolean;
  verdict: Verdict | null;
  comment: string;
  issues: ReviewIssue[];
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

  // 저장된 결과 없음(found:false) — 가짜로 채우지 않고 정직하게 안내
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
    <div
      data-testid="review-detail"
      className="lg:h-full lg:flex lg:flex-col lg:min-h-0"
    >
      {/* 고정 헤더 — PR# · 판정 · GitHub 링크. 아래 이슈/코멘트를 내려도 항상 보인다. */}
      <div className="flex items-center justify-between gap-3 pb-4 lg:shrink-0">
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

      {/* 스크롤 영역 — 이슈 카드 + 코멘트만 독립적으로 내려간다(위 헤더는 고정). */}
      <div className="space-y-5 lg:flex-1 lg:min-h-0 lg:overflow-y-auto lg:pr-1">
      {/* 이슈 목록 — 이슈 하나당 카드 한 장. 텍스트가 길어도 세로로 늘어나 레이아웃이 안 깨진다. */}
      <div>
        <h3 className="text-sm font-medium text-notion-text mb-2">
          발견된 이슈 {review.issues.length}건
        </h3>
        {review.issues.length === 0 ? (
          <p className="bg-white border border-notion-border rounded-lg px-4 py-6 text-center text-sm text-notion-text-secondary">
            지적된 이슈가 없습니다.
          </p>
        ) : (
          <div data-testid="review-issues" className="space-y-3">
            {review.issues.map((issue, i) => {
              const rag = issue.rag_context?.trim();
              return (
                <div
                  key={i}
                  data-testid={`issue-row-${i}`}
                  className="bg-white border border-notion-border rounded-lg p-4"
                >
                  {/* 상단: 심각도 · 위치 · 규칙코드(작은 꼬리표) */}
                  <div className="flex flex-wrap items-center gap-2 mb-2">
                    <span
                      className={`inline-block text-xs font-medium px-2 py-0.5 rounded border ${SEVERITY_CLS[issue.severity]}`}
                    >
                      {issue.severity}
                    </span>
                    <span className="font-mono text-xs text-notion-text-secondary break-all">
                      {issue.file ?? "(전체)"}
                      {issue.line != null ? `:${issue.line}` : ""}
                    </span>
                    {issue.rule_id && (
                      <span className="font-mono text-[11px] text-notion-text-secondary bg-notion-bg-secondary border border-notion-border px-1.5 py-0.5 rounded">
                        {issue.rule_id}
                      </span>
                    )}
                  </div>

                  {/* 설명 · 제안 */}
                  <p className="text-sm text-notion-text break-words">{issue.message}</p>
                  {issue.suggestion && (
                    <p className="text-xs text-notion-text-secondary mt-1 break-words">
                      💡 {issue.suggestion}
                    </p>
                  )}

                  {/* 📖 사내 규칙 — 카드 전체 폭 인용. 길어도 줄바꿈되어 안 깨진다. */}
                  {rag ? (
                    <div
                      data-testid={`issue-rag-${i}`}
                      className="mt-3 border-l-2 border-notion-border bg-notion-bg-secondary rounded-r px-3 py-2"
                    >
                      <div className="text-xs font-medium text-notion-text mb-0.5">
                        📖 사내 규칙
                      </div>
                      <div className="text-xs text-notion-text-secondary break-words whitespace-pre-wrap">
                        {issue.source_url ? (
                          <a
                            href={issue.source_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="underline decoration-dotted hover:text-notion-text"
                          >
                            {rag}
                          </a>
                        ) : (
                          rag
                        )}
                      </div>
                    </div>
                  ) : (
                    <div
                      data-testid={`issue-rag-${i}`}
                      className="mt-2 text-xs text-notion-text-secondary"
                    >
                      <span className="font-medium text-notion-text">📖 사내 규칙</span>{" "}
                      —
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* LLM 코멘트 본문 (마크다운 원문을 보존해 표시) */}
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
    </div>
  );
}

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
    <div
      className="max-w-6xl mx-auto w-full px-6 py-8 lg:h-full lg:flex lg:flex-col lg:overflow-hidden"
      data-testid="review-page"
    >
      <div className="mb-6 lg:shrink-0">
        <h1 className="text-2xl font-semibold text-notion-text">PR 코드 리뷰</h1>
        <p className="text-sm text-notion-text-secondary mt-1">
          {currentTeam?.name ? `${currentTeam.name} · ` : ""}
          {currentTeam?.github_repo ?? ""}
        </p>
      </div>

      <div className="flex flex-col lg:flex-row gap-5 lg:flex-1 lg:min-h-0">
        {/* 좌: PR 목록 — 오른쪽 상세와 독립적으로 스크롤(여기서 굴리면 여기만 내려감). */}
        <div className="bg-white border border-notion-border rounded-lg overflow-hidden lg:w-[31%] lg:shrink-0 lg:flex lg:flex-col lg:min-h-0">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-notion-border lg:shrink-0">
            <GitPullRequest size={16} className="text-notion-text-secondary" />
            <h2 className="text-sm font-medium text-notion-text">PR 목록</h2>
          </div>

          <div className="lg:flex-1 lg:min-h-0 lg:overflow-y-auto">
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
        </div>

        {/* 우: 선택 PR 상세 */}
        <div className="lg:flex-1 lg:min-h-0 lg:flex lg:flex-col">
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
