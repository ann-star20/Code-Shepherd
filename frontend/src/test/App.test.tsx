/**
 * TDD: 라우트 가드, 로그인 흐름, placeholder 표시.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it } from "vitest";

// 컴포넌트 임포트
import Login from "../pages/Login";
import KmsPlaceholder from "../pages/kms/Placeholder";
import ReviewPage from "../pages/review/ReviewPage";
import LearningPlaceholder from "../pages/learning/Placeholder";
import YoutubePlaceholder from "../pages/youtube/Placeholder";
import ApprovalsPlaceholder from "../pages/approvals/Placeholder";
import KmsManagePlaceholder from "../pages/kms/ManagePlaceholder";
import { AuthProvider } from "../lib/auth";
import { TeamProvider } from "../contexts/TeamContext";

function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderWithProviders(ui: React.ReactElement, { initialEntries = ["/"] } = {}) {
  const queryClient = createQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={initialEntries}>{ui}</MemoryRouter>
    </QueryClientProvider>
  );
}

// ---------------------------------------------------------------------------
// 로그인 화면
// ---------------------------------------------------------------------------

describe("Login page", () => {
  it("renders GitHub login button", () => {
    renderWithProviders(<Login />);
    expect(screen.getByTestId("github-login-button")).toBeInTheDocument();
  });

  it("GitHub login button exists and is clickable", async () => {
    renderWithProviders(<Login />);
    const btn = screen.getByTestId("github-login-button");
    expect(btn).toBeInTheDocument();
    expect(btn).not.toBeDisabled();
  });
});

// ---------------------------------------------------------------------------
// Placeholder 페이지
// ---------------------------------------------------------------------------

describe("Placeholder pages", () => {
  it("KMS placeholder shows 준비 중", () => {
    renderWithProviders(<KmsPlaceholder />);
    expect(screen.getByTestId("placeholder-kms")).toBeInTheDocument();
    expect(screen.getByText(/준비 중/)).toBeInTheDocument();
  });

  it("Learning placeholder shows 준비 중", () => {
    renderWithProviders(<LearningPlaceholder />);
    expect(screen.getByTestId("placeholder-learning")).toBeInTheDocument();
    expect(screen.getByText(/커리큘럼 추천/)).toBeInTheDocument();
    expect(screen.getByText(/준비 중/)).toBeInTheDocument();
  });

  it("Youtube placeholder shows 준비 중", () => {
    renderWithProviders(<YoutubePlaceholder />);
    expect(screen.getByTestId("placeholder-youtube")).toBeInTheDocument();
    expect(screen.getByText(/준비 중/)).toBeInTheDocument();
  });

  it("Approvals placeholder shows 준비 중", () => {
    renderWithProviders(<ApprovalsPlaceholder />);
    expect(screen.getByTestId("placeholder-approvals")).toBeInTheDocument();
    expect(screen.getByText(/준비 중/)).toBeInTheDocument();
  });

  it("KMS manage placeholder shows 준비 중", () => {
    renderWithProviders(<KmsManagePlaceholder />);
    expect(screen.getByTestId("placeholder-kms-manage")).toBeInTheDocument();
    expect(screen.getByText(/준비 중/)).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// m2 — PR 코드 리뷰 (정적 분석 · 보안 스캔)
// ---------------------------------------------------------------------------

describe("ReviewPage (m2)", () => {
  function renderReviewPage() {
    localStorage.setItem("access_token", "test-token");
    const queryClient = createQueryClient();
    return render(
      <QueryClientProvider client={queryClient}>
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

  it("run button is disabled until pr id and diff are filled", () => {
    renderReviewPage();
    expect(screen.getByTestId("review-run")).toBeDisabled();
  });

  it("runs analysis and renders static + security results", async () => {
    const user = userEvent.setup();
    renderReviewPage();

    await user.type(screen.getByTestId("review-pr-id"), "pr-42");
    await user.type(screen.getByTestId("review-diff"), "@@ -1 +1 @@");
    await user.click(screen.getByTestId("review-run"));

    expect(await screen.findByTestId("result-static_analysis")).toBeInTheDocument();
    expect(await screen.findByTestId("result-security_scan")).toBeInTheDocument();
    expect(screen.getByText(/SQL Injection/)).toBeInTheDocument();
  });
});
