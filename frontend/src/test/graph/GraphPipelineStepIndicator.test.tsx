import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { GraphPipelineStepIndicator } from "@/components/GraphPipelineStepIndicator";
import type { StepStatuses } from "@/types/graphPipeline";

describe("GraphPipelineStepIndicator", () => {
  it("5개 단계 이름 모두 렌더링", () => {
    // Arrange
    const statuses: Partial<StepStatuses> = {};
    // Act
    render(<GraphPipelineStepIndicator statuses={statuses} />);
    // Assert
    expect(screen.getByText("Input")).toBeInTheDocument();
    expect(screen.getByText("Crawler")).toBeInTheDocument();
    expect(screen.getByText("Extractor")).toBeInTheDocument();
    expect(screen.getByText("Writer")).toBeInTheDocument();
    expect(screen.getByText("Resolver")).toBeInTheDocument();
  });

  it("RUNNING 단계 항목에 파란 하이라이트 배경 적용", () => {
    // Arrange
    const statuses: Partial<StepStatuses> = { Crawler: "RUNNING" };
    // Act
    render(<GraphPipelineStepIndicator statuses={statuses} />);
    // Assert
    const crawlerItem = screen.getByText("Crawler").closest("li");
    expect(crawlerItem).toHaveClass("bg-blue-50");
  });

  it("statuses 없는 단계는 PENDING으로 기본 표시", () => {
    // Arrange
    const statuses: Partial<StepStatuses> = { Input: "DONE" };
    // Act
    render(<GraphPipelineStepIndicator statuses={statuses} />);
    // Assert — Crawler has no status, should render PENDING dot (gray)
    const dots = document.querySelectorAll(".rounded-full");
    // Input dot should be green (DONE)
    expect(dots[0]).toHaveClass("bg-green-500");
    // Crawler dot should be gray (PENDING)
    expect(dots[1]).toHaveClass("bg-gray-300");
  });

  it("Resolver가 Writer보다 먼저 표시됨 (Resolver는 HITL 승인 전 Extract 단계에서 완료되고, Writer는 HITL 승인 후에만 실행됨)", () => {
    // Arrange
    const statuses: Partial<StepStatuses> = {};
    // Act
    render(<GraphPipelineStepIndicator statuses={statuses} />);
    // Assert
    const items = screen.getAllByRole("listitem");
    const labels = items.map((li) => li.querySelector("p")?.textContent);
    const resolverIndex = labels.indexOf("Resolver");
    const writerIndex = labels.indexOf("Writer");
    expect(resolverIndex).toBeGreaterThanOrEqual(0);
    expect(writerIndex).toBeGreaterThanOrEqual(0);
    expect(resolverIndex).toBeLessThan(writerIndex);
  });
});
