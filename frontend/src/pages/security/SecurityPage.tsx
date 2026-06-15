/**
 * M2 정적 분석 · 보안 스캔 페이지.
 * PR 목록에서 선택하면 M2 파이프라인 시각화 + 이슈 결과를 보여준다.
 */

import { useEffect, useState, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { GitPullRequest, Loader2 } from "lucide-react";
import { reviewApi } from "../../lib/api";
import { useTeamContext } from "../../contexts/TeamContext";
import { M2PipelineFlow, M2StageTrace } from "../../components/M2PipelineFlow";

const PIPELINE_STAGES: M2StageTrace["key"][] = ["run_tools", "vector_search", "llm_judge", "store"];

// ── 더미 데이터 (mixed_case 데이터셋 기반) ─────────────────────────────────
const DUMMY_PRS: TeamPR[] = [
  { id: "pr-1", author_login: "dev_alice", github_pr_number: 101, github_pr_url: null, status: "reviewed", submitted_at: "2024-06-01T10:00:00Z" },
  { id: "pr-2", author_login: "dev_bob",   github_pr_number: 102, github_pr_url: null, status: "reviewed", submitted_at: "2024-06-03T14:30:00Z" },
  { id: "pr-3", author_login: "dev_carol", github_pr_number: 103, github_pr_url: null, status: "reviewed", submitted_at: "2024-06-05T09:15:00Z" },
];

const DUMMY_REVIEWS: Record<string, ReviewResult> = {
  "pr-1": {
    found: true, verdict: "rework",
    comment: "보안 취약점 2건(Critical) 및 정적 분석 이슈 3건이 발견되었습니다. 수정 후 재요청 바랍니다.",
    issues: [
      { severity: "Critical", file: "vulnerable.py", line: 4,  message: "DATABASE_URL과 API_KEY가 소스코드에 하드코딩되어 있습니다. 자격증명이 노출될 위험이 있습니다.", rule_id: "SEC-006", suggestion: "환경변수 또는 시크릿 매니저를 사용하세요." },
      { severity: "Critical", file: "vulnerable.py", line: 18, message: "f-string으로 SQL을 동적 조합하여 SQL 인젝션에 취약합니다.", rule_id: "SEC-001", suggestion: "파라미터 바인딩(플레이스홀더)을 사용하세요." },
      { severity: "Major",    file: "vulnerable.py", line: 17, message: "MD5는 암호학적으로 취약한 알고리즘입니다. 비밀번호 해시에 사용하면 안 됩니다.", rule_id: "SEC-005", suggestion: "bcrypt, argon2, scrypt 중 하나를 사용하세요." },
      { severity: "Major",    file: "vulnerable.py", line: 8,  message: "함수 'query'의 반환값 타입 힌트가 없습니다.", rule_id: "SA-C0116", suggestion: "pylint: missing-function-docstring" },
      { severity: "Minor",    file: "vulnerable.py", line: 1,  message: "모듈 수준 상수는 UPPER_CASE 명명 규칙을 따라야 합니다.", rule_id: "SA-C0103", suggestion: "pylint: invalid-name" },
    ],
  },
  "pr-2": {
    found: true, verdict: "escalate",
    comment: "Critical 보안 이슈가 다수 발견되어 시니어 검토가 필요합니다.",
    issues: [
      { severity: "Critical", file: "api/upload.py", line: 20, message: "사용자 입력이 셸 명령어에 직접 전달되어 명령어 인젝션에 취약합니다.", rule_id: "SEC-004", suggestion: "subprocess.run()에 shell=False를 사용하고 입력을 검증하세요." },
      { severity: "Major",    file: "api/upload.py", line: 17, message: "경로 탐색 공격에 취약한 파일 경로 처리가 감지되었습니다.", rule_id: "SEC-003", suggestion: "os.path.abspath()와 화이트리스트 검증을 사용하세요." },
      { severity: "Major",    file: "api/auth.py",   line: 25, message: "인증 없이 관리자 엔드포인트에 접근 가능합니다.", rule_id: "AUTH-001", suggestion: "모든 관리자 라우트에 인증 미들웨어를 적용하세요." },
      { severity: "Minor",    file: "api/auth.py",   line: 10, message: "미사용 import: os", rule_id: "SA-W0611", suggestion: "pylint: unused-import" },
    ],
  },
  "pr-3": {
    found: true, verdict: "lgtm",
    comment: "분석 결과 심각한 이슈가 없습니다. 승인 가능합니다.",
    issues: [
      { severity: "Minor", file: "utils/helper.py", line: 12, message: "변수명 'x'가 너무 짧습니다. 의미있는 이름을 사용하세요.", rule_id: "SA-C0103", suggestion: "pylint: invalid-name" },
      { severity: "Minor", file: "utils/helper.py", line: 20, message: "함수에 docstring이 없습니다.", rule_id: "SA-C0116", suggestion: "pylint: missing-function-docstring" },
    ],
  },
};

interface TeamPR {
  id: string;
  author_login: string;
  github_pr_number: number;
  github_pr_url: string | null;
  status: string;
  submitted_at: string;
}

interface ReviewIssue {
  severity: "Critical" | "Major" | "Minor";
  file: string | null;
  line: number | null;
  message: string;
  rule_id: string | null;
  suggestion: string | null;
}

interface ToolStatus {
  name: string;
  kind: "static" | "security";
  status: "ran" | "skipped";
  reason: string | null;
  issue_count: number;
}

interface ReviewResult {
  found: boolean;
  verdict: string | null;
  comment: string;
  issues: ReviewIssue[];
  tools?: ToolStatus[];
}

const SEVERITY_CLS: Record<ReviewIssue["severity"], string> = {
  Critical: "bg-red-50 text-red-700 border-red-200",
  Major:    "bg-yellow-50 text-yellow-700 border-yellow-200",
  Minor:    "bg-blue-50 text-blue-700 border-blue-200",
};

function formatDate(iso: string) {
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString();
}

const USE_DUMMY = false; // 더미 모드: true=더미데이터, false=실API
const M2_URL = "/m2-api"; // m2 직접 호출 (프록시)

// mixed_case 케이스 목록 (pr_id 101~106)
const MIXED_CASES: TeamPR[] = [
  { id: "mixed_case_01", author_login: "wooya27", github_pr_number: 101, github_pr_url: null, status: "reviewed", submitted_at: "2026-06-14T00:00:00Z" },
  { id: "mixed_case_02", author_login: "wooya27", github_pr_number: 102, github_pr_url: null, status: "reviewed", submitted_at: "2026-06-14T00:01:00Z" },
  { id: "mixed_case_03", author_login: "wooya27", github_pr_number: 103, github_pr_url: null, status: "reviewed", submitted_at: "2026-06-14T00:02:00Z" },
  { id: "mixed_case_04", author_login: "wooya27", github_pr_number: 104, github_pr_url: null, status: "reviewed", submitted_at: "2026-06-14T00:03:00Z" },
  { id: "mixed_case_05", author_login: "wooya27", github_pr_number: 105, github_pr_url: null, status: "reviewed", submitted_at: "2026-06-14T00:04:00Z" },
  { id: "mixed_case_06", author_login: "wooya27", github_pr_number: 106, github_pr_url: null, status: "reviewed", submitted_at: "2026-06-14T00:05:00Z" },
  { id: "clickjacking_case", author_login: "wooya27", github_pr_number: 107, github_pr_url: null, status: "reviewed", submitted_at: "2026-06-14T00:06:00Z" },
];

export default function SecurityPage() {
  const { currentTeamId, currentTeam, teamsLoading } = useTeamContext();
  const [selectedPr, setSelectedPr] = useState<TeamPR | null>(null);
  const [taskId, setTaskId] = useState<string | null>(null);

  const { data: prsData, isLoading: prsLoading, isError: prsError } =
    useQuery<{ prs: TeamPR[] }>({
      queryKey: ["security-prs", currentTeamId],
      queryFn: USE_DUMMY
        ? () => Promise.resolve({ prs: DUMMY_PRS })
        : () => Promise.resolve({ prs: MIXED_CASES }),
      enabled: true,
    });

  const prs = prsData?.prs ?? [];

  useEffect(() => { setSelectedPr(null); }, [currentTeamId]);

  const [activeTab, setActiveTab] = useState<"static" | "security">("static");
  const [pipelineStages, setPipelineStages] = useState<M2StageTrace[]>([]);
  const [pipelineRunning, setPipelineRunning] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // 분석 완료(파이프라인 종료) 후 task_id로 실제 저장된 이슈를 조회한다.
  const { data: review, isLoading: reviewLoading } =
    useQuery<ReviewResult>({
      queryKey: ["security-review", USE_DUMMY ? selectedPr?.id : taskId],
      queryFn: USE_DUMMY
        ? () => Promise.resolve(DUMMY_REVIEWS[selectedPr!.id] ?? { found: false, verdict: null, comment: "", issues: [] })
        : () => fetch(`${M2_URL}/scan-results/task/${taskId}`).then(r => r.json()),
      enabled: USE_DUMMY ? !!selectedPr : (!!taskId && !pipelineRunning),
    });

  // PR 선택 시 실제 분석을 트리거하고 진행상태를 폴링해 단계를 실시간 반영한다.
  useEffect(() => {
    if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    if (!selectedPr) { setPipelineStages([]); setPipelineRunning(false); setTaskId(null); return; }

    // 더미 모드: 트리거 없이 전 단계를 즉시 success 처리.
    if (USE_DUMMY) {
      setPipelineRunning(false);
      setPipelineStages(PIPELINE_STAGES.map(key => ({ key, status: "success" as const })));
      return;
    }

    let cancelled = false;
    setTaskId(null);
    setPipelineRunning(true);
    setPipelineStages(PIPELINE_STAGES.map(key => ({ key, status: "pending" as const })));

    fetch(`${M2_URL}/orchestrate/run-case/${selectedPr.id}`, { method: "POST" })
      .then(r => r.json())
      .then(({ task_id }) => {
        if (cancelled || !task_id) { setPipelineRunning(false); return; }
        setTaskId(task_id);
        pollRef.current = setInterval(() => {
          fetch(`${M2_URL}/orchestrate/status/${task_id}`)
            .then(r => r.json())
            .then(st => {
              if (cancelled || !st?.stages) return;
              setPipelineStages(
                PIPELINE_STAGES.map(key => {
                  const s = st.stages.find((x: M2StageTrace) => x.key === key);
                  return s ? { key, status: s.status, ms: s.ms } : { key, status: "pending" as const };
                })
              );
              if (st.status === "done" || st.status === "error") {
                if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
                setPipelineRunning(false);
              }
            })
            .catch(() => {});
        }, 1000);
      })
      .catch(() => { if (!cancelled) setPipelineRunning(false); });

    return () => {
      cancelled = true;
      if (pollRef.current) { clearInterval(pollRef.current); pollRef.current = null; }
    };
  }, [selectedPr]);

  const isStatic = (i: ReviewIssue) => i.rule_id?.startsWith("SA-") || i.rule_id?.startsWith("JS-");
  const isSecurity = (i: ReviewIssue) => i.rule_id?.startsWith("SEC-") || i.rule_id?.startsWith("OWASP-");

  const m2Issues = review?.issues.filter(i => isStatic(i) || isSecurity(i)) ?? [];
  const staticList   = m2Issues.filter(isStatic);
  const securityList = m2Issues.filter(isSecurity);
  const staticIssues   = staticList.length;
  const securityIssues = securityList.length;

  const tabIssues = activeTab === "static" ? staticList : securityList;

  const kpi = {
    Critical: m2Issues.filter(i => i.severity === "Critical").length,
    Major:    m2Issues.filter(i => i.severity === "Major").length,
    Minor:    m2Issues.filter(i => i.severity === "Minor").length,
  };

  if (!USE_DUMMY && !teamsLoading && !currentTeamId) {
    return (
      <div className="max-w-6xl mx-auto px-6 py-8">
        <h1 className="text-2xl font-semibold text-notion-text mb-2">정적 분석 · 보안 스캔</h1>
        <p className="text-sm text-notion-text-secondary">사이드바에서 팀을 먼저 선택해 주세요.</p>
      </div>
    );
  }

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      <div className="mb-6">
        <h1 className="text-2xl font-semibold text-notion-text">정적 분석 · 보안 스캔</h1>
        <p className="text-sm text-notion-text-secondary mt-1">
          {currentTeam?.name ? `${currentTeam.name} · ` : ""}
          {currentTeam?.github_repo ?? ""}
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
        {/* 좌: PR 목록 + 정보/범례 */}
        <div className="lg:col-span-1 space-y-5 h-fit">
        <div className="bg-white border border-notion-border rounded-lg overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-3 border-b border-notion-border">
            <GitPullRequest size={16} className="text-notion-text-secondary" />
            <h2 className="text-sm font-medium text-notion-text">PR 목록</h2>
          </div>

          {prsLoading ? (
            <p className="px-4 py-8 text-center text-sm text-notion-text-secondary">불러오는 중...</p>
          ) : prsError ? (
            <p className="px-4 py-8 text-center text-sm text-red-600">PR 목록을 불러오지 못했습니다.</p>
          ) : prs.length === 0 ? (
            <p className="px-4 py-8 text-center text-sm text-notion-text-secondary">
              아직 수집된 PR이 없습니다.<br />GitHub 웹훅을 팀 repo에 연결하세요.
            </p>
          ) : (
            <ul className="divide-y divide-notion-border">
              {prs.map(pr => {
                const active = selectedPr?.id === pr.id;
                return (
                  <li key={pr.id}>
                    <button
                      type="button"
                      onClick={() => setSelectedPr(pr)}
                      aria-pressed={active}
                      className={`w-full text-left px-4 py-3 transition-colors ${active ? "bg-sidebar-active" : "hover:bg-sidebar-hover"}`}
                    >
                      <div className="text-sm font-medium text-notion-text">#{pr.github_pr_number}</div>
                      <div className="text-xs text-notion-text-secondary mt-0.5">
                        @{pr.author_login} · {formatDate(pr.submitted_at)}
                      </div>
                    </button>
                  </li>
                );
              })}
            </ul>
          )}
        </div>

        {/* 선택한 PR 정보 */}
        {selectedPr && (
          <div className="bg-white border border-notion-border rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-notion-border">
              <h2 className="text-sm font-medium text-notion-text">선택한 PR</h2>
            </div>
            <dl className="px-4 py-3 space-y-2 text-sm">
              <div className="flex justify-between gap-2">
                <dt className="text-notion-text-secondary">번호</dt>
                <dd className="text-notion-text font-medium">#{selectedPr.github_pr_number}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-notion-text-secondary">작성자</dt>
                <dd className="text-notion-text">@{selectedPr.author_login}</dd>
              </div>
              <div className="flex justify-between gap-2">
                <dt className="text-notion-text-secondary">제출일</dt>
                <dd className="text-notion-text">{formatDate(selectedPr.submitted_at)}</dd>
              </div>
              {review?.verdict && (
                <div className="flex justify-between gap-2">
                  <dt className="text-notion-text-secondary">판정</dt>
                  <dd className="text-notion-text font-mono text-xs">{review.verdict}</dd>
                </div>
              )}
            </dl>
            {selectedPr.github_pr_url && (
              <a
                href={selectedPr.github_pr_url}
                target="_blank"
                rel="noreferrer"
                className="block px-4 py-2.5 text-xs text-blue-600 hover:bg-sidebar-hover border-t border-notion-border"
              >
                GitHub에서 PR 열기 →
              </a>
            )}
          </div>
        )}

        {/* 범례 */}
        <div className="bg-white border border-notion-border rounded-lg overflow-hidden">
          <div className="px-4 py-3 border-b border-notion-border">
            <h2 className="text-sm font-medium text-notion-text">범례</h2>
          </div>
          <div className="px-4 py-3 space-y-3 text-xs">
            <div>
              <p className="text-notion-text-secondary mb-1.5">심각도</p>
              <div className="flex flex-wrap gap-1.5">
                {(["Critical", "Major", "Minor"] as const).map(sev => (
                  <span key={sev} className={`px-2 py-0.5 rounded border ${SEVERITY_CLS[sev]}`}>{sev}</span>
                ))}
              </div>
            </div>
            <div>
              <p className="text-notion-text-secondary mb-1.5">규칙 접두사</p>
              <ul className="space-y-1 text-notion-text">
                <li><span className="font-mono text-notion-text-secondary">SA-</span> Pylint · Radon (정적)</li>
                <li><span className="font-mono text-notion-text-secondary">JS-</span> ESLint (정적)</li>
                <li><span className="font-mono text-notion-text-secondary">SEC-</span> Bandit (보안)</li>
                <li><span className="font-mono text-notion-text-secondary">OWASP-</span> Semgrep (보안)</li>
              </ul>
            </div>
          </div>
        </div>

        {/* 스캔 도구 상태 — 이 PR에서 실제로 실행/스킵된 도구 */}
        {selectedPr && (review?.tools?.length ?? 0) > 0 && (
          <div className="bg-white border border-notion-border rounded-lg overflow-hidden">
            <div className="px-4 py-3 border-b border-notion-border">
              <h2 className="text-sm font-medium text-notion-text">스캔 도구</h2>
            </div>
            <ul className="divide-y divide-notion-border">
              {review!.tools!.map(tool => (
                <li key={tool.name} className="px-4 py-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <span className="flex items-center gap-2 min-w-0">
                      <span className={`shrink-0 w-1.5 h-1.5 rounded-full ${tool.status === "ran" ? "bg-green-500" : "bg-notion-border"}`} />
                      <span className="text-sm text-notion-text">{tool.name}</span>
                      <span className="text-[10px] uppercase tracking-wide text-notion-text-secondary">
                        {tool.kind === "static" ? "정적" : "보안"}
                      </span>
                    </span>
                    {tool.status === "ran" ? (
                      <span className="shrink-0 text-xs text-green-700">실행 · {tool.issue_count}건</span>
                    ) : (
                      <span className="shrink-0 text-xs text-notion-text-secondary">스킵</span>
                    )}
                  </div>
                  {tool.status === "skipped" && tool.reason && (
                    <p className="text-xs text-notion-text-secondary mt-1 pl-3.5">{tool.reason}</p>
                  )}
                </li>
              ))}
            </ul>
          </div>
        )}
        </div>

        {/* 우: M2 파이프라인 + 이슈 */}
        <div className="lg:col-span-2 space-y-5">
          {selectedPr ? (
            <>
              <M2PipelineFlow
                found={!!review?.found}
                isLoading={pipelineRunning}
                stages={pipelineStages}
                result={!pipelineRunning && review?.found ? { staticIssues, securityIssues } : undefined}
              />

              {/* 이슈 테이블 */}
              {reviewLoading ? (
                <div className="flex items-center justify-center gap-2 text-sm text-notion-text-secondary py-10">
                  <Loader2 size={15} className="animate-spin" />
                  분석 결과 불러오는 중...
                </div>
              ) : !review?.found ? (
                <div className="text-center text-sm text-notion-text-secondary px-4 py-10 border border-dashed border-notion-border rounded-lg">
                  아직 분석 결과가 없습니다.<br />
                  PR 분석이 완료되면 이슈 목록이 여기에 표시됩니다.
                </div>
              ) : (
                <>
                  {/* 이슈 요약 KPI */}
                  <div className="grid grid-cols-3 gap-3">
                    {(["Critical", "Major", "Minor"] as const).map(sev => (
                      <div key={sev} className={`rounded-lg border px-4 py-3 ${SEVERITY_CLS[sev]}`}>
                        <div className="text-xs font-medium">{sev}</div>
                        <div className="text-2xl font-semibold mt-0.5 tabular-nums">{kpi[sev]}</div>
                      </div>
                    ))}
                  </div>

                  {/* 정적분석 / 보안스캔 탭 */}
                  <div className="bg-white border border-notion-border rounded-lg overflow-hidden">
                    <div className="flex border-b border-notion-border">
                      <button
                        type="button"
                        onClick={() => setActiveTab("static")}
                        aria-pressed={activeTab === "static"}
                        className={`flex-1 px-4 py-2.5 text-sm font-medium transition-colors ${
                          activeTab === "static"
                            ? "text-notion-text border-b-2 border-blue-500 -mb-px"
                            : "text-notion-text-secondary hover:bg-sidebar-hover"
                        }`}
                      >
                        정적 분석 <span className="text-xs text-notion-text-secondary">(Pylint · Radon · ESLint)</span> · {staticIssues}
                      </button>
                      <button
                        type="button"
                        onClick={() => setActiveTab("security")}
                        aria-pressed={activeTab === "security"}
                        className={`flex-1 px-4 py-2.5 text-sm font-medium transition-colors ${
                          activeTab === "security"
                            ? "text-notion-text border-b-2 border-red-500 -mb-px"
                            : "text-notion-text-secondary hover:bg-sidebar-hover"
                        }`}
                      >
                        보안 스캔 <span className="text-xs text-notion-text-secondary">(Bandit · Semgrep)</span> · {securityIssues}
                      </button>
                    </div>

                    {tabIssues.length === 0 ? (
                      <p className="px-4 py-6 text-center text-sm text-notion-text-secondary">
                        {activeTab === "static" ? "정적 분석" : "보안 스캔"} 이슈가 없습니다.
                      </p>
                    ) : (
                      <div className="overflow-x-auto">
                        <table className="w-full text-sm text-left">
                          <thead className="text-xs text-notion-text-secondary bg-notion-bg-secondary">
                            <tr>
                              <th className="px-4 py-2 font-medium">심각도</th>
                              <th className="px-4 py-2 font-medium">위치</th>
                              <th className="px-4 py-2 font-medium">규칙</th>
                              <th className="px-4 py-2 font-medium">설명 · 제안</th>
                            </tr>
                          </thead>
                          <tbody className="divide-y divide-notion-border">
                            {tabIssues.map((issue, i) => (
                              <tr key={i} className="align-top">
                                <td className="px-4 py-2.5 whitespace-nowrap">
                                  <span className={`inline-block text-xs font-medium px-2 py-0.5 rounded border ${SEVERITY_CLS[issue.severity]}`}>
                                    {issue.severity}
                                  </span>
                                </td>
                                <td className="px-4 py-2.5 whitespace-nowrap font-mono text-xs text-notion-text-secondary">
                                  {issue.file ?? "(전체)"}{issue.line != null ? `:${issue.line}` : ""}
                                </td>
                                <td className="px-4 py-2.5 whitespace-nowrap text-xs text-notion-text-secondary">
                                  {issue.rule_id ?? "-"}
                                </td>
                                <td className="px-4 py-2.5 text-notion-text">
                                  <p>{issue.message}</p>
                                  {issue.suggestion && (
                                    <p className="text-xs text-notion-text-secondary mt-1">💡 {issue.suggestion}</p>
                                  )}
                                </td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </>
              )}
            </>
          ) : (
            <div className="bg-white border border-dashed border-notion-border rounded-lg px-4 py-16 text-center text-sm text-notion-text-secondary">
              왼쪽에서 PR을 선택하면 분석 파이프라인과 이슈가 여기에 표시됩니다.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
