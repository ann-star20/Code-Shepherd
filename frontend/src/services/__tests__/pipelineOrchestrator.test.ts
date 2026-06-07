import { describe, it, expect, afterEach } from "vitest";
import MockAdapter from "axios-mock-adapter";
import { apiClient } from "@/services/api";
import {
  registerDocument,
  prescanDocument,
  triggerPipeline,
  runPipelineStart,
} from "@/services/pipelineOrchestrator";

const mock = new MockAdapter(apiClient);
afterEach(() => mock.reset());

// ── T_orch_01: registerDocument ───────────────────────────────────────────────
describe("registerDocument", () => {
  it("T_orch_01: returns doc_id from POST /documents", async () => {
    // Arrange
    mock.onPost("/documents", { urls: ["https://docs.djangoproject.com/"] }).reply(200, {
      documents: [{ doc_id: "EXT_django_abc" }],
    });

    // Act
    const docId = await registerDocument("https://docs.djangoproject.com/");

    // Assert
    expect(docId).toBe("EXT_django_abc");
  });
});

// ── T_orch_02: prescanDocument ────────────────────────────────────────────────
describe("prescanDocument", () => {
  it("T_orch_02: returns framework and infer_confidence from POST /documents/:id/prescan", async () => {
    // Arrange
    mock.onPost("/documents/EXT_django_abc/prescan").reply(200, {
      framework: "Django",
      infer_confidence: 0.92,
    });

    // Act
    const result = await prescanDocument("EXT_django_abc");

    // Assert
    expect(result.framework).toBe("Django");
    expect(result.infer_confidence).toBeCloseTo(0.92);
  });

  it("T_orch_02b: handles missing fields gracefully (undefined values)", async () => {
    // Arrange
    mock.onPost("/documents/EXT_unknown/prescan").reply(200, {});

    // Act
    const result = await prescanDocument("EXT_unknown");

    // Assert
    expect(result.framework).toBeUndefined();
    expect(result.infer_confidence).toBeUndefined();
  });
});

// ── T_orch_03: triggerPipeline ────────────────────────────────────────────────
describe("triggerPipeline", () => {
  it("T_orch_03: returns session_id from POST /pipeline/trigger", async () => {
    // Arrange
    mock.onPost("/pipeline/trigger", { doc_id: "EXT_django_abc" }).reply(202, {
      session_id: "ses-xyz-789",
    });

    // Act
    const sessionId = await triggerPipeline("EXT_django_abc");

    // Assert
    expect(sessionId).toBe("ses-xyz-789");
  });
});

// ── T_orch_04~07: runPipelineStart 오케스트레이션 ─────────────────────────────
describe("runPipelineStart", () => {
  it("T_orch_04: skips registerDocument when existingDocId is provided", async () => {
    // Arrange
    mock.onPost("/documents/EXISTING-DOC/prescan").reply(200, {
      framework: "Spring",
      infer_confidence: 0.85,
    });
    mock.onPost("/pipeline/trigger").reply(202, { session_id: "ses-001" });
    const logs: Array<[string, string]> = [];

    // Act
    const result = await runPipelineStart(
      ["https://spring.io/"],
      "EXISTING-DOC",
      { onLog: (type, msg) => logs.push([type, msg]) },
    );

    // Assert
    expect(result.docId).toBe("EXISTING-DOC");
    expect(result.sessionId).toBe("ses-001");
    expect(logs.some(([, m]) => m.includes("등록 완료"))).toBe(false);
  });

  it("T_orch_05: registers new document when existingDocId is null", async () => {
    // Arrange
    mock.onPost("/documents").reply(200, { documents: [{ doc_id: "NEW-DOC" }] });
    mock.onPost("/documents/NEW-DOC/prescan").reply(200, {
      framework: "FastAPI",
      infer_confidence: 0.77,
    });
    mock.onPost("/pipeline/trigger").reply(202, { session_id: "ses-002" });
    const logs: Array<[string, string]> = [];

    // Act
    const result = await runPipelineStart(
      ["https://fastapi.tiangolo.com/"],
      null,
      { onLog: (type, msg) => logs.push([type, msg]) },
    );

    // Assert
    expect(result.docId).toBe("NEW-DOC");
    expect(result.sessionId).toBe("ses-002");
    expect(logs.some(([, m]) => m.includes("NEW-DOC"))).toBe(true);
  });

  it("T_orch_06: emits logs in order INPUT(등록) → INPUT(prescan) → CRAWLER(trigger)", async () => {
    // Arrange
    mock.onPost("/documents").reply(200, { documents: [{ doc_id: "DOC-seq" }] });
    mock.onPost("/documents/DOC-seq/prescan").reply(200, {
      framework: "Django",
      infer_confidence: 0.9,
    });
    mock.onPost("/pipeline/trigger").reply(202, { session_id: "ses-003" });
    const logTypes: string[] = [];

    // Act
    await runPipelineStart(
      ["https://docs.djangoproject.com/"],
      null,
      { onLog: (type) => logTypes.push(type) },
    );

    // Assert — 3개 로그가 INPUT, INPUT, CRAWLER 순서
    expect(logTypes).toEqual(["INPUT", "INPUT", "CRAWLER"]);
  });

  it("T_orch_07: propagates error when trigger returns non-2xx", async () => {
    // Arrange
    mock.onPost("/documents").reply(200, { documents: [{ doc_id: "DOC-fail" }] });
    mock.onPost("/documents/DOC-fail/prescan").reply(200, { framework: "Django", infer_confidence: 0.8 });
    mock.onPost("/pipeline/trigger").reply(409, { detail: "이미 처리 중" });

    // Act + Assert
    await expect(
      runPipelineStart(["https://docs.djangoproject.com/"], null, { onLog: () => {} }),
    ).rejects.toThrow();
  });
});
