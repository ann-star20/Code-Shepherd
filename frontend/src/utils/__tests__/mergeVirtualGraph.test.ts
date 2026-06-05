import { describe, it, expect } from "vitest";
import { mergeVirtualGraph } from "@/utils/mergeVirtualGraph";
import { getNodeStyle } from "@/utils/nodeStyler";
import type { GraphNode } from "@/types/graph";
import type { StagingRecord } from "@/services/stagingService";

const makeConfirmed = (id: string, name: string): GraphNode => ({
  id,
  name,
  domain: "security",
  status: "COMMITTED",
});

const makeDraft = (id: string, name: string, aliases: string[] = []): StagingRecord => ({
  id,
  state: "DRAFT",
  concept_json: {
    id,
    name,
    domain: "security",
    status: "DRAFT",
    aliases,
    tags: [],
  },
});

describe("mergeVirtualGraph", () => {
  it("T_F7_merge_adds_draft: 2 confirmed + 2 draft → 4 nodes total", () => {
    const confirmed = [makeConfirmed("1", "SQLi"), makeConfirmed("2", "CSRF")];
    const draft = [makeDraft("3", "BufferOverflow"), makeDraft("4", "HeapSpray")];
    const { nodes } = mergeVirtualGraph(confirmed, draft);
    expect(nodes).toHaveLength(4);
  });

  it("T_F7_draft_status: draft nodes keep status=DRAFT", () => {
    const { nodes } = mergeVirtualGraph([], [makeDraft("1", "XSS")]);
    expect(nodes[0].status).toBe("DRAFT");
  });

  it("T_F7_committed_opacity: COMMITTED → opacity 1", () => {
    expect(getNodeStyle("COMMITTED", "security").opacity).toBe(1);
  });

  it("T_F7_draft_opacity: DRAFT → opacity 0.65", () => {
    expect(getNodeStyle("DRAFT", "security").opacity).toBe(0.65);
  });

  it("T_F7_same_as_candidate: draft aliases overlap confirmed name → SAME_AS_CANDIDATE edge", () => {
    const confirmed = [makeConfirmed("1", "XSS")];
    const draft = [makeDraft("2", "Cross-Site Scripting", ["XSS", "Cross Site Scripting"])];
    const { edges } = mergeVirtualGraph(confirmed, draft);
    const sameAs = edges.find((e) => e.type === "SAME_AS_CANDIDATE");
    expect(sameAs).toBeTruthy();
    expect([sameAs!.source, sameAs!.target]).toContain("1");
  });
});
