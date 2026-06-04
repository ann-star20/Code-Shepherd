/**
 * MSW 핸들러 — API 모킹.
 */

import { http, HttpResponse } from "msw";

const BASE = "/api";

export const handlers = [
  // Auth
  http.get(`${BASE}/auth/me`, () =>
    HttpResponse.json({
      id: 1,
      login: "testuser",
      name: "Test User",
      avatar_url: null,
      created_at: "2026-01-01T00:00:00Z",
    })
  ),
  http.post(`${BASE}/auth/logout`, () =>
    HttpResponse.json({ detail: "Logged out successfully" })
  ),

  // Teams
  http.get(`${BASE}/teams`, () =>
    HttpResponse.json([{ id: 1, name: "Alpha Team", created_at: "2026-01-01T00:00:00Z" }])
  ),
  http.post(`${BASE}/teams`, async ({ request }) => {
    const body = (await request.json()) as { name: string };
    return HttpResponse.json({ id: 2, name: body.name, created_at: new Date().toISOString() }, { status: 201 });
  }),
  http.get(`${BASE}/teams/:id/members`, () =>
    HttpResponse.json([
      { id: 1, user_id: 1, role: "lead", joined_at: "2026-01-01T00:00:00Z" },
    ])
  ),
  http.get(`${BASE}/teams/:id/prs`, ({ params }) => {
    return HttpResponse.json({ team_id: params.id, scope: "team", prs: [] });
  }),

  // Users
  http.get(`${BASE}/users`, ({ request }) => {
    const url = new URL(request.url);
    const search = url.searchParams.get("search") ?? "";
    const users = [
      { id: 1, login: "alice", name: "Alice", avatar_url: null },
      { id: 2, login: "bob", name: "Bob", avatar_url: null },
    ].filter(
      (u) =>
        u.login.includes(search) ||
        (u.name?.toLowerCase().includes(search.toLowerCase()) ?? false)
    );
    return HttpResponse.json(users);
  }),
];

// lead 역할 시뮬레이션용 핸들러 (테스트에서 오버라이드)
export const leadHandlers = [
  http.get(`${BASE}/teams/:id/prs`, () =>
    HttpResponse.json({ scope: "team", prs: [] })
  ),
];

// member 역할 시뮬레이션용 핸들러
export const memberHandlers = [
  http.get(`${BASE}/teams/:id/prs`, () =>
    HttpResponse.json({ scope: "self", prs: [] })
  ),
];
