import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Badge } from "@/components/atoms/Badge";
import { StatusDot } from "@/components/atoms/StatusDot";
import { Button } from "@/components/atoms/Button";
import { Spinner } from "@/components/atoms/Spinner";

describe("Badge", () => {
  it("T_F2_badge_security: security domain shows teal/green class", () => {
    const { container } = render(<Badge domain="security" />);
    const el = container.firstElementChild as HTMLElement;
    expect(el.className).toMatch(/teal|green|#1D9E75/i);
  });

  it("T_F2_badge_both: label prop renders text", () => {
    render(<Badge domain="both" label="교차" />);
    expect(screen.getByText("교차")).toBeTruthy();
  });
});

describe("StatusDot", () => {
  it("T_F2_status_dot_running: RUNNING has animate-pulse", () => {
    const { container } = render(<StatusDot status="RUNNING" />);
    expect(container.innerHTML).toContain("animate-pulse");
  });

  it("T_F2_status_dot_done: DONE shows done indicator", () => {
    const { container } = render(<StatusDot status="DONE" />);
    expect(container.innerHTML).toMatch(/done|check|✓/i);
  });
});

describe("Button", () => {
  it("T_F2_button_disabled: disabled button does not call onClick", async () => {
    const fn = vi.fn();
    render(
      <Button variant="primary" disabled onClick={fn}>
        텍스트
      </Button>
    );
    await userEvent.click(screen.getByRole("button"));
    expect(fn).toHaveBeenCalledTimes(0);
  });

  it("T_F2_button_loading: loading renders Spinner", () => {
    render(
      <Button variant="primary" loading onClick={() => {}}>
        저장
      </Button>
    );
    expect(document.querySelector("[data-testid='spinner']")).toBeTruthy();
  });
});
