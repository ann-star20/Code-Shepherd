import { renderHook, act } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { useGraphToast } from "@/hooks/useGraphToast";

describe("useGraphToast", () => {
  beforeEach(() => {
    vi.useFakeTimers();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("addToast 호출 시 toasts 배열에 항목 추가", () => {
    // Arrange
    const { result } = renderHook(() => useGraphToast());
    // Act
    act(() => {
      result.current.addToast("success", "작업 완료");
    });
    // Assert
    expect(result.current.toasts).toHaveLength(1);
    expect(result.current.toasts[0].kind).toBe("success");
    expect(result.current.toasts[0].message).toBe("작업 완료");
  });

  it("4초 후 자동으로 toast 제거", () => {
    // Arrange
    const { result } = renderHook(() => useGraphToast());
    act(() => {
      result.current.addToast("info", "일시 메시지");
    });
    expect(result.current.toasts).toHaveLength(1);
    // Act
    act(() => {
      vi.advanceTimersByTime(4000);
    });
    // Assert
    expect(result.current.toasts).toHaveLength(0);
  });

  it("dismiss 호출 시 해당 id toast 즉시 제거", () => {
    // Arrange
    const { result } = renderHook(() => useGraphToast());
    act(() => {
      result.current.addToast("error", "에러 발생");
    });
    const id = result.current.toasts[0].id;
    // Act
    act(() => {
      result.current.dismiss(id);
    });
    // Assert
    expect(result.current.toasts).toHaveLength(0);
  });

  it("여러 toast 추가 시 각각 독립적으로 관리", () => {
    // Arrange
    const { result } = renderHook(() => useGraphToast());
    // Act
    act(() => {
      result.current.addToast("success", "첫 번째");
      result.current.addToast("error", "두 번째");
    });
    // Assert
    expect(result.current.toasts).toHaveLength(2);
    expect(result.current.toasts[0].message).toBe("첫 번째");
    expect(result.current.toasts[1].message).toBe("두 번째");
  });
});
