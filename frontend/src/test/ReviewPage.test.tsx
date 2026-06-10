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

  it("renders the '사내 규칙' (rag_context) column with quote + optional source link", async () => {
    server.use(
      http.get(`${M3_BASE}/review/:owner/:repo/:pr`, ({ params }) =>
        HttpResponse.json({
          owner: params.owner,
          repo: params.repo,
          pr_number: Number(params.pr),
          found: true,
          verdict: "rework",
          comment: "## 🤖 자동 리뷰 (rework)\n\n본문",
          issues: [
            {
              severity: "Major",
              file: "src/payment.py",
              line: 8,
              message: "N+1 쿼리: 루프 안에서 DB 호출이 반복됩니다.",
              rule_id: "PERF-002",
              suggestion: "selectinload() 로 루프 밖에서 조회하세요.",
              rag_context: "ORM 가이드: 루프 안에서 개별 DB 호출을 하지 마세요.",
              source_url: "https://wiki.example.com/orm",
            },
            {
              severity: "Minor",
              file: "src/payment.py",
              line: 21,
              message: "O(n^2) 시간복잡도: 2중 중첩 루프.",
              rule_id: "PERF-001",
              suggestion: "해시맵으로 복잡도를 낮추세요.",
              rag_context: "복잡도 가이드: 중첩 루프 대신 해시맵을 쓰세요.",
            },
            {
              severity: "Minor",
              file: null,
              line: null,
              message: "사내 규칙 인용이 없는 이슈.",
              rule_id: null,
              suggestion: null,
            },
          ],
        })
      )
    );
    const user = userEvent.setup();
    renderReviewPage();
    await user.click(await screen.findByTestId("review-pr-42"));

    const issues = await screen.findByTestId("review-issues");
    // 사내 규칙(📖) 영역이 이슈마다 렌더된다(카드 레이아웃 — 칸 헤더가 아닌 카드별 박스).
    expect(within(issues).getAllByText("📖 사내 규칙").length).toBeGreaterThan(0);

    // 이슈 0 — 인용 텍스트 + 출처 링크
    const rag0 = await screen.findByTestId("issue-rag-0");
    expect(rag0).toHaveTextContent(
      "ORM 가이드: 루프 안에서 개별 DB 호출을 하지 마세요."
    );
    const link = within(rag0).getByRole("link");
    expect(link).toHaveAttribute("href", "https://wiki.example.com/orm");

    // 이슈 1 — 인용 텍스트만(가짜 링크 금지)
    const rag1 = screen.getByTestId("issue-rag-1");
    expect(rag1).toHaveTextContent(
      "복잡도 가이드: 중첩 루프 대신 해시맵을 쓰세요."
    );
    expect(within(rag1).queryByRole("link")).not.toBeInTheDocument();

    // 이슈 2 — 인용 없으면 '—'
    const rag2 = screen.getByTestId("issue-rag-2");
    expect(rag2).toHaveTextContent("—");
    expect(within(rag2).queryByRole("link")).not.toBeInTheDocument();
  });

  it("renders verdict reason, severity counts, and rich function-detail cards", async () => {
    server.use(
      http.get(`${M3_BASE}/review/:owner/:repo/:pr`, ({ params }) =>
        HttpResponse.json({
          owner: params.owner,
          repo: params.repo,
          pr_number: Number(params.pr),
          found: true,
          verdict: "rework",
          verdict_reason: "Major 2건 ≥ 기준 2건 → 수정 요청",
          comment: "본문",
          issues: [
            {
              severity: "Major",
              file: "src/cart.py",
              line: 8,
              message: "N+1 쿼리",
              rule_id: "PERF-002",
              suggestion: "고치세요",
            },
            {
              severity: "Major",
              file: "(전체)",
              line: null,
              message: "커버리지 미충족",
              rule_id: "TEST-001",
              suggestion: null,
            },
          ],
          rich_issues: [
            {
              agent: "performance",
              severity: "high",
              keyword: "N+1 쿼리",
              sub_category: "루프 쿼리",
              code_context: "장바구니 항목을 불러오는 함수",
              code_snippet: "def load_cart_items(uid):\n    for x in items:\n        db.query(x)",
              suggestion: "selectinload 사용",
              name_of_function: "load_cart_items",
              programming_language: "python",
              framework: "",
            },
          ],
        })
      )
    );
    const user = userEvent.setup();
    renderReviewPage();
    await user.click(await screen.findByTestId("review-pr-42"));

    // 판정 근거 한 줄
    expect(await screen.findByTestId("review-verdict-reason")).toHaveTextContent(
      "Major 2건 ≥ 기준 2건 → 수정 요청"
    );
    // 심각도 카운트 칩 (issues 에서 집계)
    const counts = screen.getByTestId("review-severity-counts");
    expect(counts).toHaveTextContent("Major 2");
    expect(counts).toHaveTextContent("Critical 0");

    // 함수별 상세 카드 — 함수명·분류·한줄설명·고칠 방향·코드 조각
    const rich = await screen.findByTestId("review-rich-0");
    expect(rich).toHaveTextContent("load_cart_items");
    expect(rich).toHaveTextContent("N+1 쿼리");
    expect(rich).toHaveTextContent("장바구니 항목을 불러오는 함수");
    expect(rich).toHaveTextContent("selectinload 사용");
    expect(within(rich).getByText(/def load_cart_items/)).toBeInTheDocument();
  });

  it("hides the rich section when rich_issues is empty (no fake content)", async () => {
    const user = userEvent.setup();
    renderReviewPage();
    await user.click(await screen.findByTestId("review-pr-42"));
    await screen.findByTestId("review-issues");
    expect(screen.queryByTestId("review-rich-section")).not.toBeInTheDocument();
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
