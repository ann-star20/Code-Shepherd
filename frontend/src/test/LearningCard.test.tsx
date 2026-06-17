/**
 * TDD: LearningCard — 완료된 학습 카드 렌더링 + 자동 완료 처리 (T9 Slice 3, FRONTEND_SPEC Section 4/5/6-1).
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";

import LearningCard from "../pages/learning/components/LearningCard";
import type { IssueWithPlan } from "../pages/learning/hooks/useLearningApi";
import { m4Api } from "../pages/learning/lib/m4Api";

vi.mock("../pages/learning/lib/m4Api", () => ({
  m4Api: { post: vi.fn().mockResolvedValue({ data: { id: "plan-1", completed_at: "2026-06-07T00:00:00Z" } }) },
}));

const COMPLETED_ISSUE: IssueWithPlan = {
  id: "issue-1",
  keyword: "SQL Injection",
  severity: "high",
  plan: {
    id: "plan-1",
    status: "completed",
    llm_fallback: false,
    error_message: null,
    ragas_reason: null,
    attempt_count: 1,
    card_content: {
      header: {
        keyword: "SQL Injection",
        name_of_function: "search_products",
        sub_category: "input validation",
        language: "Python",
        framework: "FastAPI",
        framework_version: "0.104.0",
        depth: "deep",
      },
      before_code: "def vulnerable_query(keyword):\n    return f\"SELECT * FROM t WHERE x='{keyword}'\"",
      after_code: 'def safe_query(keyword):\n    return "SELECT * FROM t WHERE x=%s", (keyword,)',
      explanation: "사용자 입력을 직접 SQL에 삽입하면 공격자가 쿼리를 조작할 수 있습니다.",
      why_dangerous: "상품 검색에 SQL Injection이 발생하면 전체 DB가 노출될 수 있습니다.",
      core_summary: "SQL Injection: 사용자 입력은 Parameterized Query로만 처리한다",
      learning_recommendations: [
        { title: "Parameterized Query 패턴", description: "FastAPI + SQLAlchemy 안전한 쿼리 작성법" },
      ],
    },
  },
};

describe("LearningCard", () => {
  afterEach(() => {
    vi.mocked(m4Api.post).mockClear();
  });

  it("완료된 카드의 핵심 내용(헤더, before/after 코드, 설명, 핵심 요약)을 표시한다", async () => {
    const user = userEvent.setup();
    render(<LearningCard issue={COMPLETED_ISSUE} />);

    expect(screen.getByText(/\[SQL Injection\]/)).toBeInTheDocument();
    expect(screen.queryByText(/vulnerable_query/)).not.toBeInTheDocument();

    await user.click(screen.getByRole("button"));

    expect(screen.getByText(/vulnerable_query/)).toBeInTheDocument();
    expect(screen.getByText(/safe_query/)).toBeInTheDocument();
    expect(screen.getByText(/사용자 입력을 직접 SQL에 삽입하면/)).toBeInTheDocument();
    expect(screen.getByText(/Parameterized Query로만 처리한다/)).toBeInTheDocument();
  });

  it("마운트 시 자동으로 POST /api/complete { plan_id }를 1번 호출한다 (D11, idempotent)", () => {
    render(<LearningCard issue={COMPLETED_ISSUE} />);

    expect(m4Api.post).toHaveBeenCalledWith("/api/complete", { plan_id: "plan-1" });
    expect(m4Api.post).toHaveBeenCalledTimes(1);
  });

  it("before_code가 null이면 Before 패널을 숨기고 After 코드만 표시한다", async () => {
    const user = userEvent.setup();
    const issueWithoutBeforeCode: IssueWithPlan = {
      ...COMPLETED_ISSUE,
      plan: {
        ...COMPLETED_ISSUE.plan,
        card_content: {
          ...COMPLETED_ISSUE.plan.card_content!,
          before_code: null,
        },
      },
    };

    render(<LearningCard issue={issueWithoutBeforeCode} />);
    await user.click(screen.getByRole("button"));

    expect(screen.queryByText("Before (문제 코드)")).not.toBeInTheDocument();
    expect(screen.queryByText(/vulnerable_query/)).not.toBeInTheDocument();
    expect(screen.getByText("After (수정 코드)")).toBeInTheDocument();
    expect(screen.getByText(/safe_query/)).toBeInTheDocument();
  });

  it("framework 정보가 없으면 framework/version 없이 language만 표시하고 군더더기 구분자를 남기지 않는다", () => {
    const noFrameworkIssue: IssueWithPlan = {
      ...COMPLETED_ISSUE,
      plan: {
        ...COMPLETED_ISSUE.plan,
        card_content: {
          ...COMPLETED_ISSUE.plan.card_content!,
          header: { ...COMPLETED_ISSUE.plan.card_content!.header, framework: "", framework_version: "" },
        },
      },
    };

    render(<LearningCard issue={noFrameworkIssue} />);

    const metaLine = screen.getByText("Python");
    expect(metaLine).toBeInTheDocument();
    expect(metaLine.textContent).toBe("Python");
  });

  it("llm_fallback이 true이면 사내 문서 기반이 아니라는 라벨을 표시한다", () => {
    const fallbackIssue: IssueWithPlan = {
      ...COMPLETED_ISSUE,
      plan: { ...COMPLETED_ISSUE.plan, llm_fallback: true },
    };

    render(<LearningCard issue={fallbackIssue} />);

    expect(screen.getByText(/사내 문서 기반 아님/)).toBeInTheDocument();
  });

  it.each(["pending", "running"] as const)("status가 %s이면 로딩 스피너를 표시하고 카드 본문은 렌더링하지 않는다", (status) => {
    const inProgressIssue: IssueWithPlan = {
      ...COMPLETED_ISSUE,
      plan: { ...COMPLETED_ISSUE.plan, status, card_content: null },
    };

    render(<LearningCard issue={inProgressIssue} />);

    expect(screen.getByRole("status")).toBeInTheDocument();
    expect(screen.queryByText(/Parameterized Query로만 처리한다/)).not.toBeInTheDocument();
    expect(m4Api.post).not.toHaveBeenCalled();
  });

  it("status가 failed이면 친절한 안내 메시지를 표시하고 원본 error_message는 노출하지 않는다", () => {
    const failedIssue: IssueWithPlan = {
      ...COMPLETED_ISSUE,
      plan: {
        ...COMPLETED_ISSUE.plan,
        status: "failed",
        card_content: null,
        error_message: "Gemini API 오류: 429 rate limit exceeded",
      },
    };

    render(<LearningCard issue={failedIssue} />);

    expect(screen.getByText("카드를 생성하는 중 문제가 발생했어요")).toBeInTheDocument();
    expect(screen.queryByText(/rate limit/)).not.toBeInTheDocument();
    expect(m4Api.post).not.toHaveBeenCalled();
  });
});
