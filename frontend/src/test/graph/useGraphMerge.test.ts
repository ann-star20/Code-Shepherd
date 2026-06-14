import { renderHook, act } from "@testing-library/react";
import { describe, it, expect } from "vitest";
import { useGraphMerge } from "@/hooks/useGraphMerge";
import type { GraphNode, StagingConcept } from "@/types/graphPipeline";

const baseConcept: GraphNode = {
  id: "concept-sql-injection",
  name: "SQL Injection",
  status: "COMMITTED",
  domains: ["security"],
};

function makeStagingConcept(overrides: Partial<StagingConcept>): StagingConcept {
  return {
    id: "concept-new-1",
    name: "New Concept",
    status: "DRAFT",
    domains: ["security"],
    staging_id: 1,
    state: "DRAFT",
    infer_action: "NEW",
    ...overrides,
  };
}

describe("useGraphMerge", () => {
  it("infer_action=NEW, state=DRAFT → DRAFT 점선 + 주황 NEW 링 노드 생성", () => {
    // Arrange
    const { result } = renderHook(() => useGraphMerge());
    const item = makeStagingConcept({ infer_action: "NEW", state: "DRAFT" });

    // Act
    act(() => {
      result.current.applyDraftNodes([item], [baseConcept]);
    });

    // Assert
    expect(result.current.draftNodes).toHaveLength(1);
    expect(result.current.draftNodes[0]).toMatchObject({
      id: "concept-new-1",
      status: "DRAFT",
      is_staging: true,
      is_new: true,
    });
  });

  it("infer_action=NEW, state=APPROVED → COMMITTED 실선 노드로 전환", () => {
    // Arrange
    const { result } = renderHook(() => useGraphMerge());
    const item = makeStagingConcept({ infer_action: "NEW", state: "APPROVED" });

    // Act
    act(() => {
      result.current.applyDraftNodes([item], [baseConcept]);
    });

    // Assert
    expect(result.current.draftNodes).toHaveLength(1);
    expect(result.current.draftNodes[0]).toMatchObject({
      id: "concept-new-1",
      status: "COMMITTED",
      is_staging: false,
      is_new: false,
    });
  });

  it("infer_action=MERGE, state=DRAFT → 대상 노드는 MERGE_PENDING 링, 병합 후보는 DRAFT 점선으로 표시", () => {
    // Arrange
    const { result } = renderHook(() => useGraphMerge());
    const item = makeStagingConcept({
      infer_action: "MERGE",
      state: "DRAFT",
      target_concept_name: "SQL Injection",
    });

    // Act
    act(() => {
      result.current.applyDraftNodes([item], [baseConcept]);
    });

    // Assert
    expect(result.current.draftNodes).toHaveLength(2);
    expect(result.current.draftNodes).toContainEqual(
      expect.objectContaining({ id: "concept-sql-injection", status: "MERGE_PENDING" })
    );
    expect(result.current.draftNodes).toContainEqual(
      expect.objectContaining({
        id: "concept-new-1",
        status: "DRAFT",
        is_staging: true,
        is_new: true,
      })
    );
    expect(result.current.draftEdges).toHaveLength(1);
    expect(result.current.draftEdges[0]).toMatchObject({
      source: "concept-new-1",
      target: "concept-sql-injection",
      type: "RELATED_TO",
    });
  });

  it("infer_action=MERGE, state=APPROVED → 노드 추가 없음(정상 상태로 복귀)", () => {
    // Arrange
    const { result } = renderHook(() => useGraphMerge());
    const item = makeStagingConcept({
      infer_action: "MERGE",
      state: "APPROVED",
      target_concept_name: "SQL Injection",
    });

    // Act
    act(() => {
      result.current.applyDraftNodes([item], [baseConcept]);
    });

    // Assert
    expect(result.current.draftNodes).toHaveLength(0);
  });

  it("infer_action=RELATED_TO, state=DRAFT → DRAFT 노드 + RELATED_TO 엣지 생성", () => {
    // Arrange
    const { result } = renderHook(() => useGraphMerge());
    const item = makeStagingConcept({
      infer_action: "RELATED_TO",
      state: "DRAFT",
      target_concept_name: "SQL Injection",
    });

    // Act
    act(() => {
      result.current.applyDraftNodes([item], [baseConcept]);
    });

    // Assert
    expect(result.current.draftNodes).toHaveLength(1);
    expect(result.current.draftNodes[0]).toMatchObject({
      id: "concept-new-1",
      status: "DRAFT",
      is_staging: true,
      is_new: true,
    });
    expect(result.current.draftEdges).toHaveLength(1);
    expect(result.current.draftEdges[0]).toMatchObject({
      source: "concept-new-1",
      target: "concept-sql-injection",
      type: "RELATED_TO",
    });
  });

  it("infer_action=RELATED_TO, state=APPROVED → COMMITTED 실선 노드로 실시간 전환", () => {
    // Arrange
    const { result } = renderHook(() => useGraphMerge());
    const item = makeStagingConcept({
      infer_action: "RELATED_TO",
      state: "APPROVED",
      target_concept_name: "SQL Injection",
    });

    // Act
    act(() => {
      result.current.applyDraftNodes([item], [baseConcept]);
    });

    // Assert
    expect(result.current.draftNodes[0]).toMatchObject({
      id: "concept-new-1",
      status: "COMMITTED",
      is_staging: false,
      is_new: false,
    });
  });

  it("state=REJECTED인 항목은 결과에서 완전히 제외", () => {
    // Arrange
    const { result } = renderHook(() => useGraphMerge());
    const item = makeStagingConcept({ infer_action: "NEW", state: "REJECTED" });

    // Act
    act(() => {
      result.current.applyDraftNodes([item], [baseConcept]);
    });

    // Assert
    expect(result.current.draftNodes).toHaveLength(0);
    expect(result.current.draftEdges).toHaveLength(0);
  });

  it("clearDraft 호출 시 draftNodes/draftEdges 초기화", () => {
    // Arrange
    const { result } = renderHook(() => useGraphMerge());
    const item = makeStagingConcept({ infer_action: "NEW", state: "DRAFT" });
    act(() => {
      result.current.applyDraftNodes([item], [baseConcept]);
    });
    expect(result.current.draftNodes).toHaveLength(1);

    // Act
    act(() => {
      result.current.clearDraft();
    });

    // Assert
    expect(result.current.draftNodes).toHaveLength(0);
    expect(result.current.draftEdges).toHaveLength(0);
  });
});
