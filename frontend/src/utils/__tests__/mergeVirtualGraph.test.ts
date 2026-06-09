/**
 * TDD: mergeVirtualGraph 순수 함수 검증
 *
 * 규칙 (PRD §2.2):
 *  M*  : merge 판정 — 기존 노드에 MERGE_PENDING 배지 오버레이, 신규 독립 노드 금지
 *  R*  : RELATED_TO — 신규 DRAFT 노드 파생 + RELATED_TO_CANDIDATE 엣지 가교
 *  N*  : NEW — 완전 독립 DRAFT 노드, 엣지 없음
 *  F*  : 필드명 규칙 — concept_name / domains[] 표준 명세 준수
 */
import { describe, it, expect } from "vitest";
import { mergeVirtualGraph } from "@/utils/mergeVirtualGraph";
import type { GraphNode } from "@/types/graph";
import type { StagingRecord } from "@/services/stagingService";

// ── 공통 픽스처 ──────────────────────────────────────────────────────────────

const confirmedNode = (id: string, name: string): GraphNode => ({
  id,
  name,
  domain: "security",
  status: "COMMITTED",
});

const draftRecord = (
  id: string,
  conceptName: string,
  mergeAction?: "MERGE" | "RELATED_TO" | "NEW",
  targetConcept?: string,
  domains = ["security"],
): StagingRecord => ({
  id,
  state: "DRAFT",
  concept_json: {
    concept_name: conceptName,
    domains,
    aliases: [],
    merge_action: mergeAction,
    target_concept: targetConcept,
  },
});

// ─────────────────────────────────────────────────────────────────────────────
// M* — MERGE: 기존 노드 오버레이 배지
// ─────────────────────────────────────────────────────────────────────────────

describe("mergeVirtualGraph — MERGE 판정", () => {
  it("M01: merge_action=MERGE + target_concept 명시 → 기존 노드 status가 MERGE_PENDING으로 변경된다", () => {
    const confirmed = [confirmedNode("csrf-1", "CSRF")];
    const draft = [draftRecord("draft-1", "CrossSiteRequestForgery", "MERGE", "CSRF")];

    const { nodes } = mergeVirtualGraph(confirmed, draft);
    const csrfNode = nodes.find((n) => n.name === "CSRF");
    expect(csrfNode?.status).toBe("MERGE_PENDING");
  });

  it("M02: merge_action=MERGE → 신규 독립 노드가 추가되지 않는다 (기존 노드 수 유지)", () => {
    const confirmed = [confirmedNode("csrf-1", "CSRF")];
    const draft = [draftRecord("draft-1", "CrossSiteRequestForgery", "MERGE", "CSRF")];

    const { nodes } = mergeVirtualGraph(confirmed, draft);
    expect(nodes).toHaveLength(confirmed.length); // 1개 그대로
  });

  it("M03: aliases에 기존 확정 노드명이 포함되면 자동 MERGE_PENDING 처리된다", () => {
    const confirmed = [confirmedNode("xss-1", "XSS")];
    const draft: StagingRecord[] = [{
      id: "draft-2",
      state: "DRAFT",
      concept_json: {
        concept_name: "CrossSiteScripting",
        domains: ["security"],
        aliases: ["XSS", "Cross-Site Scripting"],
      },
    }];

    const { nodes } = mergeVirtualGraph(confirmed, draft);
    const xssNode = nodes.find((n) => n.name === "XSS");
    expect(xssNode?.status).toBe("MERGE_PENDING");
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// R* — RELATED_TO: 독립 점선 노드 + 가교 엣지
// ─────────────────────────────────────────────────────────────────────────────

describe("mergeVirtualGraph — RELATED_TO 판정", () => {
  it("R01: merge_action=RELATED_TO → 신규 DRAFT 노드가 추가된다", () => {
    const confirmed = [confirmedNode("csrf-1", "CSRF")];
    const draft = [draftRecord("draft-3", "SSRF", "RELATED_TO", "CSRF")];

    const { nodes } = mergeVirtualGraph(confirmed, draft);
    const ssrfNode = nodes.find((n) => n.name === "SSRF");
    expect(ssrfNode).toBeDefined();
    expect(ssrfNode?.status).toBe("DRAFT");
  });

  it("R02: merge_action=RELATED_TO + target_concept → RELATED_TO_CANDIDATE 엣지가 생성된다", () => {
    const confirmed = [confirmedNode("csrf-1", "CSRF")];
    const draft = [draftRecord("draft-3", "SSRF", "RELATED_TO", "CSRF")];

    const { edges } = mergeVirtualGraph(confirmed, draft);
    const bridgeEdge = edges.find((e) => e.type === "RELATED_TO_CANDIDATE");
    expect(bridgeEdge).toBeDefined();
    expect(bridgeEdge?.target).toBe("draft-3");
  });

  it("R03: RELATED_TO이지만 target_concept 없으면 엣지 없이 독립 DRAFT 노드만 추가", () => {
    const confirmed: GraphNode[] = [];
    const draft = [draftRecord("draft-4", "SSRF", "RELATED_TO", undefined)];

    const { nodes, edges } = mergeVirtualGraph(confirmed, draft);
    expect(nodes).toHaveLength(1);
    expect(edges).toHaveLength(0);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// N* — NEW: 완전 독립 DRAFT 노드
// ─────────────────────────────────────────────────────────────────────────────

describe("mergeVirtualGraph — NEW 판정", () => {
  it("N01: merge_action=NEW → 독립 DRAFT 노드 추가, 엣지 없음", () => {
    const confirmed = [confirmedNode("csrf-1", "CSRF")];
    const draft = [draftRecord("draft-5", "Clickjacking", "NEW")];

    const { nodes, edges } = mergeVirtualGraph(confirmed, draft);
    const newNode = nodes.find((n) => n.name === "Clickjacking");
    expect(newNode?.status).toBe("DRAFT");
    expect(edges).toHaveLength(0);
  });

  it("N02: merge_action 미설정(undefined) → NEW와 동일하게 독립 DRAFT 노드 추가", () => {
    const confirmed: GraphNode[] = [];
    const draft = [draftRecord("draft-6", "Orphan", undefined)];

    const { nodes, edges } = mergeVirtualGraph(confirmed, draft);
    expect(nodes).toHaveLength(1);
    expect(nodes[0].status).toBe("DRAFT");
    expect(edges).toHaveLength(0);
  });
});

// ─────────────────────────────────────────────────────────────────────────────
// F* — 필드명 규칙: concept_name + domains[]
// ─────────────────────────────────────────────────────────────────────────────

describe("mergeVirtualGraph — 필드명 표준 명세 준수", () => {
  it("F01: concept_name 필드로 노드 name을 설정한다", () => {
    const draft = [draftRecord("d1", "SQL_Injection", "NEW")];
    const { nodes } = mergeVirtualGraph([], draft);
    expect(nodes[0].name).toBe("SQL_Injection");
  });

  it("F02: domains[0]으로 노드 domain을 설정한다", () => {
    const draft = [draftRecord("d2", "CachePoisoning", "NEW", undefined, ["performance"])];
    const { nodes } = mergeVirtualGraph([], draft);
    expect(nodes[0].domain).toBe("performance");
  });

  it("F03: domains[] 없으면 security 기본값 사용", () => {
    const draft: StagingRecord[] = [{
      id: "d3",
      state: "DRAFT",
      concept_json: { concept_name: "UnknownConcept", domains: [] },
    }];
    const { nodes } = mergeVirtualGraph([], draft);
    expect(nodes[0].domain).toBe("security");
  });
});
