import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MainPage } from "@/pages/MainPage";
import { DashboardLayout } from "@/components/templates/DashboardLayout";
import { pipelineService } from "@/services/pipelineService";
import { stagingService } from "@/services/stagingService";
import { graphService } from "@/services/graphService";
import { runPipelineStart } from "@/services/pipelineOrchestrator";
import type { GraphNode } from "@/types/graph";

vi.mock("react-force-graph-2d", () => ({
  default: ({
    graphData,
    onNodeClick,
  }: {
    graphData: { nodes: Array<{ id: string; name: string }> };
    onNodeClick: (n: unknown) => void;
  }) => (
    <div data-testid="force-graph">
      {graphData.nodes.map((n) => (
        <button key={n.id} data-testid={`node-btn-${n.id}`} onClick={() => onNodeClick(n)}>
          {n.name}
        </button>
      ))}
    </div>
  ),
}));

vi.mock("@/services/pipelineService", () => ({
  pipelineService: {
    prescan: vi.fn(),
    trigger: vi.fn(),
  },
}));
vi.mock("@/services/pipelineOrchestrator", () => ({
  runPipelineStart: vi.fn(),
}));
vi.mock("@/services/stagingService", () => ({
  stagingService: {
    getDraft: vi.fn(),
    getDiff: vi.fn(),
    approveAll: vi.fn(),
    rejectAll: vi.fn(),
    patchNode: vi.fn(),
  },
}));
vi.mock("@/services/graphService", () => ({
  graphService: { getTopology: vi.fn() },
}));

class MockEventSource {
  addEventListener = vi.fn();
  close = vi.fn();
  onerror: ((e: Event) => void) | null = null;
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.stubGlobal("EventSource", MockEventSource);
  vi.mocked(pipelineService.prescan).mockResolvedValue({
    confidence: 0.9,
    framework: "React",
    version: "18",
    lang: "TypeScript",
  });
  vi.mocked(pipelineService.trigger).mockResolvedValue({ session_id: "ses-1" });
  vi.mocked(stagingService.getDraft).mockResolvedValue([]);
  vi.mocked(stagingService.getDiff).mockResolvedValue({ draft: 0, approved: 0, committed: 0 });
  vi.mocked(graphService.getTopology).mockResolvedValue({ nodes: [], edges: [] });
  vi.mocked(runPipelineStart).mockResolvedValue({ docId: "doc-default", sessionId: "ses-default" });
});

describe("DashboardLayout", () => {
  it("T_F12_three_panels: renders all 3 panel slots", () => {
    render(
      <DashboardLayout
        sidebar={<div data-testid="s" />}
        main={<div data-testid="m" />}
        inspector={<div data-testid="i" />}
      />
    );
    expect(screen.getByTestId("s")).toBeTruthy();
    expect(screen.getByTestId("m")).toBeTruthy();
    expect(screen.getByTestId("i")).toBeTruthy();
  });
});

