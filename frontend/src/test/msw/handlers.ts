/**
 * MSW 핸들러 — API 모킹.
 */

import { http, HttpResponse } from "msw";

const BASE = "/api";
const M3_BASE = "/m3-api";

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

  // m3 리뷰 결과 조회 (SESSION 5) — GET /m3-api/review/{owner}/{repo}/{pr}
  http.get(`${M3_BASE}/review/:owner/:repo/:pr`, ({ params }) => {
    return HttpResponse.json({
      owner: params.owner,
      repo: params.repo,
      pr_number: Number(params.pr),
      found: true,
      verdict: "rework",
      comment:
        "## 🤖 자동 리뷰 (rework)\n\n테스트 커버리지가 부족하고 N+1 쿼리가 있습니다.",
      issues: [
        {
          severity: "Major",
          file: "src/payment.py",
          line: 8,
          message: "N+1 쿼리: 루프 안에서 DB 호출이 반복됩니다.",
          rule_id: "PERF-002",
          suggestion: "joinedload()/selectinload() 로 루프 밖에서 조회하세요.",
        },
        {
          severity: "Minor",
          file: "src/payment.py",
          line: 21,
          message: "O(n^2) 시간복잡도: 2중 중첩 루프.",
          rule_id: "PERF-001",
          suggestion: "해시맵으로 복잡도를 낮추세요.",
        },
      ],
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

const M6_BASE = "/m6-api";

export const m6Handlers = [
  http.post(`${M6_BASE}/documents/check-duplicate`, () =>
    HttpResponse.json({ is_duplicate: false, doc_id: "doc-123" })
  ),
  http.post(`${M6_BASE}/pipeline/trigger`, () =>
    HttpResponse.json({ session_id: "sess-123", message: "started" }, { status: 202 })
  ),
  http.get(`${M6_BASE}/staging/:sessionId`, () =>
    HttpResponse.json({ items: [] })
  ),
  http.get(`${M6_BASE}/staging/:sessionId/diff`, () =>
    HttpResponse.json({ draft: 0, approved: 0, committed: 0 })
  ),
  http.post(`${M6_BASE}/staging/:sessionId/approve`, () =>
    HttpResponse.json({ ok: true })
  ),
  http.post(`${M6_BASE}/staging/:sessionId/reject`, () =>
    HttpResponse.json({ ok: true })
  ),
  http.post(`${M6_BASE}/staging/:sessionId/commit`, () =>
    HttpResponse.json({ ok: true })
  ),
  http.post(`${M6_BASE}/staging/:id/approve`, () =>
    HttpResponse.json({ ok: true })
  ),
  http.post(`${M6_BASE}/staging/:id/reject`, () =>
    HttpResponse.json({ ok: true })
  ),
  http.get(`${M6_BASE}/graph/topology`, () =>
    HttpResponse.json({ nodes: [], edges: [] })
  ),
  http.post(`${M6_BASE}/documents/metadata/learn`, () =>
    HttpResponse.json({ ok: true })
  ),
];
