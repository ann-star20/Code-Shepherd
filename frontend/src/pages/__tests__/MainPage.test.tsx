import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MainPage } from "@/pages/MainPage";
import { PipelineStepList, ToastContainer } from "@/pages/MainPage";
import type { StepStatuses, ToastItem } from "@/pages/MainPage";
import { DashboardLayout } from "@/components/templates/DashboardLayout";
import { pipelineService } from "@/services/pipelineService";
import { stagingService } from "@/services/stagingService";
import { graphService } from "@/services/graphService";
import { runPipelineStart, checkDuplicateDocument } from "@/services/pipelineOrchestrator";

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
  checkDuplicateDocument: vi.fn(),
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
  vi.mocked(checkDuplicateDocument).mockResolvedValue({
    is_duplicate: false, doc_id: "doc-default", original_url: "", etag: null,
  });
});

// ── DashboardLayout ───────────────────────────────────────────────────────────
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

// ── T_F13: ConceptInspector ───────────────────────────────────────────────────
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
    // Act
    const allBtns = screen.getAllByRole("button");
    const xssBtn = allBtns.find(
      (b) => b.textContent?.includes("XSS") && b.textContent?.includes("CWE-79"),
    );
    expect(xssBtn).toBeDefined();
    await user.click(xssBtn!);
    // Assert
    expect(screen.getByText("template_rendering_layer")).toBeTruthy();
    expect(screen.getByText("api_response_serialization")).toBeTruthy();
  });

  it("T_F13_api_merge_preserves_seed: 토폴로지 API 응답 후 시드 데이터의 affected_components 보존", async () => {
    // Arrange
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
    // Act
    await waitFor(() => expect(fetchMock).toHaveBeenCalled());
    // Assert
    await waitFor(
      () => { expect(screen.queryByText("database_query_layer")).toBeTruthy(); },
      { timeout: 2000 },
    );
  });
});

// ── T_F12: 기존 MainPage 테스트 ──────────────────────────────────────────────
describe("MainPage", () => {
  it("T_F12_layout_renders: renders header and all 6 initial seed concepts", () => {
    render(<MainPage />);
    expect(screen.getByText("수집 에이전트 지식 그래프 실시간 웹뷰")).toBeTruthy();
    expect(screen.getAllByText("SQLi").length).toBeGreaterThan(0);
    expect(screen.getAllByText("BrokenAccessControl").length).toBeGreaterThan(0);
    expect(screen.getAllByText("MissingIndex").length).toBeGreaterThan(0);
  });

  it("T_F12_trigger_flow: pipeline start emits Input Agent log (DEV simulation)", async () => {
    const user = userEvent.setup();
    render(<MainPage />);
    await user.click(
      screen.getByRole("button", { name: /에이전트 통합 크롤러 기동하기/ }),
    );
    expect(screen.getAllByText(/Input Agent/).length).toBeGreaterThan(0);
  });

  it("T_F12_no_mock_sim_when_pipeline_off: VITE_MOCK_PIPELINE=false 시 runPipelineStart(실 API)가 호출된다", async () => {
    // Arrange
    vi.stubEnv("VITE_MOCK_PIPELINE", "false");
    const fetchMock = vi.fn().mockResolvedValue({ ok: false, json: () => Promise.resolve({}) });
    vi.stubGlobal("fetch", fetchMock);
    const user = userEvent.setup();
    render(<MainPage />);
    // Act
    await user.click(screen.getByRole("button", { name: /에이전트 통합 크롤러 기동하기/ }));
    // Assert
    await waitFor(() => expect(vi.mocked(runPipelineStart)).toHaveBeenCalled());
  });

  it("T_F12_concept_select: clicking concept list item updates inspector detail", async () => {
    const user = userEvent.setup();
    render(<MainPage />);
    expect(screen.getByText("(CWE-89)")).toBeTruthy();
    const allButtons = screen.getAllByRole("button");
    const xssBtn = allButtons.find(
      (b) => b.textContent?.includes("XSS") && b.textContent?.includes("CWE-79"),
    );
    expect(xssBtn).toBeDefined();
    await user.click(xssBtn!);
    expect(screen.getByText("(CWE-79)")).toBeTruthy();
  });
});

