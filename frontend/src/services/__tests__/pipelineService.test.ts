import { describe, it, expect, afterEach } from "vitest";
import MockAdapter from "axios-mock-adapter";
import { apiClient } from "@/services/api";
import { pipelineService } from "@/services/pipelineService";
import { stagingService } from "@/services/stagingService";
import { graphService } from "@/services/graphService";

const mock = new MockAdapter(apiClient);

afterEach(() => mock.reset());

describe("pipelineService", () => {
  it("T_F3_trigger_ok", async () => {
    mock.onPost("/pipeline/trigger").reply(200, { session_id: "abc" });
    const res = await pipelineService.trigger({ urls: ["https://example.com"], metadata: {} });
    expect(res.session_id).toBe("abc");
  });

  it("T_F3_prescan_ok", async () => {
    mock.onGet("/pipeline/prescan").reply(200, { framework: "Django", confidence: 0.9 });
    const res = await pipelineService.prescan("https://docs.djangoproject.com");
    expect(res.framework).toBe("Django");
  });
});

describe("stagingService", () => {
  it("T_F3_get_draft", async () => {
    mock.onGet("/staging/sid123").reply(200, { items: [{ id: "1", state: "DRAFT" }] });
    const items = await stagingService.getDraft("sid123");
    expect(items).toHaveLength(1);
    expect(items[0].state).toBe("DRAFT");
  });

  it("T_F3_approve_all", async () => {
    mock.onPost("/staging/sid123/approve").reply(200, { approved: 3 });
    const res = await stagingService.approveAll("sid123");
    expect(res.approved).toBe(3);
  });
});

describe("graphService", () => {
  it("T_F3_topology", async () => {
    mock.onGet("/graph/topology").reply(200, { nodes: [{ id: "1" }], edges: [] });
    const res = await graphService.getTopology();
    expect(Array.isArray(res.nodes)).toBe(true);
  });
});
