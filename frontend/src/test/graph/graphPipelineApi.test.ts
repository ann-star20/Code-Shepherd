import { describe, it, expect } from "vitest";
import { graphPipelineApi } from "@/lib/graphPipelineApi";

describe("graphPipelineApi", () => {
  it("checkDuplicate — 중복 아닌 URL에서 is_duplicate=false 반환", async () => {
    // Arrange
    const url = "https://docs.example.com/guide";
    // Act
    const res = await graphPipelineApi.checkDuplicate(url);
    // Assert
    expect(res.data.is_duplicate).toBe(false);
  });

  it("triggerPipeline — session_id 포함 202 응답", async () => {
    // Arrange
    const docId = "doc-123";
    // Act
    const res = await graphPipelineApi.triggerPipeline(docId);
    // Assert
    expect(res.data.session_id).toBe("sess-123");
    expect(res.status).toBe(202);
  });

  it("getStaging — items 배열 반환", async () => {
    // Arrange
    const sessionId = "sess-123";
    // Act
    const res = await graphPipelineApi.getStaging(sessionId);
    // Assert
    expect(Array.isArray(res.data.items)).toBe(true);
  });

  it("getTopology — nodes와 edges 배열 반환", async () => {
    // Arrange
    // Act
    const res = await graphPipelineApi.getTopology();
    // Assert
    expect(Array.isArray(res.data.nodes)).toBe(true);
    expect(Array.isArray(res.data.edges)).toBe(true);
  });

  it("approveAll — 세션 전체 승인 성공", async () => {
    // Arrange
    const sessionId = "sess-123";
    // Act
    const res = await graphPipelineApi.approveAll(sessionId);
    // Assert
    expect(res.status).toBe(200);
  });
});
