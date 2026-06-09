import { describe, it, expect, vi, beforeEach } from "vitest";
import { renderHook, waitFor } from "@testing-library/react";
import { useGraphMerge } from "@/hooks/useGraphMerge";
import { graphService } from "@/services/graphService";
import { stagingService } from "@/services/stagingService";

vi.mock("@/services/graphService", () => ({
  graphService: { getTopology: vi.fn() },
}));
vi.mock("@/services/stagingService", () => ({
  stagingService: { getDraft: vi.fn() },
}));

// ── 확정 노드 팩토리 ─────────────────────────────────────────────────────────
const makeConfirmed = (id: string, name: string, domain: "security" | "performance" = "security") => ({
  id,
  name,
  domain,
  status: "COMMITTED" as const,
});

// ── 스테이징 레코드 팩토리 (새 스펙: concept_name / domains[] / merge_action) ──
// StagingRecord.concept_json 이 새 백엔드 스펙 필드를 사용함
const makeStagingRecord = (
  id: string,
  concept_name: string,
  aliases: string[] = [],
  domains: string[] = ["security"],
  merge_action?: "MERGE" | "RELATED_TO" | "NEW",
  target_concept?: string,
) => ({
  id,
  state: "DRAFT" as const,
  concept_json: {
    concept_name,
    domains,
    aliases,
    concept_type: "vulnerability_root_cause",
    severity: "high",
    description_ko: `${concept_name} 설명`,
    cwe_id: "CWE-999",
    owasp_id: "",
    merge_action,
    target_concept,
  },
});

const CONFIRMED_CSRF = makeConfirmed("csrf-1", "CSRF", "security");
const CONFIRMED_SQLI = makeConfirmed("sqli-1", "SQLi", "security");

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(graphService.getTopology).mockResolvedValue({
    nodes: [CONFIRMED_CSRF, CONFIRMED_SQLI],
    edges: [],
  });
  vi.mocked(stagingService.getDraft).mockResolvedValue([]);
});

