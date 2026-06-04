/**
 * 대시보드 홈 — 역할 인지형.
 * lead: 팀원 PR 현황 / 승인 대기 (스텁)
 * member: 본인 현황 스텁
 */

import { useQuery } from "@tanstack/react-query";
import { teamsApi } from "../lib/api";
import { useAuth } from "../lib/auth";
import { GitPullRequest } from "lucide-react";

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

  const { data: teams } = useQuery({
    queryKey: ["teams"],
    queryFn: () => teamsApi.list().then((r) => r.data),
  });

  const firstTeam = Array.isArray(teams) && teams.length > 0 ? teams[0] : null;

  const { data: prsData } = useQuery({
    queryKey: ["prs", firstTeam?.id],
    queryFn: () =>
      firstTeam ? teamsApi.getPRs(firstTeam.id).then((r) => r.data) : null,
    enabled: !!firstTeam,
  });

  const isLead = prsData?.scope === "team";

  return (
    <div className="max-w-4xl mx-auto px-6 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-notion-text">
          안녕하세요, {user?.name ?? user?.login}님
        </h1>
        <p className="text-sm text-notion-text-secondary mt-1">
          {isLead ? "팀장 대시보드" : "팀원 대시보드"}
        </p>
      </div>

      {/* 요약 카드 */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 mb-8" data-testid="dashboard-cards">
        {isLead ? (
          <>
            <PRCard title="팀 전체 PR" count={0} label="검토 대기 중 (m4 데이터 없음)" />
            <PRCard title="승인 대기" count={0} label="Critical 이슈 없음" />
            <PRCard title="이번 주 완료" count={0} label="LGTM 처리됨" />
          </>
        ) : (
          <>
            <PRCard title="내 PR" count={0} label="검토 대기 중" />
            <PRCard title="받은 피드백" count={0} label="이번 주" />
            <PRCard title="학습 진도" count={0} label="커리큘럼 미완료" />
          </>
        )}
      </div>

      {/* PR 목록 (스텁) */}
      <div className="bg-white border border-notion-border rounded-lg">
        <div className="flex items-center gap-2 px-4 py-3 border-b border-notion-border">
          <GitPullRequest size={16} className="text-notion-text-secondary" />
          <h2 className="text-sm font-medium text-notion-text">
            {isLead ? "팀 PR 현황" : "내 PR 현황"}
          </h2>
        </div>
        <div className="px-4 py-8 text-center text-sm text-notion-text-secondary">
          PR 데이터는 m4 모듈 구현 후 표시됩니다.
        </div>
      </div>
    </div>
  );
}