// ── T_F13: ConceptInspector 영향 컴포넌트·대응 메커니즘 표시 ──────────────────────
describe("ConceptInspector", () => {
  it("T_F13_components_on_mount: SQLi의 affected_components가 인스펙터에 표시된다", () => {
    // Arrange + Act
    render(<MainPage />);
    // Assert
    expect(screen.getByText("database_query_layer")).toBeTruthy();
    expect(screen.getByText("orm_layer")).toBeTruthy();
  });

  it("T_F13_mechanisms_on_mount: SQLi의 security_mechanism이 인스펙터에 표시된다", () => {
    // Arrange + Act
    render(<MainPage />);
    // Assert
    expect(screen.getByText(/parameterized_query/)).toBeTruthy();
    expect(screen.getByText(/input_type_validation/)).toBeTruthy();
  });

  it("T_F13_select_shows_components: XSS 클릭 시 해당 affected_components가 표시된다", async () => {
    // Arrange
    const user = userEvent.setup();
    render(<MainPage />);
    // Act – 인스펙터 목록의 XSS 버튼 클릭
    const allBtns = screen.getAllByRole("button");
    const xssBtn = allBtns.find(
      (b) => b.textContent?.includes("XSS") && b.textContent?.includes("CWE-79"),
    );
    expect(xssBtn).toBeDefined();
    await user.click(xssBtn!);
    // Assert – XSS의 affected_components 표시
    expect(screen.getByText("template_rendering_layer")).toBeTruthy();
    expect(screen.getByText("api_response_serialization")).toBeTruthy();
  });

  it("T_F13_api_merge_preserves_seed: 토폴로지 API 응답 후 시드 데이터의 affected_components 보존", async () => {
    // Arrange – fetch를 모킹하여 API가 SQLi 노드를 반환 (affected_components 없이)
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (typeof url === "string" && url.includes("/api/graph/topology")) {
        return Promise.resolve({
          ok: true,
          json: () =>
            Promise.resolve({
              nodes: [
                {
                  id: "SQLi", label: "Concept", name: "SQLi",
                  cwe_id: "CWE-89", severity: "critical", domains: ["security"],
                },
              ],
              edges: [],
            }),
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({ concept: "", langs: [], frameworks: [], examples: [] }),
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    render(<MainPage />);
    // Act – API 응답 대기
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    // Assert – 시드 데이터 병합으로 affected_components 보존
    await waitFor(
      () => { expect(screen.queryByText("database_query_layer")).toBeTruthy(); },
      { timeout: 2000 },
    );
  });
});

// ── T_F12: 기존 MainPage 테스트 ──────────────────────────────────────────────────
describe("MainPage", () => {
  it("T_F12_layout_renders: renders header and all 6 initial seed concepts", () => {
    render(<MainPage />);
    expect(screen.getByText("수집 에이전트 지식 그래프 실시간 웹뷰")).toBeTruthy();
    // INITIAL_CONCEPTS 6개 인스펙터 목록 + SVG 양쪽에 표시될 수 있어 getAllByText 사용
    expect(screen.getAllByText("SQLi").length).toBeGreaterThan(0);
    expect(screen.getAllByText("BrokenAccessControl").length).toBeGreaterThan(0);
    expect(screen.getAllByText("MissingIndex").length).toBeGreaterThan(0);
  });

  it("T_F12_trigger_flow: pipeline start emits Input Agent log (DEV simulation)", async () => {
    const user = userEvent.setup();
    render(<MainPage />);

    // 초기 URL 2개 존재 → 버튼 활성
    await user.click(
      screen.getByRole("button", { name: /에이전트 통합 크롤러 기동하기/ }),
    );

    // DEV 시뮬레이션: Input Agent 로그 즉시 생성
    expect(screen.getAllByText(/Input Agent/).length).toBeGreaterThan(0);
  });

  it("T_F12_no_mock_sim_when_pipeline_off: VITE_MOCK_PIPELINE=false 시 runPipelineStart(실 API)가 호출된다", async () => {
    // Arrange – VITE_MOCK_PIPELINE=false → DEV 시뮬 억제, PROD 경로 진입
    vi.stubEnv("VITE_MOCK_PIPELINE", "false");
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, json: () => Promise.resolve({}) });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<MainPage />);

    // Act
    await user.click(screen.getByRole("button", { name: /에이전트 통합 크롤러 기동하기/ }));

    // Assert – 실제 runPipelineStart 가 호출됨 (DEV 시뮬 return 없이 PROD 경로)
    await waitFor(() => expect(vi.mocked(runPipelineStart)).toHaveBeenCalled());
  });

  it("T_F12_concept_select: clicking concept list item updates inspector detail", async () => {
    const user = userEvent.setup();
    render(<MainPage />);

    // 초기 선택: SQLi → 상세 패널 헤더에 "(CWE-89)" 표시
    expect(screen.getByText("(CWE-89)")).toBeTruthy();

    // 인스펙터 목록에서 XSS 버튼 클릭
    const allButtons = screen.getAllByRole("button");
    const xssBtn = allButtons.find(
      (b) => b.textContent?.includes("XSS") && b.textContent?.includes("CWE-79"),
    );
    expect(xssBtn).toBeDefined();
    await user.click(xssBtn!);

    // 상세 패널이 XSS로 업데이트 → "(CWE-79)" 표시
    expect(screen.getByText("(CWE-79)")).toBeTruthy();
  });
});

