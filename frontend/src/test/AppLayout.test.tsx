/**
 * AppLayout — 팀 워크스페이스, 역할별 메뉴, 비활성화 규칙.
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { describe, expect, it, beforeEach } from "vitest";
import { server } from "./msw/server";
import AppLayout from "../layouts/AppLayout";
import { AuthProvider } from "../lib/auth";
import { TeamProvider } from "../contexts/TeamContext";

const BASE = "/api";

function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
}

function renderAppLayout(initialEntries = ["/"]) {
  localStorage.setItem("access_token", "test-token");
  const queryClient = createQueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <TeamProvider>
          <MemoryRouter initialEntries={initialEntries}>
            <Routes>
              <Route element={<AppLayout />}>
                <Route path="/" element={<div>Home page</div>} />
                <Route path="/kms" element={<div>KMS page</div>} />
                <Route path="/team" element={<div>Team page</div>} />
              </Route>
            </Routes>
          </MemoryRouter>
        </TeamProvider>
      </AuthProvider>
    </QueryClientProvider>
  );
}

describe("AppLayout sidebar", () => {
  beforeEach(() => {
    localStorage.clear();
    localStorage.setItem("access_token", "test-token");
  });

  it("shows lead-only nav when member role is lead", async () => {
    renderAppLayout();
    expect(await screen.findByTestId("team-switcher")).toBeInTheDocument();
    expect(await screen.findByTestId("nav-item-approvals")).toBeInTheDocument();
    expect(screen.getByTestId("nav-item-kms-manage")).toBeInTheDocument();
    expect(screen.queryByTestId("nav-item-home-member")).not.toBeInTheDocument();
  });

  it("shows member home nav and hides lead items for member role", async () => {
    server.use(
      http.get(`${BASE}/teams/:id/members`, () =>
        HttpResponse.json([
          {
            id: 1,
            user_id: "1",
            role: "member",
            joined_at: "2026-01-01T00:00:00Z",
            login: "testuser",
            name: "Test User",
            avatar_url: null,
          },
        ])
      ),
      http.get(`${BASE}/teams/:id/prs`, () =>
        HttpResponse.json({ scope: "self", prs: [] })
      )
    );
    renderAppLayout();
    expect(await screen.findByTestId("nav-item-home-member")).toBeInTheDocument();
    expect(screen.queryByTestId("nav-item-approvals")).not.toBeInTheDocument();
    expect(screen.queryByTestId("nav-item-kms-manage")).not.toBeInTheDocument();
  });

  it("disables team-required nav when no teams exist", async () => {
    server.use(http.get(`${BASE}/teams`, () => HttpResponse.json([])));
    renderAppLayout();
    expect(await screen.findByTestId("nav-disabled-hint")).toBeInTheDocument();
    expect(screen.getByTestId("nav-item-kms-disabled")).toBeInTheDocument();
    expect(screen.getByTestId("nav-item-settings")).toBeInTheDocument();
  });

  it("persists team switch to localStorage", async () => {
    const teamA = "11111111-1111-1111-1111-111111111111";
    const teamB = "22222222-2222-2222-2222-222222222222";
    server.use(
      http.get(`${BASE}/teams`, () =>
        HttpResponse.json([
          {
            id: teamA,
            name: "Alpha Team",
            github_repo: "a/a",
            created_at: "2026-01-01T00:00:00Z",
          },
          {
            id: teamB,
            name: "Beta Team",
            github_repo: "b/b",
            created_at: "2026-01-02T00:00:00Z",
          },
        ])
      )
    );
    const user = userEvent.setup();
    renderAppLayout();
    const switcher = await screen.findByTestId("team-switcher");
    await user.selectOptions(switcher, teamA);
    await user.selectOptions(switcher, teamB);
    expect(localStorage.getItem("codeshepherd:currentTeamId")).toBe(teamB);
  });

  it("team create button opens form", async () => {
    server.use(http.get(`${BASE}/teams`, () => HttpResponse.json([])));
    const user = userEvent.setup();
    renderAppLayout();
    await user.click(await screen.findByTestId("team-create-button"));
    expect(screen.getByTestId("sidebar-new-team-name")).toBeInTheDocument();
    expect(screen.getByTestId("sidebar-new-team-repo")).toBeInTheDocument();
  });

  it("shows notification bell and pending invite actions", async () => {
    const invId = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb";
    let accepted = false;
    server.use(
      http.get(`${BASE}/invitations`, () => {
        if (accepted) return HttpResponse.json([]);
        return HttpResponse.json([
          {
            id: invId,
            team_id: "11111111-1111-1111-1111-111111111111",
            team_name: "Alpha Team",
            invited_by_login: "lead1",
            invited_by_name: "Lead One",
            status: "pending",
            created_at: "2026-01-01T00:00:00Z",
          },
        ]);
      }),
      http.post(`${BASE}/invitations/${invId}/accept`, () => {
        accepted = true;
        return HttpResponse.json({
          invitation_id: invId,
          team_id: "11111111-1111-1111-1111-111111111111",
        });
      })
    );
    const user = userEvent.setup();
    renderAppLayout();
    expect(await screen.findByTestId("header-notifications")).toBeInTheDocument();
    await user.click(screen.getByLabelText("팀 초대 알림"));
    expect(screen.getByTestId(`notification-item-${invId}`)).toBeInTheDocument();
    await user.click(screen.getByTestId(`accept-invite-${invId}`));
    expect(await screen.findByText("새 초대가 없습니다")).toBeInTheDocument();
  });
});
