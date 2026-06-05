import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { PipelineStepIndicator } from "@/components/molecules/PipelineStepIndicator";
import { MetadataForm } from "@/components/molecules/MetadataForm";
import { DiffSummaryCard } from "@/components/molecules/DiffSummaryCard";
import type { PipelineStep } from "@/types/pipeline";

const ALL_STEPS: PipelineStep[] = [
  { agent: "Input",     status: "DONE" },
  { agent: "Crawler",   status: "DONE" },
  { agent: "Extractor", status: "PENDING" },
  { agent: "Writer",    status: "PENDING" },
  { agent: "Resolver",  status: "PENDING" },
];

describe("PipelineStepIndicator", () => {
  it("T_F4_steps_render: all 5 agent names visible", () => {
    render(<PipelineStepIndicator steps={ALL_STEPS} />);
    for (const step of ALL_STEPS) {
      expect(screen.getByText(step.agent)).toBeTruthy();
    }
  });

  it("T_F4_running_highlighted: RUNNING step has highlight class", () => {
    const steps: PipelineStep[] = ALL_STEPS.map((s, i) =>
      i === 2 ? { ...s, status: "RUNNING" } : s
    );
    const { container } = render(<PipelineStepIndicator steps={steps} />);
    const highlighted = container.querySelector("[data-running='true']");
    expect(highlighted).toBeTruthy();
    expect(highlighted!.textContent).toContain("Extractor");
  });
});

describe("MetadataForm", () => {
  const noop = vi.fn();

  it("T_F4_meta_confidence_high: confidence >= 0.8 shows 자동 추론됨", () => {
    render(
      <MetadataForm
        urls={["https://example.com"]}
        prescanResult={{ framework: "Django", confidence: 0.9 }}
        confidence={0.9}
        onConfirm={noop}
        onAddUrl={noop}
        onRemoveUrl={noop}
      />
    );
    expect(screen.getByText(/자동 추론됨/)).toBeTruthy();
  });

  it("T_F4_meta_confidence_low: confidence < 0.8 shows 수동 입력 필요", () => {
    render(
      <MetadataForm
        urls={["https://example.com"]}
        confidence={0.2}
        onConfirm={noop}
        onAddUrl={noop}
        onRemoveUrl={noop}
      />
    );
    expect(screen.getByText(/수동 입력 필요/)).toBeTruthy();
  });

  it("T_F4_url_max_5: add button disabled when 5 URLs present", () => {
    const urls = Array.from({ length: 5 }, (_, i) => `https://example.com/${i}`);
    render(
      <MetadataForm
        urls={urls}
        onConfirm={noop}
        onAddUrl={noop}
        onRemoveUrl={noop}
      />
    );
    const addBtn = screen.getByRole("button", { name: /URL 추가|add/i });
    expect((addBtn as HTMLButtonElement).disabled).toBe(true);
  });
});

describe("DiffSummaryCard", () => {
  it("T_F4_diff_card: shows new, update, merge counts", () => {
    render(<DiffSummaryCard newCount={4} updateCount={2} mergeCount={1} />);
    expect(screen.getByText("4")).toBeTruthy();
    expect(screen.getByText("2")).toBeTruthy();
    expect(screen.getByText("1")).toBeTruthy();
  });
});