// ── T_F14: Extractor 스피너 + PROD 실제 staging 데이터 표시 ──────────────────
// llm_response.json 응답값 기반 mock (Gemini 실비용 방지)
describe("ExtractorSpinner", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("T_F14_extractor_spinner_shows: Extractor 로그 감지 시 step-3에 스피너가 나타난다", async () => {
    // Arrange
    vi.stubEnv("VITE_MOCK_PIPELINE", "false");
    vi.mocked(runPipelineStart).mockResolvedValue({ docId: "doc-t14a", sessionId: "ses-t14a" });

    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (typeof url === "string" && url.includes("/api/pipeline/logs/ses-t14a")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({
            doc_state: "CRAWLING",
            logs: [
              { ts: "2026-06-08T10:00:00.000", agent: "Extractor", level: "INFO", message: "Gemini 추출 시작" },
            ],
          }),
        });
      }
      if (typeof url === "string" && url.includes("/api/graph/topology")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ nodes: [], edges: [] }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ concept: "", langs: [], frameworks: [], examples: [] }) });
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<MainPage />);

    // Act – 파이프라인 시작
    await user.click(screen.getByRole("button", { name: /에이전트 통합 크롤러 기동하기/ }));

    // Assert – "LLM 응답 대기 중..." 텍스트가 step-3에 나타남
    await waitFor(
      () => { expect(screen.getByText("LLM 응답 대기 중...")).toBeTruthy(); },
      { timeout: 5000 },
    );
  });

  it("T_F14_extractor_spinner_hides: EXTRACTED 상태 도달 시 스피너가 사라진다", async () => {
    // Arrange
    vi.stubEnv("VITE_MOCK_PIPELINE", "false");
    vi.mocked(runPipelineStart).mockResolvedValue({ docId: "doc-t14b", sessionId: "ses-t14b" });

    let callCount = 0;
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (typeof url === "string" && url.includes("/api/pipeline/logs/ses-t14b")) {
        callCount++;
        // 첫 번째 폴링: Extractor 실행 중
        if (callCount === 1) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
              doc_state: "CRAWLING",
              logs: [{ ts: "2026-06-08T10:00:00.000", agent: "Extractor", level: "INFO", message: "추출 중" }],
            }),
          });
        }
        // 두 번째 폴링: EXTRACTED 완료
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ doc_state: "EXTRACTED", logs: [] }),
        });
      }
      if (typeof url === "string" && url.includes("/api/staging/ses-t14b")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ items: [] }),
        });
      }
      if (typeof url === "string" && url.includes("/api/graph/topology")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ nodes: [], edges: [] }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ concept: "", langs: [], frameworks: [], examples: [] }) });
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<MainPage />);

    await user.click(screen.getByRole("button", { name: /에이전트 통합 크롤러 기동하기/ }));

    // Assert – EXTRACTED 후 스피너 메시지 사라짐
    await waitFor(
      () => { expect(screen.queryByText("LLM 응답 대기 중...")).toBeNull(); },
      { timeout: 8000 },
    );
  });

  it("T_F14_draft_from_staging: EXTRACTED 후 llm_response.json 기반 DRAFT 개념이 스테이징에 표시된다", async () => {
    // Arrange – llm_response.json 실제 Gemini 응답값 기반 mock staging data
    const stagingItems = [
      {
        id: "st-csrf-1", state: "DRAFT",
        concept_name: "CrossSiteRequestForgery",
        concept_type: "vulnerability_root_cause",
        cwe_id: "CWE-352", owasp_id: "A04:2021", severity: "high",
        domains: ["security"], aliases: ["CSRF", "XSRF"],
        affected_components: ["web_application", "http_request_handler", "user_session"],
        security_mechanism: ["csrf_cookie", "csrf_middleware_token_field"],
        description_ko: "악의적인 웹사이트가 로그인한 사용자의 자격 증명을 이용하여 특정 동작을 수행하도록 유도하는 공격입니다.",
      },
    ];

    vi.stubEnv("VITE_MOCK_PIPELINE", "false");
    vi.mocked(runPipelineStart).mockResolvedValue({ docId: "doc-t14c", sessionId: "ses-t14c" });

    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (typeof url === "string" && url.includes("/api/pipeline/logs/ses-t14c")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ doc_state: "EXTRACTED", logs: [] }),
        });
      }
      if (typeof url === "string" && url.includes("/api/staging/ses-t14c")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ items: stagingItems }),
        });
      }
      if (typeof url === "string" && url.includes("/api/graph/topology")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ nodes: [], edges: [] }) });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve({ concept: "", langs: [], frameworks: [], examples: [] }) });
    });
    vi.stubGlobal("fetch", fetchMock);

    const user = userEvent.setup();
    render(<MainPage />);
    await user.click(screen.getByRole("button", { name: /에이전트 통합 크롤러 기동하기/ }));

    // Assert – 스테이징 완료 안내 메시지 + DRAFT 승인 대기
    await waitFor(
      () => { expect(screen.getByText(/스테이징 적재 완료/)).toBeTruthy(); },
      { timeout: 6000 },
    );
  });
});
