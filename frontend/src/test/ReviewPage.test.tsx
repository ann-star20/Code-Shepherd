/**
 * ReviewPage — PR 목록 렌더 → PR 선택 → 판정 뱃지·이슈 테이블·코멘트 렌더,
 * 빈/처리중/에러 상태 검증. 외부 API 는 MSW 로 모킹.
 */

import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { describe, expect, it, beforeEach } from "vitest";
import { server } from "./msw/server";
import ReviewPage from "../pages/review/ReviewPage";
import { AuthProvider } from "../lib/auth";
import { TeamProvider } from "../contexts/TeamContext";

const BASE = "/api";
const M3_BASE = "/m3-api";

function createQueryClient() {
  return new QueryClient({ defaultOptions: { queries: { retry: false } } });
}

function renderReviewPage() {
  localStorage.setItem("access_token", "test-token");
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <AuthProvider>
        <TeamProvider>
          <MemoryRouter initialEntries={["/review"]}>
            <ReviewPage />
          </MemoryRouter>
        </TeamProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}

describe("ReviewPage", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("access_token", "test-token");
  });

  it("renders the team PR list", async () => {
    renderReviewPage();
    const item = await screen.findByTestId("review-pr-42");
    expect(item).toBeInTheDocument();
    expect(within(item).getByText(/#42/)).toBeInTheDocument();
    expect(within(item).getByText(/testuser/)).toBeInTheDocument();
  });

  it("shows verdict badge, issues table, comment, and GitHub link when a PR is selected", async () => {
    const user = userEvent.setup();
    renderReviewPage();
    await user.click(await screen.findByTestId("review-pr-42"));

    // 판정 뱃지
    const verdict = await screen.findByTestId("review-verdict");
    expect(verdict).toHaveTextContent(/rework/i);

    // 이슈 테이블 — severity·file:line·rule_id·message·suggestion
    const issues = await screen.findByTestId("review-issues");
    expect(within(issues).getByText("PERF-002")).toBeInTheDocument();
    expect(within(issues).getByText(/N\+1 쿼리/)).toBeInTheDocument();
    expect(within(issues).getByText(/src\/payment\.py:8/)).toBeInTheDocument();
    expect(within(issues).getByText("PERF-001")).toBeInTheDocument();

    // LLM 코멘트 본문
    expect(await screen.findByTestId("review-comment")).toHaveTextContent(
      "테스트 커버리지가 부족하고 N+1 쿼리가 있습니다."
    );

    // "GitHub에서 보기" 링크 — PR github_pr_url
    const link = screen.getByTestId("review-github-link");
    expect(link).toHaveAttribute(
      "href",
      "https://github.com/alpha-org/alpha-repo/pull/42"
    );
  });

  it("shows an empty state when the team has no PRs", async () => {
    server.use(
      http.get(`${BASE}/teams/:id/prs`, () =>
        HttpResponse.json({ scope: "team", prs: [] })
      )
    );
    renderReviewPage();
    expect(await screen.findByTestId("review-pr-empty")).toBeInTheDocument();
  });

  it("shows a '분석 결과 없음/처리 중' state when the review is not found", async () => {
    server.use(
      http.get(`${M3_BASE}/review/:owner/:repo/:pr`, ({ params }) =>
        HttpResponse.json({
          owner: params.owner,
          repo: params.repo,
          pr_number: Number(params.pr),
          found: false,
          verdict: null,
          comment: "",
          issues: [],
        })
      )
    );
    const user = userEvent.setup();
    renderReviewPage();
    await user.click(await screen.findByTestId("review-pr-42"));
    expect(await screen.findByTestId("review-empty")).toBeInTheDocument();
    // 가짜 데이터로 채우지 않음 — 이슈 테이블/뱃지 없음
    expect(screen.queryByTestId("review-issues")).not.toBeInTheDocument();
  });

  it("shows an error state when the review request fails", async () => {
    server.use(
      http.get(`${M3_BASE}/review/:owner/:repo/:pr`, () =>
        HttpResponse.json({ detail: "boom" }, { status: 500 })
      )
    );
    const user = userEvent.setup();
    renderReviewPage();
    await user.click(await screen.findByTestId("review-pr-42"));
    expect(await screen.findByTestId("review-error")).toBeInTheDocument();
  });
});
