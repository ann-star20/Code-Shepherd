/**
 * HitlQueue — KB Evolution UI TDD
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { HitlQueueItem, HitlQueuePageResponse } from "../types/kms";

// vi.mock은 호이스팅됨 — vi.fn()으로 선언 후 beforeEach에서 값 주입
vi.mock("../api/hitlApi", () => ({
  listHitlQueue:     vi.fn(),
  suggestCategory:   vi.fn(),
  applyCategory:     vi.fn(),
  approveHitl:       vi.fn(),
  rejectHitl:        vi.fn(),
  reprocessHitl:     vi.fn(),
  getHitlMarkdown:   vi.fn(),
}));

// vi.mock 이후 import — mocked 버전을 가져옴
import * as hitlApi from "../api/hitlApi";
import { HitlQueue } from "./HitlQueue";

// ── 픽스처 ──────────────────────────────────────────────────────────────────

function makeKbItem(overrides: Partial<HitlQueueItem> = {}): HitlQueueItem {
  return {
    queue_id: "kb-queue-001",
    doc_id:   "doc-001",
    stage:    "stage5b_metadata_validate",
    reason:   "새 카테고리 감지",
    quality_score: null,
    issues: {
      issues: ["새 카테고리 제안: 'NCS교육'"],
      category_reasoning: "NCS 기반 교육 자료입니다.",
      category_alternatives: ["아키텍처", "온보딩"],
    },
    status:      "pending",
    reviewer_id: null,
    review_note: null,
    created_at:  "2026-06-03T10:00:00",
    ...overrides,
  };
}

function makeNormalItem(): HitlQueueItem {
  return {
    queue_id: "normal-queue-001",
    doc_id:   "doc-002",
    stage:    "stage2_validate",
    reason:   "품질 점수 미달",
    quality_score: 0.65,
    issues: null,
    status:      "pending",
    reviewer_id: null,
    review_note: null,
    created_at:  "2026-06-03T10:01:00",
  };
}

function pageOf(items: HitlQueueItem[]): HitlQueuePageResponse {
  return { items, total: items.length, limit: 20, offset: 0 };
}

// ── 공통 setup ───────────────────────────────────────────────────────────────

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(hitlApi.listHitlQueue).mockResolvedValue(pageOf([]));
  vi.mocked(hitlApi.suggestCategory).mockResolvedValue({
    suggested: ["NCS교육", "직무교육"],
    reasoning: "NCS 기반 자료입니다.",
    alternatives: ["아키텍처"],
  });
  vi.mocked(hitlApi.applyCategory).mockResolvedValue({ status: "ok", message: "카테고리 적용 완료" });
  vi.mocked(hitlApi.approveHitl).mockResolvedValue({ status: "ok", message: "승인됨" });
  vi.mocked(hitlApi.rejectHitl).mockResolvedValue({ status: "ok", message: "거부됨" });
  vi.mocked(hitlApi.reprocessHitl).mockResolvedValue({ status: "ok", message: "재처리", doc_id: "doc-001" });
  vi.mocked(hitlApi.getHitlMarkdown).mockResolvedValue({ markdown: "# 미리보기 내용", path: "markdown/test/raw.md" });
});

// ── KB Evolution 패널 표시 ───────────────────────────────────────────────────

describe("HitlQueue — KB Evolution 패널 표시", () => {

  it("KB Evolution 항목 클릭 시 KB 패널이 렌더링된다", async () => {
    vi.mocked(hitlApi.listHitlQueue).mockResolvedValue(pageOf([makeKbItem()]));
    render(<HitlQueue />);

    const card = await screen.findByText("새 카테고리 감지");
    fireEvent.click(card);

    expect(await screen.findByText(/AI 카테고리 제안/i)).toBeInTheDocument();
  });

  it("일반 항목 클릭 시 KB 패널이 표시되지 않는다", async () => {
    vi.mocked(hitlApi.listHitlQueue).mockResolvedValue(pageOf([makeNormalItem()]));
    render(<HitlQueue />);

    const card = await screen.findByText("품질 점수 미달");
    fireEvent.click(card);

    await screen.findByText("항목 상세");
    expect(screen.queryByText(/AI 카테고리 제안/i)).toBeNull();
  });
});

// ── KB Evolution AI 제안 흐름 ────────────────────────────────────────────────

describe("HitlQueue — KB Evolution AI 제안 흐름", () => {

  async function renderWithKbSelected() {
    vi.mocked(hitlApi.listHitlQueue).mockResolvedValue(pageOf([makeKbItem()]));
    render(<HitlQueue />);
    const card = await screen.findByText("새 카테고리 감지");
    fireEvent.click(card);
    await screen.findByText(/AI 카테고리 제안/i);
  }

  it("'AI 제안 받기' 버튼 클릭 시 suggestCategory 호출", async () => {
    await renderWithKbSelected();
    fireEvent.click(screen.getByRole("button", { name: /AI 제안 받기/i }));
    await waitFor(() =>
      expect(hitlApi.suggestCategory).toHaveBeenCalledWith("kb-queue-001"),
    );
  });

  it("제안 결과 — suggested 목록이 화면에 표시된다", async () => {
    await renderWithKbSelected();
    fireEvent.click(screen.getByRole("button", { name: /AI 제안 받기/i }));
    expect(await screen.findByText("NCS교육")).toBeInTheDocument();
    expect(await screen.findByText("직무교육")).toBeInTheDocument();
  });

  it("제안 항목 클릭 시 확정 적용 버튼이 활성화된다", async () => {
    await renderWithKbSelected();
    fireEvent.click(screen.getByRole("button", { name: /AI 제안 받기/i }));
    await screen.findByText("NCS교육");
    fireEvent.click(screen.getByText("NCS교육"));

    expect(screen.getByRole("button", { name: /확정 적용/i })).not.toBeDisabled();
  });

  it("'확정 적용' 클릭 시 applyCategory 호출", async () => {
    await renderWithKbSelected();
    fireEvent.click(screen.getByRole("button", { name: /AI 제안 받기/i }));
    await screen.findByText("NCS교육");
    fireEvent.click(screen.getByText("NCS교육"));
    fireEvent.click(screen.getByRole("button", { name: /확정 적용/i }));

    await waitFor(() =>
      expect(hitlApi.applyCategory).toHaveBeenCalledWith(
        "kb-queue-001", "NCS교육", expect.any(String),
      ),
    );
  });
});

// ── KB Evolution 직접 입력 흐름 ──────────────────────────────────────────────

describe("HitlQueue — KB Evolution 직접 입력 흐름", () => {

  async function renderWithKbSelected() {
    vi.mocked(hitlApi.listHitlQueue).mockResolvedValue(pageOf([makeKbItem()]));
    render(<HitlQueue />);
    const card = await screen.findByText("새 카테고리 감지");
    fireEvent.click(card);
    await screen.findByText(/AI 카테고리 제안/i);
  }

  it("텍스트 입력 후 '확정 적용' → applyCategory에 입력값 전달", async () => {
    await renderWithKbSelected();

    const input = screen.getByPlaceholderText(/직접 입력/i);
    fireEvent.change(input, { target: { value: "커스텀카테고리" } });
    fireEvent.click(screen.getByRole("button", { name: /확정 적용/i }));

    await waitFor(() =>
      expect(hitlApi.applyCategory).toHaveBeenCalledWith(
        "kb-queue-001", "커스텀카테고리", expect.any(String),
      ),
    );
  });

  it("카테고리 미선택 + 입력 없을 때 '확정 적용' 버튼 비활성", async () => {
    await renderWithKbSelected();

    const applyBtn = screen.getByRole("button", { name: /확정 적용/i });
    expect(applyBtn).toBeDisabled();
  });
});

// ── T5: 파서/파일 정보 행 표시 ────────────────────────────────────────────────

describe("HitlQueue — 파서/파일 정보 표시", () => {
  function makeItemWithDocInfo(overrides: Partial<HitlQueueItem> = {}): HitlQueueItem {
    return {
      queue_id: "q-docinfo-001",
      doc_id:   "doc-docinfo-001",
      stage:    "stage2_validate",
      reason:   "품질 검증 실패",
      quality_score: 0.75,
      issues: null,
      status:      "pending",
      reviewer_id: null,
      review_note: null,
      created_at:  "2026-06-03T10:00:00",
      original_filename: "테스트문서.pdf",
      file_type: "pdf",
      parser_used: "upstage",
      ...overrides,
    };
  }

  it("original_filename이 있으면 '원본 파일' 행이 표시된다", async () => {
    vi.mocked(hitlApi.listHitlQueue).mockResolvedValue(pageOf([makeItemWithDocInfo()]));
    render(<HitlQueue />);
    const card = await screen.findByText("품질 검증 실패");
    fireEvent.click(card);
    expect(await screen.findByText("테스트문서.pdf")).toBeInTheDocument();
  });

  it("parser_used가 있으면 '파서' 행이 표시된다", async () => {
    vi.mocked(hitlApi.listHitlQueue).mockResolvedValue(pageOf([makeItemWithDocInfo()]));
    render(<HitlQueue />);
    const card = await screen.findByText("품질 검증 실패");
    fireEvent.click(card);
    expect(await screen.findByText("upstage")).toBeInTheDocument();
  });

  it("parser_used가 null이면 '파서' 행이 표시되지 않는다", async () => {
    vi.mocked(hitlApi.listHitlQueue).mockResolvedValue(
      pageOf([makeItemWithDocInfo({ parser_used: null, file_type: null, original_filename: null })])
    );
    render(<HitlQueue />);
    const card = await screen.findByText("품질 검증 실패");
    fireEvent.click(card);
    await screen.findByText("항목 상세");
    expect(screen.queryByText("upstage")).toBeNull();
  });
});

// ── T2: issues 카드 렌더링 ────────────────────────────────────────────────────

describe("HitlQueue — issues 이슈 카드 렌더링", () => {
  function makeItemWithIssues(issues: Record<string, unknown> | null): HitlQueueItem {
    return {
      queue_id: "q-issues-001",
      doc_id:   "doc-issues-001",
      stage:    "stage2_validate",
      reason:   "품질 검증 실패",
      quality_score: 0.75,
      issues: issues as HitlQueueItem["issues"],
      status:      "pending",
      reviewer_id: null,
      review_note: null,
      created_at:  "2026-06-03T10:00:00",
    };
  }

  it("quality_issues 배열의 각 항목이 개별 텍스트로 표시된다", async () => {
    vi.mocked(hitlApi.listHitlQueue).mockResolvedValue(
      pageOf([makeItemWithIssues({
        quality_issues: ["표 구조 손실", "헤딩 계층 오류"],
        markdown_storage_path: "markdown/doc-001/raw.md",
      })])
    );
    render(<HitlQueue />);
    const card = await screen.findByText("품질 검증 실패");
    fireEvent.click(card);

    expect(await screen.findByText("표 구조 손실")).toBeInTheDocument();
    expect(screen.getByText("헤딩 계층 오류")).toBeInTheDocument();
  });

  it("raw JSON 덩어리(JSON.stringify 결과)가 화면에 보이지 않는다", async () => {
    vi.mocked(hitlApi.listHitlQueue).mockResolvedValue(
      pageOf([makeItemWithIssues({
        quality_issues: ["표 구조 손실"],
        markdown_storage_path: "markdown/doc-001/raw.md",
      })])
    );
    render(<HitlQueue />);
    const card = await screen.findByText("품질 검증 실패");
    fireEvent.click(card);

    await screen.findByText("표 구조 손실");
    // raw JSON 브라켓이 그대로 노출되지 않아야 함
    expect(screen.queryByText(/\"quality_issues\"/)).toBeNull();
  });

  it("issues가 null이면 이슈 섹션이 표시되지 않는다", async () => {
    vi.mocked(hitlApi.listHitlQueue).mockResolvedValue(
      pageOf([makeItemWithIssues(null)])
    );
    render(<HitlQueue />);
    const card = await screen.findByText("품질 검증 실패");
    fireEvent.click(card);

    await screen.findByText("항목 상세");
    expect(screen.queryByText(/이슈 목록/i)).toBeNull();
  });

  it("quality_issues가 빈 배열이면 이슈 섹션이 표시되지 않는다", async () => {
    vi.mocked(hitlApi.listHitlQueue).mockResolvedValue(
      pageOf([makeItemWithIssues({ quality_issues: [] })])
    );
    render(<HitlQueue />);
    const card = await screen.findByText("품질 검증 실패");
    fireEvent.click(card);

    await screen.findByText("항목 상세");
    expect(screen.queryByText(/이슈 목록/i)).toBeNull();
  });
});

// ── T7: Markdown 미리보기 패널 ────────────────────────────────────────────────

describe("HitlQueue — Markdown 미리보기 패널", () => {
  function makeItemForPreview(): HitlQueueItem {
    return {
      queue_id: "q-preview-001",
      doc_id:   "doc-preview-001",
      stage:    "stage2_validate",
      reason:   "품질 검증 실패",
      quality_score: 0.75,
      issues: { quality_issues: ["표 구조 손실"] } as HitlQueueItem["issues"],
      status:      "pending",
      reviewer_id: null,
      review_note: null,
      created_at:  "2026-06-03T10:00:00",
    };
  }

  it("'Markdown 미리보기' 버튼이 상세 패널에 표시된다", async () => {
    vi.mocked(hitlApi.listHitlQueue).mockResolvedValue(pageOf([makeItemForPreview()]));
    render(<HitlQueue />);
    const card = await screen.findByText("품질 검증 실패");
    fireEvent.click(card);

    expect(await screen.findByRole("button", { name: /Markdown 미리보기/i })).toBeInTheDocument();
  });

  it("버튼 클릭 시 getHitlMarkdown이 호출된다", async () => {
    vi.mocked(hitlApi.listHitlQueue).mockResolvedValue(pageOf([makeItemForPreview()]));
    render(<HitlQueue />);
    const card = await screen.findByText("품질 검증 실패");
    fireEvent.click(card);

    const btn = await screen.findByRole("button", { name: /Markdown 미리보기/i });
    fireEvent.click(btn);

    await waitFor(() =>
      expect(hitlApi.getHitlMarkdown).toHaveBeenCalledWith("q-preview-001")
    );
  });

  it("Markdown 내용이 로드되면 화면에 표시된다", async () => {
    vi.mocked(hitlApi.listHitlQueue).mockResolvedValue(pageOf([makeItemForPreview()]));
    render(<HitlQueue />);
    const card = await screen.findByText("품질 검증 실패");
    fireEvent.click(card);

    const btn = await screen.findByRole("button", { name: /Markdown 미리보기/i });
    fireEvent.click(btn);

    expect(await screen.findByText("# 미리보기 내용")).toBeInTheDocument();
  });
});
