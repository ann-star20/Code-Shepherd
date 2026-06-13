import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, it, expect, vi } from "vitest";
import { GraphDomainSelect } from "@/components/GraphDomainSelect";

describe("GraphDomainSelect", () => {
  it("전체/security/performance/both 옵션을 렌더링", () => {
    // Arrange / Act
    render(<GraphDomainSelect value="all" onChange={vi.fn()} />);

    // Assert
    expect(screen.getByRole("option", { name: "전체" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "security" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "performance" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "both" })).toBeInTheDocument();
  });

  it("값을 변경하면 onChange가 새 도메인으로 호출됨", async () => {
    // Arrange
    const onChange = vi.fn();
    render(<GraphDomainSelect value="all" onChange={onChange} />);

    // Act
    await userEvent.selectOptions(screen.getByRole("combobox"), "security");

    // Assert
    expect(onChange).toHaveBeenCalledWith("security");
  });
});
