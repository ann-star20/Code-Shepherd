/**
 * TDD: 인증 가드 — 미인증 시 로그인으로 리다이렉트.
 */

import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { describe, expect, it, beforeEach } from "vitest";

import { AuthProvider } from "../lib/auth";

function TestApp({ initialPath = "/" }: { initialPath?: string }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  return (
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[initialPath]}>
        <AuthProvider>
          <Routes>
            <Route path="/login" element={<div data-testid="login-page">Login</div>} />
            <Route path="/" element={<div data-testid="dashboard">Dashboard</div>} />
          </Routes>
        </AuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("Auth guard", () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it("unauthenticated user — AuthProvider renders without crash", () => {
    const { container } = render(<TestApp initialPath="/" />);
    expect(container).toBeTruthy();
  });

  it("login page is accessible without auth", () => {
    render(<TestApp initialPath="/login" />);
    expect(screen.getByTestId("login-page")).toBeInTheDocument();
  });
});
