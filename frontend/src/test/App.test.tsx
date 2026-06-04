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
import ReviewPlaceholder from "../pages/review/Placeholder";
import LearningPlaceholder from "../pages/learning/Placeholder";
import GraphPlaceholder from "../pages/graph/Placeholder";

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

  it("Review placeholder shows 준비 중", () => {
    renderWithProviders(<ReviewPlaceholder />);
    expect(screen.getByTestId("placeholder-review")).toBeInTheDocument();
    expect(screen.getByText(/준비 중/)).toBeInTheDocument();
  });

  it("Learning placeholder shows 준비 중", () => {
    renderWithProviders(<LearningPlaceholder />);
    expect(screen.getByTestId("placeholder-learning")).toBeInTheDocument();
    expect(screen.getByText(/준비 중/)).toBeInTheDocument();
  });

  it("Graph placeholder shows 준비 중", () => {
    renderWithProviders(<GraphPlaceholder />);
    expect(screen.getByTestId("placeholder-graph")).toBeInTheDocument();
    expect(screen.getByText(/준비 중/)).toBeInTheDocument();
  });
});
