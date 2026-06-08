/**
 * TDD: 학습 시작 팝업 모달 — 표시/숨김, 예/아니오 콜백 호출 (T9, FRONTEND_SPEC Section 1/10).
 */

import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import LearningModal from "../pages/learning/components/LearningModal";

describe("LearningModal", () => {
  it("open이 true이면 안내 문구와 예/아니오 버튼을 표시한다", () => {
    render(<LearningModal open onConfirm={vi.fn()} onCancel={vi.fn()} />);

    expect(screen.getByText("학습을 시작하겠습니까?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "예" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "아니오" })).toBeInTheDocument();
  });

  it("open이 false이면 아무것도 렌더링하지 않는다", () => {
    render(<LearningModal open={false} onConfirm={vi.fn()} onCancel={vi.fn()} />);

    expect(screen.queryByText("학습을 시작하겠습니까?")).not.toBeInTheDocument();
  });

  it("예 클릭 시 onConfirm만 1번 호출된다", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(<LearningModal open onConfirm={onConfirm} onCancel={onCancel} />);

    await user.click(screen.getByRole("button", { name: "예" }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
    expect(onCancel).not.toHaveBeenCalled();
  });

  it("아니오 클릭 시 onCancel만 1번 호출된다", async () => {
    const user = userEvent.setup();
    const onConfirm = vi.fn();
    const onCancel = vi.fn();
    render(<LearningModal open onConfirm={onConfirm} onCancel={onCancel} />);

    await user.click(screen.getByRole("button", { name: "아니오" }));

    expect(onCancel).toHaveBeenCalledTimes(1);
    expect(onConfirm).not.toHaveBeenCalled();
  });
});
