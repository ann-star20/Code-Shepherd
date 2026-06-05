import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { LogConsole } from "@/components/organisms/LogConsole";
import { ApprovalPanel } from "@/components/organisms/ApprovalPanel";

describe("LogConsole", () => {
  it("T_F9_logs_rendered: both log messages appear in DOM", () => {
    const logs = ["[Crawler] 완료", "[Extractor] 시작"];
    render(<LogConsole logs={logs} isConnected={true} />);
    expect(screen.getByText("[Crawler] 완료")).toBeTruthy();
    expect(screen.getByText("[Extractor] 시작")).toBeTruthy();
  });

  it("T_F9_disconnected: isConnected=false shows disconnect notice", () => {
    render(<LogConsole logs={[]} isConnected={false} />);
    expect(screen.getByText(/연결 끊김/)).toBeTruthy();
  });
});

describe("ApprovalPanel", () => {
  const diff = { draft: 4, approved: 0, committed: 0 };

  it("T_F9_approval_panel_buttons: shows 전체 승인 and 전체 거부 buttons", () => {
    render(
      <ApprovalPanel
        sessionId="sess1"
        onApproveAll={vi.fn()}
        onRejectAll={vi.fn()}
        diff={diff}
        isLoading={false}
      />
    );
    expect(screen.getByRole("button", { name: /전체 승인/ })).toBeTruthy();
    expect(screen.getByRole("button", { name: /전체 거부/ })).toBeTruthy();
  });

  it("T_F9_approve_clicked: click 전체 승인 calls onApproveAll", async () => {
    const onApproveAll = vi.fn();
    render(
      <ApprovalPanel
        sessionId="sess1"
        onApproveAll={onApproveAll}
        onRejectAll={vi.fn()}
        diff={diff}
        isLoading={false}
      />
    );
    await userEvent.click(screen.getByRole("button", { name: /전체 승인/ }));
    expect(onApproveAll).toHaveBeenCalledTimes(1);
  });

  it("T_F9_loading_disables: isLoading=true disables buttons and shows Spinner", () => {
    render(
      <ApprovalPanel
        sessionId="sess1"
        onApproveAll={vi.fn()}
        onRejectAll={vi.fn()}
        diff={diff}
        isLoading={true}
      />
    );
    const buttons = screen.getAllByRole("button");
    expect(buttons.every((b) => (b as HTMLButtonElement).disabled)).toBe(true);
    expect(document.querySelector("[data-testid='spinner']")).toBeTruthy();
  });
});