// ── T12: PipelineStepList 단계별 StepStatus 렌더링 (단위 테스트) ──────────────
const IDLE_STATUSES: StepStatuses = { 1: "IDLE", 2: "IDLE", 3: "IDLE", 4: "IDLE", 5: "IDLE" };

describe("T12 PipelineStepList — 단계별 상태 전이 렌더링", () => {
  it("T12_Assert1: LOADING 상태에서 step에 animate-spin 스피너가 존재한다", () => {
    // Arrange
    const statuses: StepStatuses = { ...IDLE_STATUSES, 3: "LOADING" };
    // Act
    render(<PipelineStepList statuses={statuses} />);
    const step3 = document.querySelector('[data-testid="step-3"]')!;
    // Assert
    const spinner = step3.querySelector('[data-testid="spinner"]');
    expect(spinner).toBeTruthy();
    expect(spinner!.className).toContain("animate-spin");
  });

  it("T12_Assert2: SUCCESS 전이 시 스피너 소거 + ✓ 체크가 렌더링된다", () => {
    // Arrange
    const statuses: StepStatuses = { ...IDLE_STATUSES, 2: "SUCCESS" };
    // Act
    render(<PipelineStepList statuses={statuses} />);
    const step2 = document.querySelector('[data-testid="step-2"]')!;
    // Assert — spinner 없음
    expect(step2.querySelector('[data-testid="spinner"]')).toBeNull();
    // Assert — check mark
    const check = step2.querySelector('[data-testid="check"]');
    expect(check).toBeTruthy();
    expect(check!.textContent).toBe("✓");
  });

  it("T12_Assert3: LOADING 상태에서 해당 단계 subText(Gemini)가 정확히 출력된다", () => {
    // Arrange
    const statuses: StepStatuses = { ...IDLE_STATUSES, 3: "LOADING" };
    // Act
    render(<PipelineStepList statuses={statuses} />);
    // Assert
    expect(screen.getByText(/Gemini 2\.5 Flash 가동 중/)).toBeTruthy();
  });

  it("T12_Assert4: FAILED 상태에서 ✗ 아이콘이 렌더링된다", () => {
    // Arrange
    const statuses: StepStatuses = { ...IDLE_STATUSES, 1: "FAILED" };
    // Act
    render(<PipelineStepList statuses={statuses} />);
    const step1 = document.querySelector('[data-testid="step-1"]')!;
    // Assert
    const xMark = step1.querySelector('[data-testid="x-mark"]');
    expect(xMark).toBeTruthy();
    expect(xMark!.textContent).toBe("✗");
  });

  it("T12_Assert5: IDLE 상태에서 idle-dot만 존재하고 spinner/check 없다", () => {
    // Arrange + Act
    render(<PipelineStepList statuses={IDLE_STATUSES} />);
    const step4 = document.querySelector('[data-testid="step-4"]')!;
    // Assert
    expect(step4.querySelector('[data-testid="idle-dot"]')).toBeTruthy();
    expect(step4.querySelector('[data-testid="spinner"]')).toBeNull();
    expect(step4.querySelector('[data-testid="check"]')).toBeNull();
  });
});

