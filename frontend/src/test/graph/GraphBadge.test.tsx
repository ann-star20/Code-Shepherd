import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { DomainBadge, ActionBadge } from "@/components/GraphBadge";

describe("DomainBadge", () => {
  it("security 도메인에 teal 배지 클래스 적용", () => {
    // Arrange / Act
    render(<DomainBadge domain="security" />);
    // Assert
    const badge = screen.getByText("security");
    expect(badge).toHaveClass("bg-teal-100", "text-teal-800");
  });

  it("performance 도메인에 orange 배지 클래스 적용", () => {
    // Arrange / Act
    render(<DomainBadge domain="performance" />);
    // Assert
    const badge = screen.getByText("performance");
    expect(badge).toHaveClass("bg-orange-100", "text-orange-800");
  });

  it("md 사이즈에서 더 큰 패딩 클래스 적용", () => {
    // Arrange / Act
    render(<DomainBadge domain="both" size="md" />);
    // Assert
    const badge = screen.getByText("both");
    expect(badge).toHaveClass("px-2.5", "py-1");
  });
});

describe("ActionBadge", () => {
  it("NEW 액션에서 신뢰도 퍼센트 표시", () => {
    // Arrange / Act
    render(<ActionBadge action="NEW" confidence={0.923} />);
    // Assert
    expect(screen.getByText("NEW (92.3%)")).toBeInTheDocument();
  });

  it("MERGE 액션에서 타겟 개념명 표시", () => {
    // Arrange / Act
    render(<ActionBadge action="MERGE" target="SQL Injection" />);
    // Assert
    expect(screen.getByText("MERGE → SQL Injection")).toBeInTheDocument();
  });

  it("RELATED_TO 액션에서 관련 개념명 표시", () => {
    // Arrange / Act
    render(<ActionBadge action="RELATED_TO" target="XSS" />);
    // Assert
    expect(screen.getByText("RELATED_TO XSS")).toBeInTheDocument();
  });
});
