import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { GraphStatusDot } from "@/components/GraphStatusDot";

describe("GraphStatusDot", () => {
  it("PENDING 상태에서 회색 점 렌더링", () => {
    // Arrange
    // Act
    render(<GraphStatusDot status="PENDING" />);
    // Assert
    const dot = document.querySelector(".rounded-full");
    expect(dot).toHaveClass("bg-gray-300");
    expect(dot).not.toHaveClass("animate-pulse");
  });

  it("RUNNING 상태에서 파란 점과 animate-pulse 렌더링", () => {
    // Arrange
    // Act
    render(<GraphStatusDot status="RUNNING" />);
    // Assert
    const dot = document.querySelector(".rounded-full");
    expect(dot).toHaveClass("bg-blue-500");
    expect(dot).toHaveClass("animate-pulse");
  });

  it("DONE 상태에서 초록 점 렌더링", () => {
    // Arrange
    // Act
    render(<GraphStatusDot status="DONE" />);
    // Assert
    const dot = document.querySelector(".rounded-full");
    expect(dot).toHaveClass("bg-green-500");
  });

  it("FAILED 상태에서 빨간 점 렌더링", () => {
    // Arrange
    // Act
    render(<GraphStatusDot status="FAILED" />);
    // Assert
    const dot = document.querySelector(".rounded-full");
    expect(dot).toHaveClass("bg-red-500");
  });

  it("label prop이 있으면 아이콘 대신 label 텍스트 표시", () => {
    // Arrange
    const label = "진행중";
    // Act
    render(<GraphStatusDot status="RUNNING" label={label} />);
    // Assert
    expect(screen.getByText(label)).toBeInTheDocument();
  });
});
