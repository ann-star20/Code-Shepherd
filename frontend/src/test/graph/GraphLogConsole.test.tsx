import { render, screen } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { GraphLogConsole } from "@/components/GraphLogConsole";

describe("GraphLogConsole", () => {
  it("연결됨 상태에서 초록 pulse 인디케이터 표시", () => {
    // Arrange / Act
    render(<GraphLogConsole logs={[]} isConnected={true} />);
    // Assert
    expect(document.querySelector(".animate-pulse.bg-green-400")).toBeInTheDocument();
    expect(screen.queryByText("연결 끊김")).not.toBeInTheDocument();
  });

  it("연결 끊김 상태에서 오류 메시지 표시", () => {
    // Arrange / Act
    render(<GraphLogConsole logs={[]} isConnected={false} />);
    // Assert
    expect(screen.getByText("연결 끊김")).toBeInTheDocument();
  });

  it("logs 배열의 각 항목을 줄 단위로 렌더링", () => {
    // Arrange
    const logs = ["[2026-06-13] [Crawler] 크롤링 시작", "[2026-06-13] [Extractor] 추출 완료"];
    // Act
    render(<GraphLogConsole logs={logs} isConnected={true} />);
    // Assert
    expect(screen.getByText(logs[0])).toBeInTheDocument();
    expect(screen.getByText(logs[1])).toBeInTheDocument();
  });

  it("빈 logs일 때 오류 없이 렌더링", () => {
    // Arrange / Act
    render(<GraphLogConsole logs={[]} isConnected={false} />);
    // Assert
    expect(screen.getByText("Runtime Log")).toBeInTheDocument();
  });
});