describe("useGraphMerge", () => {

  // ── T_F7_no_session: 기존 테스트 유지 ──────────────────────────────────────
  it("T_F7_no_session: null sessionId → only confirmed nodes", async () => {
    vi.mocked(graphService.getTopology).mockResolvedValue({
      nodes: [makeConfirmed("1", "SQLi")],
      edges: [],
    });
    const { result } = renderHook(() => useGraphMerge(null));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    expect(result.current.nodes).toHaveLength(1);
    expect(result.current.nodes[0].name).toBe("SQLi");
  });

  // ── T_gm_U01: concept_name 필드 파싱 (구형 name 아님) ────────────────────────
  it("T_gm_U01: staging record의 concept_name 필드를 노드 name으로 사용한다", async () => {
    vi.mocked(stagingService.getDraft).mockResolvedValue([
      makeStagingRecord("st-1", "CommandInjection", [], ["security"]),
    ]);
    const { result } = renderHook(() => useGraphMerge("sess-u01"));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    const newNode = result.current.nodes.find((n) => n.name === "CommandInjection");
    expect(newNode).toBeTruthy();
  });

  // ── T_gm_U02: domains[] 첫 번째 요소가 domain에 사용된다 ──────────────────────
  it("T_gm_U02: domains 배열의 첫 번째 값이 GraphNode.domain에 매핑된다", async () => {
    vi.mocked(stagingService.getDraft).mockResolvedValue([
      makeStagingRecord("st-2", "MissingIndex", [], ["performance"]),
    ]);
    const { result } = renderHook(() => useGraphMerge("sess-u02"));
    await waitFor(() => expect(result.current.isLoading).toBe(false));
    const node = result.current.nodes.find((n) => n.name === "MissingIndex");
    expect(node?.domain).toBe("performance");
  });

  // ── T_gm_U03: MERGE_PENDING — 기존 노드 흡수, 신규 노드 미생성 ─────────────────
  it("T_gm_U03: aliases에 기존 확정 노드 이름 포함 → 확정 노드 status=MERGE_PENDING, 신규 노드 없음", async () => {
    vi.mocked(stagingService.getDraft).mockResolvedValue([
      // CrossSiteRequestForgery 은 aliases 에 "CSRF" 를 포함 → 기존 CSRF 노드에 흡수
      makeStagingRecord("st-3", "CrossSiteRequestForgery", ["CSRF", "Cross-Site Request Forgery"], ["security"]),
    ]);
    const { result } = renderHook(() => useGraphMerge("sess-u03"));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // 신규 독립 노드 생성 금지
    const newNode = result.current.nodes.find((n) => n.name === "CrossSiteRequestForgery");
    expect(newNode).toBeUndefined();

    // 기존 CSRF 노드의 status가 MERGE_PENDING으로 변이
    const csrfNode = result.current.nodes.find((n) => n.name === "CSRF");
    expect(csrfNode).toBeTruthy();
    expect(csrfNode?.status).toBe("MERGE_PENDING");
  });

  // ── T_gm_U04: merge_action=MERGE → alias 없어도 target_concept로 흡수 ─────────
  it("T_gm_U04: merge_action=MERGE + target_concept 지정 → target 노드 MERGE_PENDING 전이", async () => {
    vi.mocked(stagingService.getDraft).mockResolvedValue([
      makeStagingRecord("st-4", "SqlInjectionAttack", [], ["security"], "MERGE", "SQLi"),
    ]);
    const { result } = renderHook(() => useGraphMerge("sess-u04"));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const sqliNode = result.current.nodes.find((n) => n.name === "SQLi");
    expect(sqliNode?.status).toBe("MERGE_PENDING");

    // 독립 신규 노드 없음
    expect(result.current.nodes.find((n) => n.name === "SqlInjectionAttack")).toBeUndefined();
  });

  // ── T_gm_U05: merge_action=RELATED_TO → 새 점선 노드 + RELATED_TO_CANDIDATE 엣지 ──
  it("T_gm_U05: merge_action=RELATED_TO → 신규 노드 생성 + RELATED_TO_CANDIDATE 엣지 포함", async () => {
    vi.mocked(stagingService.getDraft).mockResolvedValue([
      makeStagingRecord("st-5", "SSRF", [], ["security"], "RELATED_TO", "CommandInjection"),
    ]);
    const { result } = renderHook(() => useGraphMerge("sess-u05"));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    // 신규 노드 존재
    const ssrfNode = result.current.nodes.find((n) => n.name === "SSRF");
    expect(ssrfNode).toBeTruthy();
    expect(ssrfNode?.status).toBe("DRAFT");

    // RELATED_TO_CANDIDATE 엣지 존재
    const rtEdge = result.current.edges.find((e) => e.type === "RELATED_TO_CANDIDATE");
    expect(rtEdge).toBeTruthy();
  });

  // ── T_gm_U06: merge_action=NEW (또는 없음) → 완전 독립 DRAFT 노드 ──────────────
  it("T_gm_U06: merge_action=NEW → alias/target 없이 독립 DRAFT 노드 생성", async () => {
    vi.mocked(stagingService.getDraft).mockResolvedValue([
      makeStagingRecord("st-6", "MemoryLeak", [], ["performance"], "NEW"),
    ]);
    const { result } = renderHook(() => useGraphMerge("sess-u06"));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const mlNode = result.current.nodes.find((n) => n.name === "MemoryLeak");
    expect(mlNode).toBeTruthy();
    expect(mlNode?.status).toBe("DRAFT");

    // RELATED_TO_CANDIDATE 엣지 없음
    const rtEdge = result.current.edges.find((e) => e.type === "RELATED_TO_CANDIDATE");
    expect(rtEdge).toBeUndefined();
  });

  // ── T_gm_U07: merge_action 없을 때도 alias 매칭으로 MERGE_PENDING 판정 ─────────
  it("T_gm_U07: merge_action 미지정 + aliases 매칭 → MERGE_PENDING 흡수", async () => {
    vi.mocked(stagingService.getDraft).mockResolvedValue([
      // aliases에 "CSRF" 포함 → 자동 MERGE_PENDING
      makeStagingRecord("st-7", "SeaSurf", ["CSRF", "Session Riding"], ["security"]),
    ]);
    const { result } = renderHook(() => useGraphMerge("sess-u07"));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    expect(result.current.nodes.find((n) => n.name === "SeaSurf")).toBeUndefined();
    const csrfNode = result.current.nodes.find((n) => n.name === "CSRF");
    expect(csrfNode?.status).toBe("MERGE_PENDING");
  });

  // ── T_gm_U08: merge_action 없고 alias 불일치 → DRAFT 독립 노드 ────────────────
  it("T_gm_U08: merge_action 없고 alias 불일치 → 독립 DRAFT 노드 추가", async () => {
    vi.mocked(stagingService.getDraft).mockResolvedValue([
      makeStagingRecord("st-8", "ClickjackingAttack", ["Clickjacking"], ["security"]),
    ]);
    const { result } = renderHook(() => useGraphMerge("sess-u08"));
    await waitFor(() => expect(result.current.isLoading).toBe(false));

    const node = result.current.nodes.find((n) => n.name === "ClickjackingAttack");
    expect(node).toBeTruthy();
    expect(node?.status).toBe("DRAFT");
  });
});
