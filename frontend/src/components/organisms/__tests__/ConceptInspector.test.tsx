import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ConceptInspector } from "@/components/organisms/ConceptInspector";
import type { ConceptNode } from "@/types/concept";

const makeNode = (overrides: Partial<ConceptNode> = {}): ConceptNode => ({
  id: "node-1",
  name: "SQL Injection",
  domain: "security",
  status: "DRAFT",
  aliases: [],
  tags: [],
  ...overrides,
});

describe("ConceptInspector", () => {
  it("T_F11_null_node: shows guide text when node is null", () => {
    render(
      <ConceptInspector
        node={null}
        sessionId="sid"
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByText("노드를 클릭하세요")).toBeTruthy();
  });

  it("T_F11_committed_readonly: no approve/reject buttons for COMMITTED", () => {
    const node = makeNode({ status: "COMMITTED" });
    render(
      <ConceptInspector
        node={node}
        sessionId="sid"
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.queryByRole("button", { name: "승인" })).toBeNull();
    expect(screen.queryByRole("button", { name: "거부" })).toBeNull();
  });

  it("T_F11_draft_buttons: shows approve and reject buttons for DRAFT", () => {
    const node = makeNode({ status: "DRAFT" });
    render(
      <ConceptInspector
        node={node}
        sessionId="sid"
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByRole("button", { name: "승인" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "거부" })).toBeTruthy();
  });

  it("T_F11_approve_click: calls onApprove with node.id", async () => {
    const onApprove = vi.fn();
    const node = makeNode({ id: "node-42", status: "DRAFT" });
    render(
      <ConceptInspector
        node={node}
        sessionId="sid"
        onApprove={onApprove}
        onReject={vi.fn()}
        onClose={vi.fn()}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: "승인" }));
    expect(onApprove).toHaveBeenCalledTimes(1);
    expect(onApprove).toHaveBeenCalledWith("node-42");
  });

  it("T_F11_severity_critical: CRITICAL severity renders with red class", () => {
    const node = makeNode({ severity: "critical" });
    render(
      <ConceptInspector
        node={node}
        sessionId="sid"
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onClose={vi.fn()}
      />
    );
    const el = screen.getByText("critical");
    expect(el.className).toMatch(/red/);
  });

  it("T_F11_aliases: renders all aliases", () => {
    const node = makeNode({ aliases: ["Cross-Site Scripting", "XSS"] });
    render(
      <ConceptInspector
        node={node}
        sessionId="sid"
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByText("Cross-Site Scripting")).toBeTruthy();
    expect(screen.getByText("XSS")).toBeTruthy();
  });

  it("T_F11_domain_badge: renders Badge with domain='both'", () => {
    const node = makeNode({ domain: "both" });
    render(
      <ConceptInspector
        node={node}
        sessionId="sid"
        onApprove={vi.fn()}
        onReject={vi.fn()}
        onClose={vi.fn()}
      />
    );
    expect(screen.getByText("both")).toBeTruthy();
  });
});