// ── T13: ToastContainer 렌더링 및 해제 ───────────────────────────────────────
describe("T13 ToastContainer — 알림 렌더링 및 해제", () => {
  it("T13_Assert1: 토스트 메시지가 화면에 렌더링된다", () => {
    // Arrange
    const toasts: ToastItem[] = [
      { id: "toast-1", kind: "success", message: "10개 핵심 기술 개념 도출 완료" },
    ];
    // Act
    render(<ToastContainer toasts={toasts} onDismiss={() => {}} />);
    // Assert
    expect(screen.getByText("10개 핵심 기술 개념 도출 완료")).toBeTruthy();
  });

  it("T13_Assert2: success 토스트에 ✓ 아이콘이 표시된다", () => {
    // Arrange
    const toasts: ToastItem[] = [{ id: "t1", kind: "success", message: "완료" }];
    // Act
    render(<ToastContainer toasts={toasts} onDismiss={() => {}} />);
    const toast = document.querySelector('[data-testid="toast"]')!;
    // Assert
    expect(toast.textContent).toContain("✓");
  });

  it("T13_Assert3: error 토스트에 ✗ 아이콘이 표시된다", () => {
    // Arrange
    const toasts: ToastItem[] = [{ id: "t2", kind: "error", message: "오류 발생" }];
    // Act
    render(<ToastContainer toasts={toasts} onDismiss={() => {}} />);
    const toast = document.querySelector('[data-testid="toast"]')!;
    // Assert
    expect(toast.textContent).toContain("✗");
  });

  it("T13_Assert4: × 버튼 클릭 시 onDismiss가 해당 id로 호출된다", async () => {
    // Arrange
    const mockDismiss = vi.fn();
    const toasts: ToastItem[] = [{ id: "toast-99", kind: "info", message: "알림" }];
    const user = userEvent.setup();
    // Act
    render(<ToastContainer toasts={toasts} onDismiss={mockDismiss} />);
    await user.click(document.querySelector('[data-testid="toast-dismiss"]')!);
    // Assert
    expect(mockDismiss).toHaveBeenCalledWith("toast-99");
  });

  it("T13_Assert5: 토스트가 없으면 아무것도 렌더링되지 않는다", () => {
    // Arrange + Act
    render(<ToastContainer toasts={[]} onDismiss={() => {}} />);
    // Assert
    expect(document.querySelectorAll('[data-testid="toast"]').length).toBe(0);
  });
});

// ── T14: Extractor 스피너 + PROD staging 데이터 통합 ─────────────────────────
describe("T14 ExtractorSpinner — 통합 폴링 테스트", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
  });

  it("T14_extractor_spinner_shows: Extractor 로그 감지 시 '응답 대기 중...' 배지가 나타난다", async () => {
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
    // Act
    await user.click(screen.getByRole("button", { name: /에이전트 통합 크롤러 기동하기/ }));
    // Assert — 구현에서 "응답 대기 중..." 배지 (구: "LLM 응답 대기 중...")
    await waitFor(
      () => { expect(screen.getByText("응답 대기 중...")).toBeTruthy(); },
      { timeout: 5000 },
    );
  });

  it("T14_extractor_spinner_hides: EXTRACTED 상태 도달 시 '응답 대기 중...' 배지가 사라진다", async () => {
    // Arrange
    vi.stubEnv("VITE_MOCK_PIPELINE", "false");
    vi.mocked(runPipelineStart).mockResolvedValue({ docId: "doc-t14b", sessionId: "ses-t14b" });
    let callCount = 0;
    const fetchMock = vi.fn().mockImplementation((url: string) => {
      if (typeof url === "string" && url.includes("/api/pipeline/logs/ses-t14b")) {
        callCount++;
        if (callCount === 1) {
          return Promise.resolve({
            ok: true,
            json: () => Promise.resolve({
              doc_state: "CRAWLING",
              logs: [{ ts: "2026-06-08T10:00:00.000", agent: "Extractor", level: "INFO", message: "추출 중" }],
            }),
          });
        }
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ doc_state: "EXTRACTED", logs: [] }),
        });
      }
      if (typeof url === "string" && url.includes("/api/staging/ses-t14b")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: [] }) });
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
    // Assert — EXTRACTED 후 "응답 대기 중..." 배지 소거
    await waitFor(
      () => { expect(screen.queryByText("응답 대기 중...")).toBeNull(); },
      { timeout: 8000 },
    );
  });

  it("T14_draft_from_staging: EXTRACTED 후 DRAFT 개념이 스테이징에 표시된다", async () => {
    // Arrange
    const stagingItems = [
      {
        id: "st-csrf-1", state: "DRAFT",
        concept_name: "CrossSiteRequestForgery",
        concept_type: "vulnerability_root_cause",
        cwe_id: "CWE-352", owasp_id: "A04:2021", severity: "high",
        domains: ["security"], aliases: ["CSRF", "XSRF"],
        affected_components: ["web_application", "http_request_handler"],
        security_mechanism: ["csrf_cookie", "csrf_middleware_token_field"],
        description_ko: "악의적인 웹사이트가 로그인한 사용자의 자격 증명을 이용하는 공격.",
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
        return Promise.resolve({ ok: true, json: () => Promise.resolve({ items: stagingItems }) });
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
    // Assert
    await waitFor(
      () => { expect(screen.getByText(/스테이징 적재 완료/)).toBeTruthy(); },
      { timeout: 6000 },
    );
  });
});

