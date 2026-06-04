/**
 * 대시보드 홈 — 역할·활성 팀 인지형 + PR 목록.
 */

import { useQuery } from "@tanstack/react-query";
import { teamsApi } from "../lib/api";
import { useAuth } from "../lib/auth";
import { useTeamContext } from "../contexts/TeamContext";
import { ExternalLink, GitPullRequest } from "lucide-react";
import { Link } from "react-router-dom";

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

function PRCard({ title, count, label }: { title: string; count: number; label: string }) {
  return (
    <div className="bg-white border border-notion-border rounded-lg p-4">
      <p className="text-sm text-notion-text-secondary">{title}</p>
      <p className="text-2xl font-semibold text-notion-text mt-1">{count}</p>
      <p className="text-xs text-notion-text-secondary mt-1">{label}</p>
    </div>
  );
}

export default function DashboardHome() {
  const { user } = useAuth();
  const { currentTeamId, currentTeam, role, teamsLoading } = useTeamContext();

  const { data: prsData } = useQuery({
    queryKey: ["prs", currentTeamId],
    queryFn: () =>
      currentTeamId
        ? teamsApi.getPRs(currentTeamId).then((r) => r.data)
        : null,
    enabled: !!currentTeamId,
  });

  const isLead = role === "lead" || prsData?.scope === "team";
  const prs: TeamPR[] = prsData?.prs ?? [];
  const openCount = prs.filter((p) => p.status === "open").length;

  if (!teamsLoading && !currentTeamId) {
    return (
      <div className="max-w-4xl mx-auto px-6 py-8">
        <h1 className="text-2xl font-semibold text-notion-text mb-2">
          안녕하세요, {user?.name ?? user?.login}님
        </h1>
        <p className="text-sm text-notion-text-secondary mb-4">
          사이드바에서 팀을 선택하거나 새 팀을 만들어 주세요.
        </p>
        <Link
          to="/team"
          className="text-sm text-blue-600 underline"
          data-testid="dashboard-pick-team"
        >
          팀 멤버 관리로 이동
        </Link>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-notion-text">
          안녕하세요, {user?.name ?? user?.login}님
        </h1>
        <p className="text-sm text-notion-text-secondary mt-1">
          {currentTeam ? `${currentTeam.name} · ` : ""}
          {currentTeam?.github_repo ? `${currentTeam.github_repo} · ` : ""}
          {isLead ? "팀장 대시보드" : "팀원 대시보드"}
        </p>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8" data-testid="dashboard-cards">
        {isLead ? (
          <>
            <PRCard title="팀 전체 PR" count={prs.length} label={`open ${openCount}건`} />
            <PRCard title="승인 대기" count={0} label="HITL 연동 예정" />
            <PRCard title="이번 주 완료" count={prs.filter((p) => p.is_lgtm).length} label="LGTM" />
          </>
        ) : (
          <>
            <PRCard title="내 PR" count={prs.length} label={`open ${openCount}건`} />
            <PRCard title="받은 피드백" count={0} label="m4 연동 예정" />
            <PRCard title="학습 진도" count={0} label="커리큘럼 미완료" />
          </>
        )}
      </div>

      <div className="bg-white border border-notion-border rounded-lg">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-notion-border">
          <GitPullRequest size={16} className="text-notion-text-secondary" />
          <h2 className="text-sm font-medium text-notion-text">
            {isLead ? "팀 PR 현황" : "내 PR 현황"}
          </h2>
        </div>
        {prs.length === 0 ? (
          <div className="px-4 py-8 text-center text-sm text-notion-text-secondary">
            아직 수집된 PR이 없습니다. GitHub 웹훅을 팀 repo에 연결하세요.
          </div>
        ) : (
          <ul className="divide-y divide-notion-border" data-testid="dashboard-pr-list">
            {prs.map((pr) => (
              <li
                key={pr.id}
                className="flex items-center justify-between gap-4 px-4 py-3"
              >
                <div className="min-w-0">
                  <p className="text-sm font-medium text-notion-text">
                    #{pr.github_pr_number}
                    {isLead && (
                      <span className="text-notion-text-secondary font-normal">
                        {" "}
                        · @{pr.author_login}
                      </span>
                    )}
                  </p>
                  <p className="text-xs text-notion-text-secondary capitalize">
                    {pr.status}
                    {pr.is_lgtm ? " · LGTM" : ""}
                  </p>
                </div>
                {pr.github_pr_url && (
                  <a
                    href={pr.github_pr_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex-shrink-0 text-notion-text-secondary hover:text-notion-text"
                    aria-label="GitHub에서 열기"
                  >
                    <ExternalLink size={14} />
                  </a>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
