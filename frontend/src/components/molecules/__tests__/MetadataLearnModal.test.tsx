import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MetadataLearnModal } from "@/components/molecules/MetadataLearnModal";
import type { PrescanResult } from "@/services/pipelineOrchestrator";

const BASE_PRESCAN: PrescanResult = {
  doc_id: "DOC-unknown",
  original_url: "https://docs.astro.build/en/getting-started/",
  framework: undefined,
  infer_confidence: 0.0,
  infer_status: "manual_required",
  suggested_frameworks: ["Django", "FastAPI"],
};

describe("MetadataLearnModal", () => {
  it("T_meta_modal_01: shows suggested frameworks and the '목록에 없음' option in the dropdown", () => {
    render(<MetadataLearnModal prescanResult={BASE_PRESCAN} onSubmit={vi.fn()} onCancel={vi.fn()} />);

    const select = screen.getByLabelText("프레임워크") as HTMLSelectElement;
    const optionLabels = Array.from(select.options).map((o) => o.textContent);

    expect(optionLabels).toEqual(["Django", "FastAPI", "[목록에 없음 (직접 입력 활성화)]"]);
    expect(select.value).toBe("Django");
  });

  it("T_meta_modal_02: selecting '목록에 없음' reveals the custom framework input", async () => {
    const user = userEvent.setup();
    render(<MetadataLearnModal prescanResult={BASE_PRESCAN} onSubmit={vi.fn()} onCancel={vi.fn()} />);

    expect(screen.queryByLabelText("신규 프레임워크명")).not.toBeInTheDocument();

    await user.selectOptions(screen.getByLabelText("프레임워크"), "[목록에 없음 (직접 입력 활성화)]");

    expect(screen.getByLabelText("신규 프레임워크명")).toBeInTheDocument();
  });

  it("T_meta_modal_03: submit button is disabled until pattern and supported languages are filled", async () => {
    const user = userEvent.setup();
    render(<MetadataLearnModal prescanResult={BASE_PRESCAN} onSubmit={vi.fn()} onCancel={vi.fn()} />);

    const submitBtn = screen.getByRole("button", { name: "학습 및 계속" });
    expect(submitBtn).toBeDisabled();

    await user.type(screen.getByLabelText("URL 패턴 (정규식)"), "docs\\.astro\\.build");
    expect(submitBtn).toBeDisabled();

    await user.type(screen.getByLabelText("지원 언어 (쉼표 구분)"), "TypeScript");
    expect(submitBtn).toBeEnabled();
  });

  it("T_meta_modal_04: submits selected framework with pattern and parsed langs", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<MetadataLearnModal prescanResult={BASE_PRESCAN} onSubmit={onSubmit} onCancel={vi.fn()} />);

    await user.selectOptions(screen.getByLabelText("프레임워크"), "FastAPI");
    await user.type(screen.getByLabelText("URL 패턴 (정규식)"), "fastapi\\.tiangolo\\.com");
    await user.type(screen.getByLabelText("지원 언어 (쉼표 구분)"), "Python, TypeScript");
    await user.click(screen.getByRole("button", { name: "학습 및 계속" }));

    expect(onSubmit).toHaveBeenCalledWith({
      framework: "FastAPI",
      pattern: "fastapi\\.tiangolo\\.com",
      supported_langs: ["Python", "TypeScript"],
      default_lang: undefined,
    });
  });

  it("T_meta_modal_05: submits a custom framework name when '목록에 없음' is selected", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<MetadataLearnModal prescanResult={BASE_PRESCAN} onSubmit={onSubmit} onCancel={vi.fn()} />);

    await user.selectOptions(screen.getByLabelText("프레임워크"), "[목록에 없음 (직접 입력 활성화)]");
    await user.type(screen.getByLabelText("신규 프레임워크명"), "Astro");
    await user.type(screen.getByLabelText("URL 패턴 (정규식)"), "docs\\.astro\\.build");
    await user.type(screen.getByLabelText("지원 언어 (쉼표 구분)"), "TypeScript");
    await user.click(screen.getByRole("button", { name: "학습 및 계속" }));

    expect(onSubmit).toHaveBeenCalledWith({
      framework: "Astro",
      pattern: "docs\\.astro\\.build",
      supported_langs: ["TypeScript"],
      default_lang: undefined,
    });
  });

  it("T_meta_modal_06: clicking 취소 calls onCancel", async () => {
    const user = userEvent.setup();
    const onCancel = vi.fn();
    render(<MetadataLearnModal prescanResult={BASE_PRESCAN} onSubmit={vi.fn()} onCancel={onCancel} />);

    await user.click(screen.getByRole("button", { name: "취소" }));

    expect(onCancel).toHaveBeenCalled();
  });
});