// ── flow-ui-V4 §1: ETag 중복 문서 안내 모달 ───────────────────────────────────
describe("flow-ui-V4 §1 — 중복 문서 안내 모달", () => {
  it("중복 문서 감지 시 안내 모달이 표시되고 URL 대기열에는 추가되지 않는다", async () => {
    // Arrange
    const dupUrl = "https://docs.python.org/3/library/secrets.html";
    vi.mocked(checkDuplicateDocument).mockResolvedValue({
      is_duplicate: true, doc_id: "EXT_dup_00000000", original_url: dupUrl, etag: "abc123",
    });
    const user = userEvent.setup();
    render(<MainPage />);
    // Act
    await user.type(screen.getByPlaceholderText("공식 가이드 및 보안 URL을 입력하세요..."), dupUrl);
    await user.click(screen.getByRole("button", { name: "추가" }));
    // Assert
    const dialog = await screen.findByRole("dialog", { name: "중복 문서 안내" });
    expect(dialog.textContent).toContain("는 이미 지식화된 문서입니다.");
    expect(dialog.textContent).toContain(dupUrl);
    expect(screen.queryByText(dupUrl, { selector: "span.font-mono.text-stone-700" })).toBeNull();
  });

  it("중복 안내 모달에서 '확인' 클릭 시 모달이 닫힌다", async () => {
    // Arrange
    const dupUrl = "https://docs.python.org/3/library/secrets.html";
    vi.mocked(checkDuplicateDocument).mockResolvedValue({
      is_duplicate: true, doc_id: "EXT_dup_00000000", original_url: dupUrl, etag: "abc123",
    });
    const user = userEvent.setup();
    render(<MainPage />);
    await user.type(screen.getByPlaceholderText("공식 가이드 및 보안 URL을 입력하세요..."), dupUrl);
    await user.click(screen.getByRole("button", { name: "추가" }));
    await screen.findByRole("dialog", { name: "중복 문서 안내" });
    // Act
    await user.click(screen.getByRole("button", { name: "확인" }));
    // Assert
    expect(screen.queryByRole("dialog", { name: "중복 문서 안내" })).toBeNull();
  });
});

// ── T15: Debug Drawer 열기/닫기 ───────────────────────────────────────────────
describe("T15 DebugDrawer — 터미널 로그 드로어", () => {
  it("T15_Assert1: '▸ Logs' 버튼 클릭 시 드로어 dialog가 열린다", async () => {
    // Arrange
    const user = userEvent.setup();
    render(<MainPage />);
    // Act
    await user.click(screen.getByRole("button", { name: /Logs/ }));
    // Assert
    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByText("TERMINAL RAW LOGS")).toBeTruthy();
  });

  it("T15_Assert2: 드로어 × 버튼 클릭 시 dialog가 닫힌다", async () => {
    // Arrange
    const user = userEvent.setup();
    render(<MainPage />);
    await user.click(screen.getByRole("button", { name: /Logs/ }));
    expect(screen.getByRole("dialog")).toBeTruthy();
    // Act
    await user.click(screen.getByLabelText("close-drawer"));
    // Assert
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("T15_Assert3: 드로어 오버레이 클릭 시 닫힌다", async () => {
    // Arrange
    const user = userEvent.setup();
    render(<MainPage />);
    await user.click(screen.getByRole("button", { name: /Logs/ }));
    // Act
    await user.click(screen.getByTestId("drawer-overlay"));
    // Assert
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
