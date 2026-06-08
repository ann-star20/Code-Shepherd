/**
 * MSW 핸들러 — API 모킹.
 */

import { http, HttpResponse } from "msw";

const BASE = "/api";

const MOCK_TEAM_ID = "11111111-1111-1111-1111-111111111111";
const MOCK_TEAM_ID_2 = "22222222-2222-2222-2222-222222222222";

export const handlers = [
  http.get(`${BASE}/auth/me`, () =>
    HttpResponse.json({
      id: "1",
      login: "testuser",
      name: "Test User",
      avatar_url: null,
      created_at: "2026-01-01T00:00:00Z",
    })
  ),
  http.post(`${BASE}/auth/logout`, () =>
    HttpResponse.json({ detail: "Logged out successfully" })
  ),

  http.get(`${BASE}/teams`, () =>
    HttpResponse.json([
      {
        id: MOCK_TEAM_ID,
        name: "Alpha Team",
        github_repo: "alpha-org/alpha-repo",
        created_at: "2026-01-01T00:00:00Z",
      },
    ])
  ),
  http.post(`${BASE}/teams`, async ({ request }) => {
    const body = (await request.json()) as { name: string; github_repo: string };
    return HttpResponse.json(
      {
        id: MOCK_TEAM_ID_2,
        name: body.name,
        github_repo: body.github_repo,
        created_at: new Date().toISOString(),
      },
      { status: 201 }
    );
  }),
  http.get(`${BASE}/teams/:id/members`, () =>
    HttpResponse.json([
      {
        id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
        user_id: "1",
        role: "lead",
        joined_at: "2026-01-01T00:00:00Z",
        login: "testuser",
        name: "Test User",
        avatar_url: null,
      },
    ])
  ),
  http.get(`${BASE}/invitations`, () => HttpResponse.json([])),
  http.post(`${BASE}/invitations/:id/accept`, () =>
    HttpResponse.json({
      invitation_id: "inv-1",
      team_id: MOCK_TEAM_ID,
      member: {
        id: "mem-2",
        user_id: "1",
        role: "member",
        login: "testuser",
        name: "Test User",
        avatar_url: null,
      },
    })
  ),
  http.post(`${BASE}/invitations/:id/decline`, () =>
    HttpResponse.json({
      id: "inv-1",
      team_id: MOCK_TEAM_ID,
      team_name: "Alpha Team",
      status: "declined",
      created_at: "2026-01-01T00:00:00Z",
    })
  ),
  http.post(`${BASE}/teams/:id/invitations`, () =>
    HttpResponse.json(
      {
        id: "inv-new",
        team_id: MOCK_TEAM_ID,
        team_name: "Alpha Team",
        status: "pending",
        created_at: new Date().toISOString(),
      },
      { status: 201 }
    )
  ),
  http.get(`${BASE}/teams/:id/prs`, ({ params }) => {
    return HttpResponse.json({
      team_id: params.id,
      scope: "team",
      prs: [
        {
          id: "pr-1",
          user_id: "1",
          author_login: "testuser",
          github_pr_number: 42,
          github_pr_url: "https://github.com/alpha-org/alpha-repo/pull/42",
          status: "open",
          submitted_at: "2026-01-01T00:00:00Z",
          is_lgtm: false,
        },
      ],
    });
  }),

  http.post(`${BASE}/analyze/static`, async ({ request }) => {
    const body = (await request.json()) as { task_id: string };
    return HttpResponse.json({
      task_id: body.task_id,
      agent: "static_analysis",
      issues: [
        {
          severity: "Major",
          line: 12,
          file: "src/utils/parse.py",
          message: "순환 복잡도가 너무 높습니다 (15 > 10).",
          rule_id: "C901",
          suggestion: "함수를 더 작은 단위로 분리하세요.",
        },
        {
          severity: "Minor",
          line: 3,
          file: "src/utils/parse.py",
          message: "사용되지 않는 import 'os'.",
          rule_id: "F401",
          suggestion: "import 문을 제거하세요.",
        },
      ],
      summary: { critical: 0, major: 1, minor: 1 },
      execution_ms: 142,
    });
  }),
  http.post(`${BASE}/analyze/security`, async ({ request }) => {
    const body = (await request.json()) as { task_id: string };
    return HttpResponse.json({
      task_id: body.task_id,
      agent: "security_scan",
      issues: [
        {
          severity: "Critical",
          line: 27,
          file: "src/db/query.py",
          message: "f-string으로 SQL을 조합해 SQL Injection에 취약합니다.",
          rule_id: "B608",
          suggestion: "파라미터 바인딩을 사용하세요.",
        },
      ],
      summary: { critical: 1, major: 0, minor: 0 },
      execution_ms: 215,
    });
  }),

  http.get(`${BASE}/users`, ({ request }) => {
    const url = new URL(request.url);
    const search = url.searchParams.get("search") ?? "";
    const users = [
      { id: "1", login: "alice", name: "Alice", avatar_url: null },
      { id: "2", login: "bob", name: "Bob", avatar_url: null },
    ].filter(
      (u) =>
        u.login.includes(search) ||
        (u.name?.toLowerCase().includes(search.toLowerCase()) ?? false)
    );
    return HttpResponse.json(users);
  }),
];

export const leadHandlers = [
  http.get(`${BASE}/teams/:id/prs`, () =>
    HttpResponse.json({ scope: "team", prs: [] })
  ),
];

export const memberHandlers = [
  http.get(`${BASE}/teams/:id/prs`, () =>
    HttpResponse.json({ scope: "self", prs: [] })
  ),
];
