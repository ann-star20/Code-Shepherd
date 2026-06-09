import { describe, it, expect } from "vitest";
import { getNodeStyle, getDomainColor } from "@/utils/nodeStyler";
import { parseDocId } from "@/utils/docId";

describe("nodeStyler", () => {
  it("T_F1_draft_style", () => {
    const s = getNodeStyle("DRAFT", "security");
    expect(s.opacity).toBe(0.65);
    expect(s.strokeDasharray).toBe("5,3");
  });

  it("T_F1_committed_style", () => {
    const s = getNodeStyle("COMMITTED", "security");
    expect(s.opacity).toBe(1);
    expect(s.strokeDasharray).toBe("none");
  });

  it("T_F1_rejected_style", () => {
    const s = getNodeStyle("REJECTED", "performance");
    expect(s.color).toBe("#E24B4A");
  });

  // ── T_gm_ns: MERGE_PENDING + REJECTED opacity 수정 ──────────────────────────
  it("T_gm_ns_01: MERGE_PENDING → opacity 1 (기존 노드에 오버레이, 흐림 없음)", () => {
    const s = getNodeStyle("MERGE_PENDING", "security");
    expect(s.opacity).toBe(1);
  });

  it("T_gm_ns_02: MERGE_PENDING → strokeDasharray none (실선 유지)", () => {
    const s = getNodeStyle("MERGE_PENDING", "security");
    expect(s.strokeDasharray).toBe("none");
  });

  it("T_gm_ns_03: MERGE_PENDING → 도메인 색상 그대로 유지", () => {
    const s = getNodeStyle("MERGE_PENDING", "security");
    expect(s.color).toBe("#1D9E75");
  });

  it("T_gm_ns_04: REJECTED → opacity 0.3 (spec 준수, 구형 0.5 아님)", () => {
    const s = getNodeStyle("REJECTED", "security");
    expect(s.opacity).toBe(0.3);
  });

  it("T_F1_domain_color_security", () => {
    expect(getDomainColor("security")).toBe("#1D9E75");
  });

  it("T_F1_domain_color_both", () => {
    expect(getDomainColor("both")).toBe("#534AB7");
  });
});

describe("parseDocId", () => {
  it("T_F1_parse_doc_id", () => {
    const result = parseDocId("EXT_https---docs-django_a3f9c21b");
    expect(result.prefix).toBe("EXT");
    expect(result.hash).toBe("a3f9c21b");
  });
});
