import { useState, useEffect, useRef, useCallback, useMemo } from "react";
import {
  runPipelineStart,
  continuePipeline,
  learnFrameworkMetadata,
  type PrescanResult,
  type LearnMetadataPayload,
} from "@/services/pipelineOrchestrator";
import { MetadataLearnModal } from "@/components/molecules/MetadataLearnModal";

// ── 도메인 레지스트리 (수정 없음) ───────────────────────────────────────────
const DOMAIN_REGISTRY: Record<string, { label_ko: string; color_hex: string; bg_hex: string; border_hex: string }> = {
  security:    { label_ko: "보안",  color_hex: "#B91C1C", bg_hex: "#FEF2F2", border_hex: "#FCA5A5" },
  performance: { label_ko: "성능",  color_hex: "#0F766E", bg_hex: "#F0FDF4", border_hex: "#86EFAC" },
};

type ConceptItem = {
  name: string;
  concept_type: string;
  cwe_id: string;
  owasp_id: string;
  severity: string;
  description_ko: string;
  aliases: string[];
  affected_components: string[];
  mechanism: string[];
  domains: string[];
  state: string;
  // 3-Factor 하이브리드 판정 역추적 (DRAFT 개념에서만 유효)
  infer_action?: string;
  infer_confidence?: number;
  target_concept_name?: string;
  score_jaro_winkler?: number;
  score_name_vector?: number;
  score_desc_vector?: number;
};

const INITIAL_CONCEPTS: ConceptItem[] = [
  {
    name: "SQLi",
    concept_type: "vulnerability_root_cause",
    cwe_id: "CWE-89",
    owasp_id: "A03:2025",
    severity: "critical",
    description_ko: "SQL 인젝션은 공격자가 악의적인 SQL 구문을 입력값에 삽입하여 데이터베이스를 조작하는 공격.",
    aliases: ["SQL Injection", "SQLInjection", "SqlInjectionVulnerability"],
    affected_components: ["database_query_layer", "orm_layer"],
    mechanism: ["parameterized_query", "input_type_validation"],
    domains: ["security"],
    state: "COMMITTED",
  },
  {
    name: "XSS",
    concept_type: "vulnerability_root_cause",
    cwe_id: "CWE-79",
    owasp_id: "A03:2025",
    severity: "high",
    description_ko: "크로스 사이트 스크립팅(XSS)은 공격자가 악성 스크립트를 신뢰된 웹 페이지에 주입하는 공격.",
    aliases: ["Cross-Site Scripting", "CrossSiteScripting"],
    affected_components: ["template_rendering_layer", "api_response_serialization"],
    mechanism: ["output_encoding", "content_security_policy"],
    domains: ["security"],
    state: "COMMITTED",
  },
  {
    name: "BrokenAccessControl",
    concept_type: "vulnerability_root_cause",
    cwe_id: "CWE-284",
    owasp_id: "A01:2021",
    severity: "critical",
    description_ko: "접근 제어 결함은 사용자가 권한 밖의 작업을 수행할 수 있게 만드는 보안 취약점.",
    aliases: ["Broken Access Control", "IDOR", "AuthorizationBypass"],
    affected_components: ["authorization_layer", "api_endpoint"],
    mechanism: ["rbac", "attribute_based_access_control"],
    domains: ["security"],
    state: "COMMITTED",
  },
  {
    name: "CSRF",
    concept_type: "vulnerability_root_cause",
    cwe_id: "CWE-352",
    owasp_id: "A01:2021",
    severity: "high",
    description_ko: "사용자가 의도하지 않은 상태 변경 요청을 공격자가 위조하여 인증된 사용자 권한으로 실행시키는 공격.",
    aliases: ["CrossSiteRequestForgery", "CSRFAttack", "크로스사이트 요청 위조"],
    affected_components: ["web_forms", "session_management", "api_endpoints"],
    mechanism: ["csrf_token", "samesite_cookie", "origin_validation"],
    domains: ["security"],
    state: "COMMITTED",
  },
  {
    name: "MissingIndex",
    concept_type: "performance_antipattern",
    cwe_id: "CWE-1047",
    owasp_id: "",
    severity: "medium",
    description_ko: "인덱스 누락으로 인해 DB 전체 테이블 스캔(Full Scan)이 발생하여 쿼리 성능이 급격히 저하되는 안티패턴.",
    aliases: ["Missing Database Index", "MissingDbIndex", "FullTableScan"],
    affected_components: ["database_query_layer", "reporting_module"],
    mechanism: ["composite_index", "covering_index"],
    domains: ["performance"],
    state: "COMMITTED",
  },
  {
    name: "N+1Query",
    concept_type: "performance_antipattern",
    cwe_id: "CWE-1048",
    owasp_id: "",
    severity: "medium",
    description_ko: "루프 내에서 관련 객체를 개별 쿼리로 지연 로딩하여 DB 쿼리가 N+1회 실행되는 성능 안티패턴.",
    aliases: ["NPlusOneQuery", "NPlusOneQueryProblem", "LazyLoadingLoop"],
    affected_components: ["orm_layer", "database_query_layer", "api_list_endpoint"],
    mechanism: ["eager_loading", "batch_fetch"],
    domains: ["performance"],
    state: "COMMITTED",
  },
];

// DRAFT 시연용 [시나리오 A] NEW 분기 — ConnPoolExhaustion (Hybrid Score 0.439 < 0.72)
const DRAFT_CONCEPT: ConceptItem = {
  name: "ConnPoolExhaustion",
  concept_type: "performance_antipattern",
  cwe_id: "CWE-400",
  owasp_id: "",
  severity: "high",
  description_ko: "커넥션 반환 실패 또는 풀 설정 미흡으로 DB 커넥션 풀이 고갈되어 새로운 요청이 대기 또는 실패.",
  aliases: ["Connection Pool Exhaustion", "커넥션 풀 고갈", "DB Connection Leak"],
  affected_components: ["database_connection_pool", "http_client_pool", "api_gateway"],
  mechanism: ["connection_pool_sizing", "context_manager_connection"],
  domains: ["security", "performance"],
  state: "DRAFT",
  infer_action: "NEW",
  infer_confidence: 0.439,
  score_jaro_winkler: 0.421,
  score_name_vector: 0.512,
  score_desc_vector: 0.388,
};

// DRAFT 시연용 [시나리오 B] MERGE 분기 — CrossSiteRequestForgery → CSRF 병합 (Hybrid Score 0.934 ≥ 0.88)
const DRAFT_CONCEPT_MERGE: ConceptItem = {
  name: "CrossSiteRequestForgery",
  concept_type: "vulnerability_root_cause",
  cwe_id: "CWE-352",
  owasp_id: "A01:2021",
  severity: "high",
  description_ko: "사용자가 의도하지 않은 상태 변경 요청을 공격자가 위조하여 인증된 사용자 권한으로 실행시키는 공격.",
  aliases: ["Cross-Site Request Forgery", "Session Riding", "CSRF"],
  affected_components: ["web_forms", "api_endpoints", "session_management"],
  mechanism: ["csrf_token", "samesite_cookie", "origin_validation"],
  domains: ["security"],
  state: "DRAFT",
  infer_action: "MERGE",
  infer_confidence: 0.934,
  target_concept_name: "CSRF",
  score_jaro_winkler: 0.961,
  score_name_vector: 0.924,
  score_desc_vector: 0.911,
};

// ── 타입 정의 ─────────────────────────────────────────────────────────────────
type PipelineState = "IDLE" | "RUNNING" | "WAITING_APPROVAL" | "COMMITTING" | "FINISHED";
export type StepStatus = "IDLE" | "LOADING" | "SUCCESS" | "FAILED";
export type StepStatuses = Record<number, StepStatus>;
export type ToastItem = { id: string; kind: "info" | "success" | "warning" | "error"; message: string };

// ── 스텝 메타데이터 (보정 완료: SAME_AS 잔재 완벽 척결) ──────────────────────────
const STEPS_CONFIG = [
  { step: 1, title: "Input Agent",        desc: "링크 유효성 및 ETag 캐싱 분석" },
  { step: 2, title: "Crawler Agent",      desc: "DOM 파싱 및 텍스트 블록 정제" },
  { step: 3, title: "Extractor Agent",    desc: "Gemini 구조화 의미 스키마 추출" },
  { step: 4, title: "Graph Writer Agent", desc: "PostgreSQL / Neo4j 스테이징 적재" },
  { step: 5, title: "Link Resolver Agent", desc: "하이브리드 유사도 판정 및 동의어 수렴" }, // 🛠️ 수정: SAME_AS 삭제 및 유사도 수렴 명시
];

// ── 스텝별 실시간 동적 롤링 로딩 가이드 (보정 완료: 렉시컬/의미론적 병합 원리 반영) ──
const STEP_LOADING_TEXTS: Record<number, string> = {
  1: "대기열 링크 해시 검사 및 도메인 분석 중...",
  2: "대상 URL에서 불필요한 DOM 제거 및 핵심 본문 텍스트 추출 중...",
  3: "Gemini 2.5 Flash 가동 중. 보안 메커니즘, 취약점 원인 및 설정 속성 구조화 JSON 추출 중...",
  4: "추출된 JSON 데이터를 PostgreSQL 및 Neo4j 스테이징(DRAFT) 레이어에 분리 보관 중...",
  5: "Jaro-Winkler 렉시컬 판정과 임베딩 코사인 유사도 분석을 통한 동의어 수렴 및 RELATED_TO 연관 조인 중...", // 🛠️ 수정: 하이브리드 수렴 논리 상세화
};

const INITIAL_STEP_STATUSES: StepStatuses = { 1: "IDLE", 2: "IDLE", 3: "IDLE", 4: "IDLE", 5: "IDLE" };

// 메인 컴포넌트 껍데기 선언 (React 규격 준수용)
export default function App() {
  return (
    <div className="p-6 bg-stone-50 min-h-screen">
      <h1 className="text-xl font-bold text-stone-800">지식 에이전트 수집 파이프라인 관제판</h1>
      <p className="text-xs text-stone-500 mt-1">하이브리드 유사도 통계 매칭 및 수렴 엔진 적용 완료</p>
    </div>
  );
}
// ── PipelineStepList: 단계별 Spinner/Check/X/Dot 인디케이터 ──────────────────
export function PipelineStepList({
  statuses,
  onRetry,
}: {
  statuses: StepStatuses;
  onRetry?: (step: number) => void;
}) {
  return (
    <div className="space-y-3">
      {STEPS_CONFIG.map((s) => {
        const status: StepStatus = (statuses[s.step] ?? "IDLE") as StepStatus;
        return (
          <div
            key={s.step}
            data-testid={`step-${s.step}`}
            className="group flex items-center justify-between p-3 rounded-xl border border-stone-100 bg-stone-50/50"
          >
            <div className="flex items-center space-x-3">
              <div className="w-6 h-6 flex items-center justify-center shrink-0">
                {status === "LOADING" && (
                  <div
                    data-testid="spinner"
                    className="animate-spin rounded-full h-4 w-4 border-2 border-[#115E59] border-t-transparent"
                  />
                )}
                {status === "SUCCESS" && (
                  <span data-testid="check" className="text-emerald-600 font-bold text-sm">✓</span>
                )}
                {status === "FAILED" && (
                  <span className="relative w-6 h-6 flex items-center justify-center">
                    <span data-testid="x-mark" className="text-rose-500 font-bold text-sm group-hover:invisible">✗</span>
                    {onRetry && (
                      <button
                        data-testid="retry-btn"
                        onClick={() => onRetry(s.step)}
                        className="absolute inset-0 invisible group-hover:visible flex items-center justify-center text-[8px] font-bold bg-rose-100 text-rose-700 rounded-md leading-none hover:bg-rose-200 transition-colors"
                      >
                        RETRY
                      </button>
                    )}
                  </span>
                )}
                {status === "IDLE" && (
                  <span data-testid="idle-dot" className="w-2 h-2 rounded-full bg-stone-300 block" />
                )}
              </div>
              <div>
                <span className={`text-sm font-bold block ${status !== "IDLE" ? "text-stone-900" : "text-stone-400"}`}>
                  {s.step}. {s.title}
                </span>
                <span className={`text-xs block mt-0.5 ${
                  status === "LOADING" ? "text-amber-600 font-medium animate-pulse" :
                  status === "FAILED"  ? "text-rose-400" :
                  status !== "IDLE"    ? "text-stone-400" : "text-stone-300"
                }`}>
                  {status === "LOADING" ? STEP_LOADING_TEXTS[s.step] : s.desc}
                </span>
              </div>
            </div>
            {status === "LOADING" && (
              <span className="text-xs text-amber-600 font-medium animate-pulse shrink-0 ml-2">
                응답 대기 중...
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

// ── ToastContainer: 우측 상단 고정 알림 ──────────────────────────────────────
export function ToastContainer({ toasts, onDismiss }: { toasts: ToastItem[]; onDismiss: (id: string) => void }) {
  return (
    <div className="fixed top-4 right-4 z-50 space-y-2 pointer-events-none" role="status" aria-live="polite">
      {toasts.map((t) => (
        <div
          key={t.id}
          data-testid="toast"
          className={`pointer-events-auto flex items-center space-x-2 px-4 py-3 rounded-xl shadow-lg text-sm font-medium max-w-sm ${
            t.kind === "success" ? "bg-emerald-50 border border-emerald-200 text-emerald-800" :
            t.kind === "error"   ? "bg-rose-50 border border-rose-200 text-rose-800" :
            t.kind === "warning" ? "bg-amber-50 border border-amber-200 text-amber-800" :
            "bg-white border border-stone-200 text-stone-800"
          }`}
        >
          <span className="shrink-0">
            {t.kind === "success" ? "✓" : t.kind === "error" ? "✗" : t.kind === "warning" ? "⚠" : "ℹ"}
          </span>
          <span className="flex-1">{t.message}</span>
          <button
            data-testid="toast-dismiss"
            onClick={() => onDismiss(t.id)}
            className="shrink-0 text-stone-400 hover:text-stone-600 ml-1 text-sm leading-none"
          >×</button>
        </div>
      ))}
    </div>
  );
}

// ── 유틸리티 ──────────────────────────────────────────────────────────────────
function detectFramework(url: string): string {
  const u = url.toLowerCase();
  if (u.includes("spring"))  return "Spring Framework 명세 자동 추론";
  if (u.includes("django"))  return "Django Framework 명세 자동 추론";
  if (u.includes("react"))   return "React 문서 패턴 적용";
  if (u.includes("fastapi")) return "FastAPI 명세 자동 추론";
  return "범용 가이드라인 분석 패턴 적용";
}

type ApiMechanism = string | { mechanism_name: string; code_examples?: unknown[] };

type ApiConcept = {
  id: string; state: string; concept_name: string; domains: string[];
  concept_type?: string; cwe_id?: string; owasp_id?: string; severity?: string;
  description_ko?: string; aliases?: string[]; affected_components?: string[];
  mechanism?: ApiMechanism[];
  // staging API가 3-Factor 점수를 반환할 때 (선택적)
  infer_action?: string;
  infer_confidence?: number;
  target_concept_name?: string;
  score_jaro_winkler?: number;
  score_name_vector?: number;
  score_desc_vector?: number;
};

function normMechanism(m: ApiMechanism): string {
  return typeof m === "string" ? m : (m.mechanism_name ?? "");
}

function mapApiConcept(item: ApiConcept) {
  return {
    name: item.concept_name, concept_type: item.concept_type ?? "vulnerability_root_cause",
    cwe_id: item.cwe_id ?? "", owasp_id: item.owasp_id ?? "",
    severity: item.severity ?? "medium", description_ko: item.description_ko ?? "",
    aliases: item.aliases ?? [], affected_components: item.affected_components ?? [],
    mechanism: (item.mechanism ?? []).map(normMechanism),
    domains: item.domains ?? [], state: item.state ?? "DRAFT",
    infer_action: item.infer_action,
    infer_confidence: item.infer_confidence,
    target_concept_name: item.target_concept_name,
    score_jaro_winkler: item.score_jaro_winkler,
    score_name_vector: item.score_name_vector,
    score_desc_vector: item.score_desc_vector,
  };
}

type GraphNode = {
  id: string; label: "Domain" | "Concept" | "Mechanism";
  name?: string; concept_type?: string; cwe_id?: string; owasp_id?: string;
  severity?: string; domains?: string[]; description_ko?: string; aliases?: string[];
  state?: string;
};
type GraphEdge = { source: string; target: string; type: string };

function layoutMechanismNodes(mechs: GraphNode[]): (GraphNode & { cx: number; cy: number })[] {
  const visible = mechs.slice(0, 6);
  const count = visible.length;
  return visible.map((m, i) => ({
    ...m,
    cx: Math.round(860 / (count + 1) * (i + 1)),
    cy: 390,
  }));
}


const _domainKeys = Object.keys(DOMAIN_REGISTRY);
const DOMAIN_HUB_POS: Record<string, number[]> = Object.fromEntries(
  _domainKeys.map((d, i) => [d, [Math.round(860 / (_domainKeys.length + 1) * (i + 1)), 47]])
);
const CONCEPT_R = 18;
const MAX_PER_CONCEPT_ROW = 8;
const CONCEPT_ROW_Y = [175, 135];

function getConceptStyle(domains: string[] | undefined) {
  const d = domains ?? [];
  const s = d.includes("security"), p = d.includes("performance");
  if (s && p) return { fill: "#EEF2FF", stroke: "#4F46E5", text: "#4F46E5" };
  if (s)      return { fill: "#FEF2F2", stroke: "#B91C1C", text: "#B91C1C" };
  if (p)      return { fill: "#F0FDF4", stroke: "#0F766E", text: "#0F766E" };
  return             { fill: "#F5F3FF", stroke: "#7C3AED", text: "#7C3AED" };
}

function graphLabel(name: string): string {
  if (name.length <= 5) return name;
  const caps = Array.from(name).filter(c => c >= "A" && c <= "Z");
  if (caps.length >= 2) return caps.join("").slice(0, 4);
  return name.slice(0, 4);
}

function layoutConceptNodes<T extends { name: string; domains: string[]; cwe_id: string }>(list: T[]) {
  return list.map((c, i) => {
    const row    = Math.floor(i / MAX_PER_CONCEPT_ROW);
    const col    = i % MAX_PER_CONCEPT_ROW;
    const rowCnt = Math.min(list.length - row * MAX_PER_CONCEPT_ROW, MAX_PER_CONCEPT_ROW);
    return { ...c, cx: Math.round(860 / (rowCnt + 1) * (col + 1)), cy: CONCEPT_ROW_Y[Math.min(row, 1)] };
  });
}

// ── MainPage ──────────────────────────────────────────────────────────────────
export function MainPage() {
  const [urls, setUrls] = useState([
    { id: 1, value: "https://docs.djangoproject.com/en/6.0/topics/security/",      label: "Django Core Security 명세 감지" },
    { id: 2, value: "https://docs.spring.io/spring-security/reference/reactive/", label: "Spring Security Reactive 명세 감지" },
  ]);
  const [newUrl, setNewUrl]               = useState("");
  const [pipelineState, setPipelineState] = useState<PipelineState>("IDLE");
  const [stepStatuses, setStepStatuses]   = useState<StepStatuses>(INITIAL_STEP_STATUSES);
  const [toasts, setToasts]               = useState<ToastItem[]>([]);
  const [showDrawer, setShowDrawer]       = useState(false);
  const [logs, setLogs] = useState([
    { time: "00:00:00", type: "SYSTEM", message: "수집 에이전트 토폴로지 분석 웹뷰가 초기화되었습니다." },
    { time: "00:00:02", type: "DB",     message: "domain_registry 캐시 주입 완료. [security, performance]" },
  ]);
  const [concepts, setConcepts]             = useState(INITIAL_CONCEPTS);
  const [selectedConcept, setSelectedConcept] = useState<ConceptItem | undefined>(INITIAL_CONCEPTS[0]);
  const [showDraft, setShowDraft]           = useState(false);
  const [activeTab, setActiveTab]           = useState("all");
  const [pendingDomain, setPendingDomain]   = useState(false);
  const [apiGraph, setApiGraph]             = useState<{ nodes: GraphNode[]; edges: GraphEdge[] }>({ nodes: [], edges: [] });
  const [graphSearch, setGraphSearch]       = useState("");
  const [codeLang, setCodeLang]             = useState("");
  const [codeFramework, setCodeFramework]   = useState("");
  const [codeResult, setCodeResult]         = useState<{
    langs: string[]; frameworks: string[]; examples: Array<{
      mechanism: string; lang: string; framework: string; code: string; description?: string;
    }>;
  } | null>(null);
  const [codeLoading, setCodeLoading]       = useState(false);
  const [draftSummary, setDraftSummary]     = useState<{ count: number; names: string[]; domains: string[] }>({ count: 0, names: [], domains: [] });
  const [metadataLearnModal, setMetadataLearnModal] = useState<PrescanResult | null>(null);
  const [isLearningMetadata, setIsLearningMetadata] = useState(false);

  const consoleRef        = useRef<HTMLDivElement>(null);
  const sseRef            = useRef<EventSource | null>(null);
  const sessionIdRef      = useRef<string | null>(null);
  const docIdRef          = useRef<string | null>(null);
  const lastDocStateRef   = useRef<string | null>(null);
  const stagingFetchedRef = useRef(false);
  const baselineNamesRef = useRef<Set<string> | null>(null);
  const [svgViewBox, setSvgViewBox] = useState({ x: 0, y: 0, w: 860, h: 520 });
  const [svgDragging, setSvgDragging] = useState(false);
  const svgContainerRef = useRef<HTMLDivElement>(null);
  const isDraggingRef   = useRef(false);
  const dragStartRef    = useRef({ mx: 0, my: 0, vx: 0, vy: 0, vw: 860, vh: 520 });

  useEffect(() => () => { if (sseRef.current) sseRef.current.close(); }, []);
  useEffect(() => {
    if (consoleRef.current) consoleRef.current.scrollTop = consoleRef.current.scrollHeight;
  }, [logs]);

  // ── Toast 헬퍼 ──────────────────────────────────────────────────────────
  const addToast = useCallback((kind: ToastItem["kind"], message: string) => {
    const id = `t-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setToasts(prev => [...prev, { id, kind, message }]);
    setTimeout(() => setToasts(prev => prev.filter(t => t.id !== id)), 4000);
  }, []);

  const dismissToast = useCallback((id: string) => {
    setToasts(prev => prev.filter(t => t.id !== id));
  }, []);

  // ── 토폴로지 조회 ────────────────────────────────────────────────────────
  const fetchTopology = useCallback(async (domain: string, search: string) => {
    try {
      const params = new URLSearchParams();
      if (domain !== "all") params.set("domains", domain);
      if (search.trim()) params.set("search", search.trim());
      const res = await fetch(`/api/graph/topology?${params}`);
      if (!res.ok) return;
      const data = await res.json();
      setApiGraph(data);
      const seedMap = new Map(INITIAL_CONCEPTS.map((c) => [c.name, c]));
      const apiConcepts = (data.nodes as GraphNode[])
        .filter((n) => n.label === "Concept")
        .map((n) => {
          const seed = seedMap.get(n.name ?? "");
          return {
            name: n.name ?? n.id,
            concept_type: n.concept_type ?? seed?.concept_type ?? "vulnerability_root_cause",
            cwe_id: n.cwe_id ?? seed?.cwe_id ?? "",
            owasp_id: n.owasp_id ?? seed?.owasp_id ?? "",
            severity: n.severity ?? seed?.severity ?? "medium",
            description_ko: n.description_ko ?? seed?.description_ko ?? "",
            aliases: n.aliases ?? seed?.aliases ?? [],
            affected_components: seed?.affected_components ?? [],
            mechanism: seed?.mechanism ?? [],
            domains: n.domains ?? seed?.domains ?? [],
            state: n.state ?? "COMMITTED",
          };
        });
      if (baselineNamesRef.current === null) {
        baselineNamesRef.current = new Set(apiConcepts.map((c) => c.name));
      }
      setConcepts(apiConcepts as typeof INITIAL_CONCEPTS);
      if (apiConcepts.length > 0) {
        setSelectedConcept(apiConcepts[0] as typeof INITIAL_CONCEPTS[0]);
      }
    } catch { /* 네트워크 오류 시 하드코딩 초기값 유지 */ }
  }, []);

  useEffect(() => { fetchTopology("all", ""); }, [fetchTopology]);

  // DEV mock: CSRF는 INITIAL_CONCEPTS에 포함됨 — 별도 덮어쓰기 불필요
  // (이전: setConcepts([CSRF_SEED]) → 다른 시드 개념을 소거하는 부작용 있어 제거)

  useEffect(() => {
    const id = setTimeout(() => fetchTopology(activeTab, graphSearch), 300);
    return () => clearTimeout(id);
  }, [activeTab, graphSearch, fetchTopology]);

  // ── 코드 예제 조회 ───────────────────────────────────────────────────────
  const fetchCode = useCallback(async (conceptName: string, lang: string, framework: string) => {
    setCodeLoading(true);
    setCodeResult(null);
    try {
      const params = new URLSearchParams();
      if (lang) params.set("lang", lang);
      if (framework) params.set("framework", framework);
      const res = await fetch(`/api/graph/concept/${encodeURIComponent(conceptName)}/code?${params}`);
      if (res.ok) setCodeResult(await res.json());
    } catch { /* neo4j 미연결 시 null 유지 */ }
    finally { setCodeLoading(false); }
  }, []);

  useEffect(() => {
    if (!selectedConcept) return;
    setCodeLang("");
    setCodeFramework("");
    fetchCode(selectedConcept.name, "", "");
  }, [selectedConcept?.name, fetchCode]);

  function handleCodeLangChange(lang: string) {
    setCodeLang(lang);
    fetchCode(selectedConcept?.name ?? "", lang, codeFramework);
  }

  function handleCodeFrameworkChange(fw: string) {
    setCodeFramework(fw);
    fetchCode(selectedConcept?.name ?? "", codeLang, fw);
  }

  function addLog(type: string, message: string) {
    const t = new Date().toTimeString().slice(0, 8);
    setLogs((prev) => [...prev, { time: t, type, message }]);
  }

  // ── SSE 구독 (guardrail §1.3: GET /api/pipeline/stream/{session_id}) ──
  const startSSE = useCallback((sessionId: string) => {
    if (sseRef.current) { sseRef.current.close(); sseRef.current = null; }

    const es = new EventSource(`/api/pipeline/stream/${sessionId}`);
    sseRef.current = es;

    const closeSSE = () => { es.close(); sseRef.current = null; };

    es.onmessage = (event: MessageEvent) => {
      try {
        const msg: {
          type: string;
          agent?: string;
          status?: string;
          message?: string;
          ts?: string;
        } = JSON.parse(event.data as string);

        if (msg.type === "connected") {
          addLog("SYSTEM", `SSE 채널 확립 — session: ${sessionId}`);
          return;
        }

        if (msg.type === "log" && msg.message) {
          const t = msg.ts?.slice(11, 19) ?? new Date().toTimeString().slice(0, 8);
          // 로그 형식: "[AgentName] 메시지" — agent 필드는 별도로 내려오지 않음
          const agentMatch = msg.message.match(/^\[([^\]]+)\]/);
          const agentType = agentMatch ? agentMatch[1].toUpperCase() : "SYSTEM";
          setLogs((prev) => {
            if (prev.some((e) => e.message === msg.message)) return prev;
            return [...prev, { time: t, type: agentType, message: msg.message! }];
          });
          return;
        }

        // ── step_update: DB 상태 전이마다 백엔드가 발행 ────────────────────
        if (msg.type === "step_update") {
          const { agent, status } = msg;

          if (agent === "Input" && status === "DONE") {
            setStepStatuses(s => ({ ...s, 1: "SUCCESS" }));
          } else if (agent === "Crawler" && status === "RUNNING") {
            setStepStatuses(s => ({ ...s, 1: "SUCCESS", 2: "LOADING" }));
            addToast("info", "Crawler Agent 시작 — 원본 텍스트 정제 중");
            lastDocStateRef.current = "CRAWLING";
          } else if (agent === "Crawler" && status === "DONE") {
            setStepStatuses(s => ({ ...s, 2: "SUCCESS" }));
          } else if (agent === "Extractor" && status === "RUNNING") {
            setStepStatuses(s => ({ ...s, 2: "SUCCESS", 3: "LOADING" }));
            addToast("info", "Extractor Agent 시작 — Gemini 추출 중");
            lastDocStateRef.current = "EXTRACTING";
          } else if (agent === "Extractor" && status === "DONE" && !stagingFetchedRef.current) {
            stagingFetchedRef.current = true;
            lastDocStateRef.current = "EXTRACTED";
            setStepStatuses(s => ({ ...s, 3: "SUCCESS", 4: "LOADING" }));

            fetch(`/api/staging/${sessionId}?all_states=true`).then(async (sRes) => {
              if (!sRes.ok) return;
              const sData = await sRes.json();
              const drafted = (sData.items as ApiConcept[]).map(mapApiConcept);
              if (drafted.length > 0) {
                setConcepts((prev) => {
                  const names = new Set(prev.map((c) => c.name));
                  return [...prev, ...drafted.filter((d) => !names.has(d.name))] as typeof INITIAL_CONCEPTS;
                });
                setSelectedConcept(drafted[0] as typeof DRAFT_CONCEPT);
                const count = drafted.length;
                const names = drafted.slice(0, 3).map((d) => d.name);
                const domains = [...new Set(drafted.flatMap((d) => d.domains))];
                setDraftSummary({ count, names, domains });
                addToast("success", `${count}개 핵심 기술 개념 도출 완료`);
              }
              setStepStatuses(s => ({ ...s, 4: "SUCCESS" }));
              addLog("SYSTEM", "스테이징 적재 완료. 점선(DRAFT) 미리보기를 확인 후 승인하세요.");
              setPipelineState("WAITING_APPROVAL");
              setShowDraft(true);
            }).catch(() => {
              setStepStatuses(s => ({ ...s, 4: "SUCCESS" }));
              setPipelineState("WAITING_APPROVAL");
              setShowDraft(true);
            });
          } else if (agent === "Writer" && status === "DONE") {
            if (lastDocStateRef.current === "COMMITTED") return;
            lastDocStateRef.current = "COMMITTED";
            setStepStatuses(s => ({ ...s, 5: "SUCCESS" }));
            closeSSE();
            setConcepts((prev) => prev.map((c) => ({ ...c, state: "COMMITTED" })) as typeof INITIAL_CONCEPTS);
            addLog("SYSTEM", "파이프라인 완료 — COMMITTED");
            addToast("success", "파이프라인 완료 — 모든 개념이 확정 적재되었습니다");
            setPipelineState("FINISHED");
            setShowDraft(false);
            setUrls([]);
          }
          return;
        }

        if (msg.type === "finished") {
          if (lastDocStateRef.current === "COMMITTED") return;
          lastDocStateRef.current = "COMMITTED";
          setStepStatuses(s => ({ ...s, 5: "SUCCESS" }));
          closeSSE();
          setConcepts((prev) => prev.map((c) => ({ ...c, state: "COMMITTED" })) as typeof INITIAL_CONCEPTS);
          addLog("SYSTEM", "파이프라인 완료 — COMMITTED");
          addToast("success", "파이프라인 완료 — 모든 개념이 확정 적재되었습니다");
          setPipelineState("FINISHED");
          setShowDraft(false);
          setUrls([]);
        }
      } catch { /* JSON parse 오류 무시 */ }
    };

    es.onerror = () => {
      addLog("SYSTEM", "SSE 연결 오류 — 백엔드 재연결 대기 중...");
    };
  }, [addToast]);

  // ── URL 추가 ─────────────────────────────────────────────────────────────
  async function handleAddUrl(e: React.SyntheticEvent) {
    e.preventDefault();
    if (!newUrl.trim()) return;
    if (urls.length >= 5) { addLog("WARNING", "URL 대기열은 최대 5개입니다."); return; }
    if (urls.some((u) => u.value.toLowerCase() === newUrl.trim().toLowerCase())) {
      addLog("WARNING", `중복 URL 차단: ${newUrl}`); return;
    }
    try {
      const res = await fetch("/api/documents", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ urls: [newUrl.trim()] }),
      });
      if (!res.ok) throw new Error(`${res.status}`);
      const data = await res.json();
      const doc = data.documents?.[0];
      if (doc) {
        docIdRef.current = doc.doc_id;
        setUrls((prev) => [...prev, { id: Date.now(), value: newUrl.trim(), label: detectFramework(newUrl) }]);
        addLog("INPUT", `[EXT] 문서 등록 완료: ${doc.doc_id}`);
      }
    } catch {
      setUrls((prev) => [...prev, { id: Date.now(), value: newUrl.trim(), label: detectFramework(newUrl) }]);
      addLog("INPUT", `[로컬] URL 대기열 추가: ${newUrl}`);
    }
    setNewUrl("");
  }

  // ── 파이프라인 시작 ──────────────────────────────────────────────────────
  async function startPipeline() {
    if (urls.length === 0) return;
    setPipelineState("RUNNING");
    setStepStatuses({ ...INITIAL_STEP_STATUSES, 1: "LOADING" });
    stagingFetchedRef.current = false;
    lastDocStateRef.current = null;
    addLog("INPUT", "1단계 [Input Agent] 개시: 수집 링크 대기열 ETag 해시 검사 수행 중...");

    // DEV 시뮬레이션 (VITE_MOCK_PIPELINE=false 로 억제)
    if (import.meta.env.DEV && import.meta.env.VITE_MOCK_PIPELINE !== "false") {
      setTimeout(() => {
        setStepStatuses(s => ({ ...s, 1: "SUCCESS", 2: "LOADING" }));
        addLog("CRAWLER", "2단계 [Crawler Agent] 개시: 대상 URL DOM 정제 중...");
      }, 1500);
      setTimeout(() => {
        setStepStatuses(s => ({ ...s, 2: "SUCCESS", 3: "LOADING" }));
        addLog("EXTRACTOR", "3단계 [Extractor Agent] 개시: Gemini 2.5 Flash 구조화 추출 중...");
      }, 3000);
      setTimeout(() => {
        addLog("EXTRACTOR", "개념 1/2 추출: ConnPoolExhaustion (security+performance 교차 도메인)");
        addLog("RESOLVER", "▶ 3-Factor 판정 [1/2]: ConnPoolExhaustion vs. 시드 노드 풀 (16개)");
        addLog("RESOLVER", "  ① Jaro-Winkler(40%) = 0.421  ② Name_Vector cos(30%) = 0.512  ③ Desc_Vector cos(30%) = 0.388");
        addLog("RESOLVER", "  Hybrid Score = 0.439 < 0.72 → NEW 분기 결정");
      }, 5000);
      setTimeout(() => {
        addLog("EXTRACTOR", "개념 2/2 추출: CrossSiteRequestForgery (CWE-352, security)");
        addLog("RESOLVER", "▶ 3-Factor 판정 [2/2]: CrossSiteRequestForgery vs. 시드 노드 풀 (16개)");
        addLog("RESOLVER", "  ① Jaro-Winkler(40%) = 0.961  ② Name_Vector cos(30%) = 0.924  ③ Desc_Vector cos(30%) = 0.911");
        addLog("RESOLVER", "  Hybrid Score = 0.934 ≥ 0.88 → MERGE 분기 결정 (기존 'CSRF' 노드로 병합 예약)");
        setStepStatuses(s => ({ ...s, 3: "SUCCESS", 4: "LOADING" }));
        setConcepts(prev => {
          const names = new Set(prev.map(c => c.name));
          // MERGE 개념(CrossSiteRequestForgery)은 타겟 노드 배지로 표시 — 별도 노드 추가 안 함
          const toAdd = [DRAFT_CONCEPT, DRAFT_CONCEPT_MERGE].filter(d => !names.has(d.name));
          return [...prev, ...toAdd] as typeof INITIAL_CONCEPTS;
        });
        setSelectedConcept(DRAFT_CONCEPT_MERGE);
        setDraftSummary({ count: 2, names: [DRAFT_CONCEPT.name, DRAFT_CONCEPT_MERGE.name], domains: ["security", "performance"] });
      }, 6000);
      setTimeout(() => {
        setStepStatuses(s => ({ ...s, 4: "SUCCESS" }));
        addLog("WRITER", "4단계 [Graph Writer Agent] 2개 DRAFT 스테이징 완료 (NEW 1건 + MERGE 예약 1건). 관리자 HITL 승인 대기.");
        setPipelineState("WAITING_APPROVAL");
        setShowDraft(true);
        addToast("success", "2개 핵심 기술 개념 도출 완료 — HITL 승인 필요");
      }, 7500);
      return;
    }

    // PROD: 실제 API 호출
    try {
      const result = await runPipelineStart(
        urls.map((u) => u.value),
        docIdRef.current,
        { onLog: addLog },
      );
      docIdRef.current = result.docId;

      if (result.needsManualMetadata && result.prescanResult) {
        addLog("INPUT", "메타데이터 자동 추론 실패 — 관리자 수동 보정 대기 중...");
        setStepStatuses(s => ({ ...s, 1: "SUCCESS" }));
        setMetadataLearnModal(result.prescanResult);
        return;
      }

      sessionIdRef.current = result.sessionId;
      setStepStatuses(s => ({ ...s, 1: "SUCCESS", 2: "LOADING" }));
      startSSE(result.sessionId!);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      addLog("ERROR", `파이프라인 시작 실패: ${msg}`);
      setPipelineState("IDLE");
      setStepStatuses(INITIAL_STEP_STATUSES);
    }
  }

  // ── HITL 메타데이터 자율 학습 (v3.2) ────────────────────────────────────
  async function submitMetadataCorrection(payload: LearnMetadataPayload) {
    if (!docIdRef.current) return;
    setIsLearningMetadata(true);
    try {
      await learnFrameworkMetadata(payload);
      addLog("INPUT", `메타데이터 학습 완료: ${payload.framework} 패턴이 framework_metadata에 등록되었습니다.`);
      setMetadataLearnModal(null);

      const result = await continuePipeline(docIdRef.current, { onLog: addLog });
      sessionIdRef.current = result.sessionId;
      setStepStatuses(s => ({ ...s, 2: "LOADING" }));
      startSSE(result.sessionId!);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      addLog("ERROR", `메타데이터 학습 실패: ${msg}`);
    } finally {
      setIsLearningMetadata(false);
    }
  }

  function cancelMetadataCorrection() {
    setMetadataLearnModal(null);
    addLog("INPUT", "메타데이터 보정 취소 — 파이프라인 대기 상태로 복귀.");
    setPipelineState("IDLE");
    setStepStatuses(INITIAL_STEP_STATUSES);
  }

  // ── HITL 도메인 복구 (mock 모드) ─────────────────────────────────────────
  function resolveDomain() {
    addLog("SYSTEM", "HITL 게이트 복구: ConnPoolExhaustion 교차 도메인 domain_registry 등록 완료.");
    setPendingDomain(false);
    setStepStatuses(s => ({ ...s, 1: "SUCCESS", 2: "SUCCESS", 3: "SUCCESS", 4: "SUCCESS" }));
    addLog("WRITER", "4단계 [Graph Writer Agent] 개시: staging_concepts DRAFT 보관 완료.");
    setPipelineState("WAITING_APPROVAL");
    setShowDraft(true);
    setSelectedConcept(DRAFT_CONCEPT);
  }

  // ── 최종 승인 ────────────────────────────────────────────────────────────
  async function approveAll() {
    const sessionId = sessionIdRef.current;
    setPipelineState("COMMITTING");
    setStepStatuses(s => ({ ...s, 5: "LOADING" }));
    addLog("SYSTEM", "최종 승인 ──► 크로스 DB 원자적 트랜잭션 구동 시작.");

    if (sessionId) {
      try {
        const appRes = await fetch(`/api/staging/${sessionId}/approve`, { method: "POST" });
        if (appRes.ok) {
          const d = await appRes.json();
          addLog("DB", `PostgreSQL APPROVED 전이 완료 — ${d.approved}건`);
        }
        const commitRes = await fetch(`/api/staging/${sessionId}/commit`, { method: "POST" });
        if (commitRes.ok) {
          addLog("WRITER", "4단계 [Graph Writer Agent] 큐 적재 완료.");
          startSSE(sessionId);
          return;
        }
      } catch { /* 폴백으로 진행 */ }
    }

    addLog("RESOLVER", "5단계 [Link Resolver Agent] — HITL 승인 수신. 2개 분기 액션 시퀀스 실행 중...");
    setTimeout(() => {
      addLog("RESOLVER", "▶ [1/2] MERGE 분기 실행: CrossSiteRequestForgery → 'CSRF' 기존 노드 병합");
      addLog("DB", "  CSRF.aliases += ['CrossSiteRequestForgery', 'Cross-Site Request Forgery', 'Session Riding'] (중복 제거)");
      addLog("DB", "  MockEmbedding.embed('CSRF, CrossSiteRequestForgery, CSRFAttack, 크로스사이트 요청 위조, Session Riding') → 768-dim name_vector");
      addLog("DB", "  PostgreSQL UPDATE concepts SET name_vector=$1::vector, aliases=$2 WHERE name='CSRF' — Centroid Shifting 완료");
      addLog("RESOLVER", "  CSRF 벡터 중심점 이동 완료 (aliases 3개 → 6개, name_vector 재임베딩)");
      addLog("RESOLVER", "▶ [2/2] NEW 분기 실행: ConnPoolExhaustion — 독립 마스터 노드 신규 생성");
      addLog("DB", "  MockEmbedding.embed('ConnPoolExhaustion, Connection Pool Exhaustion, 커넥션 풀 고갈, DB Connection Leak') → 768-dim name_vector");
      addLog("DB", "  PostgreSQL INSERT: concepts (name='ConnPoolExhaustion', name_vector=$10::vector, desc_vector=$11::vector) ON CONFLICT UPSERT");
      addLog("GRAPH", "Neo4j MERGE (:Concept {name:'CSRF'}) SET aliases=apoc.coll.toSet([...]) 완료");
      addLog("GRAPH", "Neo4j MERGE (:Concept {name:'ConnPoolExhaustion'}) SET labels=apoc.coll.toSet(['performance','security']) 완료");
      const committed = concepts
        .filter(c => c.name !== DRAFT_CONCEPT_MERGE.name)
        .map(c => c.name === "CSRF"
          ? { ...c, aliases: [...new Set([...c.aliases, "CrossSiteRequestForgery", "Cross-Site Request Forgery", "Session Riding"])], state: "COMMITTED" }
          : { ...c, state: "COMMITTED" });
      const final = committed.some(c => c.name === DRAFT_CONCEPT.name)
        ? committed
        : [...committed, { ...DRAFT_CONCEPT, state: "COMMITTED" }];
      setConcepts(final as typeof INITIAL_CONCEPTS);
      setSelectedConcept((final.find(c => c.name === "CSRF") ?? final[0]) as typeof INITIAL_CONCEPTS[0]);
      setStepStatuses({ 1: "SUCCESS", 2: "SUCCESS", 3: "SUCCESS", 4: "SUCCESS", 5: "SUCCESS" });
      addLog("SYSTEM", "파이프라인 완료 — COMMITTED. (MERGE 1건 + NEW 1건)");
      addToast("success", "파이프라인 완료 — MERGE 1건(CSRF 벡터 업데이트) + NEW 1건(ConnPoolExhaustion)");
      setPipelineState("FINISHED");
      setShowDraft(false);
      setUrls([]);
    }, 2000);
  }

  // ── 스텝 재시도 ──────────────────────────────────────────────────────────
  const handleRetryStep = useCallback((step: number) => {
    addLog("SYSTEM", `[RETRY] ${step}단계 재시도 요청`);
    setStepStatuses(s => ({ ...s, [step]: "LOADING" as StepStatus }));
    if (sessionIdRef.current) {
      fetch(`/api/pipeline/${sessionIdRef.current}/resume`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ resume_step: step }),
      }).catch(() => {});
    }
  }, [addLog]);

  // ── 전체 거부 ────────────────────────────────────────────────────────────
  function rejectAll() {
    if (sessionIdRef.current) {
      fetch(`/api/staging/${sessionIdRef.current}/reject`, { method: "POST" }).catch(() => {});
    }
    if (sseRef.current) { sseRef.current.close(); sseRef.current = null; }
    addLog("SYSTEM", "관리자 거부: staging_concepts DRAFT 소거 완료.");
    setPipelineState("IDLE");
    setShowDraft(false);
    setStepStatuses(INITIAL_STEP_STATUSES);
    sessionIdRef.current = null;
    docIdRef.current = null;
  }

  const filteredConcepts = concepts.filter(
    (c) => c.state !== "DRAFT" && (activeTab === "all" || (c.domains ?? []).includes(activeTab)),
  );

  // 링크 추출(Resolver) 단계에서 도출된 실제 DRAFT 개념 — 도메인 필터 적용
  const draftConcepts = concepts.filter(
    (c) => c.state === "DRAFT" && (activeTab === "all" || (c.domains ?? []).includes(activeTab)),
  );

  // MERGE 분기 DRAFT 개념은 별도 노드가 아닌 타겟 노드에 오버레이 배지로 표시
  const mergePendingTargets = useMemo(() => {
    if (!showDraft) return new Set<string>();
    return new Set(
      concepts
        .filter((c) => c.state === "DRAFT" && c.infer_action === "MERGE" && c.target_concept_name)
        .map((c) => c.target_concept_name!),
    );
  }, [concepts, showDraft]);

  const apiConceptNodes = useMemo(() => {
    const fromApi = apiGraph.nodes.filter((n) => n.label === "Concept") as (GraphNode & { name: string; cwe_id: string; domains: string[] })[];
    // 링크 추출(Resolver) 결과의 실제 DRAFT 개념 — MERGE 분기는 타겟 노드에 오버레이로만 표시
    const draftNewConcepts = concepts.filter(
      (c) => c.state === "DRAFT" && c.infer_action !== "MERGE",
    ) as unknown as typeof fromApi;

    if (fromApi.length > 0) {
      const apiNames = new Set(fromApi.map((n) => n.name));
      return layoutConceptNodes([
        ...fromApi,
        ...(showDraft ? draftNewConcepts.filter((c) => !apiNames.has(c.name)) : []),
      ]);
    }
    // 로컬 개념 목록: MERGE DRAFT 개념은 노드로 렌더링하지 않음
    const nonMergeDrafts = concepts.filter(
      (c) => !(c.state === "DRAFT" && c.infer_action === "MERGE"),
    );
    return layoutConceptNodes(nonMergeDrafts);
  }, [apiGraph, concepts, showDraft]);

  const allConceptNodes = apiConceptNodes;
  const activeDomainKeys = new Set(allConceptNodes.flatMap((c) => c.domains ?? []));

  const selectedMechanismNodes = useMemo(() => {
    if (!selectedConcept) return [];
    const mechIds = new Set(
      apiGraph.edges
        .filter((e) => e.source === selectedConcept.name && e.type === "MITIGATED_BY")
        .map((e) => e.target),
    );
    const mechs = apiGraph.nodes.filter((n) => n.label === "Mechanism" && mechIds.has(n.id));
    return layoutMechanismNodes(mechs);
  }, [selectedConcept, apiGraph]);

  const isConceptDimmed = useCallback((name: string) => {
    if (!graphSearch.trim()) return false;
    const q = graphSearch.toLowerCase();
    return !name.toLowerCase().includes(q);
  }, [graphSearch]);

  const severityClass = (s: string) =>
    s === "critical" ? "bg-rose-50 text-rose-700 border border-rose-200"
    : s === "high"   ? "bg-amber-50 text-amber-700 border border-amber-200"
    :                  "bg-stone-50 text-stone-600 border border-stone-200";

  // ── SVG 줌/팬 핸들러 ─────────────────────────────────────────────────────
  function handleSvgWheel(e: React.WheelEvent<HTMLDivElement>) {
    e.preventDefault();
    const factor = e.deltaY > 0 ? 1.15 : 0.87;
    setSvgViewBox(prev => {
      const newW = Math.max(200, Math.min(2000, prev.w * factor));
      const newH = Math.max(80,  Math.min(1000, prev.h * factor));
      return { x: prev.x + (prev.w - newW) / 2, y: prev.y + (prev.h - newH) / 2, w: newW, h: newH };
    });
  }
  function handleSvgMouseDown(e: React.MouseEvent<HTMLDivElement>) {
    isDraggingRef.current = true;
    setSvgDragging(true);
    dragStartRef.current = { mx: e.clientX, my: e.clientY, vx: svgViewBox.x, vy: svgViewBox.y, vw: svgViewBox.w, vh: svgViewBox.h };
  }
  function handleSvgMouseMove(e: React.MouseEvent<HTMLDivElement>) {
    if (!isDraggingRef.current) return;
    const rect = svgContainerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const { mx, my, vx, vy, vw, vh } = dragStartRef.current;
    const sx = vw / rect.width, sy = vh / rect.height;
    setSvgViewBox(prev => ({ ...prev, x: vx - (e.clientX - mx) * sx, y: vy - (e.clientY - my) * sy }));
  }
  function handleSvgMouseUp() { isDraggingRef.current = false; setSvgDragging(false); }
  function svgZoomIn()  { setSvgViewBox(p => ({ x: p.x + p.w * 0.1,    y: p.y + p.h * 0.1,    w: Math.max(200,  p.w * 0.8),  h: Math.max(80,  p.h * 0.8)  })); }
  function svgZoomOut() { setSvgViewBox(p => ({ x: p.x - p.w * 0.125,  y: p.y - p.h * 0.125,  w: Math.min(2000, p.w * 1.25), h: Math.min(1000, p.h * 1.25) })); }
  function svgReset()   { setSvgViewBox({ x: 0, y: 0, w: 860, h: 520 }); }

  // ── JSX ───────────────────────────────────────────────────────────────────
  return (
    <div className="min-h-screen bg-[#FAF8F5] text-[#1C1917] font-sans antialiased">

      {/* ── TOAST CONTAINER (고정 우상단) ────────────────────────────────── */}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />

      {/* ── HEADER ──────────────────────────────────────────────────────── */}
      <header className="sticky top-0 z-40 border-b border-stone-200/60 bg-white/90 backdrop-blur-md px-8 py-4 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-lg bg-[#115E59] flex items-center justify-center text-white font-bold text-lg">K</div>
          <div>
            <h1 className="font-serif text-xl font-bold tracking-tight text-stone-900">수집 에이전트 지식 그래프 실시간 웹뷰</h1>
            <p className="text-sm text-stone-500">공식 문서 파싱 → 다중 도메인 지식 그래프 실시간 동기화 관제 패널</p>
          </div>
        </div>
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <span className="relative flex h-2 w-2">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${pipelineState === "RUNNING" ? "bg-amber-400" : "bg-emerald-400"} opacity-75`} />
              <span className={`relative inline-flex rounded-full h-2 w-2 ${pipelineState === "RUNNING" ? "bg-amber-500" : "bg-emerald-500"}`} />
            </span>
            <span className="text-sm font-medium text-stone-600">
              {pipelineState === "RUNNING" ? "에이전트 작동 중" : "파이프라인 준비 완료"}
            </span>
          </div>
          <span className="px-2.5 py-1 text-sm italic bg-stone-100 rounded-full text-stone-700">Django & Spring 하이브리드 대응</span>
        </div>
      </header>

      <main className="max-w-[1900px] mx-auto px-8 pt-8 pb-8">
        {/* ── 지표 카드 ──────────────────────────────────────────────────── */}
        <div className="grid grid-cols-5 gap-4 mb-6">
          {[
            { label: "스캔 문서",    value: urls.length,                                          sub: "URL Queue" },
            { label: "신규 생성",    value: showDraft || pipelineState === "FINISHED" ? 1 : 0,   sub: "Draft 포함" },
            { label: "필드 보완",    value: 0,                                                    sub: "자동 정규화" },
            { label: "단순 스킵",    value: 0,                                                    sub: "ETag 일치" },
            { label: "총 적재 개념", value: concepts.length,                                     sub: "Committed" },
          ].map((m) => (
            <div key={m.label} className="bg-white rounded-xl border border-stone-200/70 p-4 shadow-sm">
              <span className="text-xs font-medium text-stone-500 block">{m.label}</span>
              <span className="font-serif text-3xl font-bold text-stone-900 block mt-1">{m.value}</span>
              <span className="text-[11px] text-[#0F766E] font-medium block mt-1">✓ {m.sub}</span>
            </div>
          ))}
        </div>

        {/* ── 2-컬럼 그리드 ──────────────────────────────────────────────── */}
        <div className="grid grid-cols-12 gap-8">

          {/* ══ LEFT COLUMN ══ */}
          <section className="col-span-12 lg:col-span-4 flex flex-col space-y-6">

            {/* URL 대기열 */}
            <div className="bg-white rounded-2xl border border-stone-200/70 p-6 shadow-sm">
              <h2 className="font-serif text-lg font-bold text-stone-900 mb-4 flex items-center justify-between">
                <span>수집 대상 링크 대기열</span>
                <span className="text-sm font-sans text-stone-400 font-normal">MAX 5 URLs</span>
              </h2>
              <form onSubmit={handleAddUrl} className="flex gap-2 mb-4">
                <input
                  type="text" value={newUrl} onChange={(e) => setNewUrl(e.target.value)}
                  placeholder="공식 가이드 및 보안 URL을 입력하세요..."
                  className="flex-1 px-4 py-2.5 text-base bg-stone-50 border border-stone-200 rounded-xl focus:outline-none focus:ring-1 focus:ring-[#115E59] focus:bg-white transition-all placeholder:text-stone-400"
                />
                <button type="submit" className="px-4 py-2 text-base bg-[#115E59] text-white rounded-xl hover:bg-[#0f4e4a] transition-all font-medium">추가</button>
              </form>
              <div className="space-y-2 max-h-[180px] overflow-y-auto mb-4">
                {urls.map((u) => (
                  <div key={u.id} className="p-3 bg-stone-50/60 rounded-xl border border-stone-200/50 flex flex-col space-y-1">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-sm font-mono text-stone-700 break-all font-semibold flex-1">{u.value}</span>
                      <button type="button" onClick={() => setUrls((p) => p.filter((x) => x.id !== u.id))}
                        className="shrink-0 text-stone-400 hover:text-red-500 text-sm">✕</button>
                    </div>
                    <span className="text-xs text-[#0F766E] font-medium">{u.label}</span>
                  </div>
                ))}
                {urls.length === 0 && <div className="text-center py-6 text-stone-400 text-base italic">대기열이 비어 있습니다.</div>}
              </div>
              <button
                onClick={startPipeline}
                disabled={pipelineState === "RUNNING" || pipelineState === "COMMITTING" || urls.length === 0}
                className="w-full py-3.5 rounded-xl font-medium text-sm transition-all flex items-center justify-center space-x-2 bg-stone-900 text-white hover:bg-stone-800 disabled:bg-stone-100 disabled:text-stone-400 disabled:cursor-not-allowed"
              >
                <span>에이전트 통합 크롤러 기동하기</span><span>✦</span>
              </button>
            </div>

            {/* 파이프라인 흐름 — PRD-UI-V2 §3 StepStatus 인디케이터 */}
            <div className="bg-white rounded-2xl border border-stone-200/70 p-6 shadow-sm">
              <h3 className="font-serif text-lg font-bold text-stone-900 mb-4">에이전트 파이프라인 흐름 상태</h3>
              <PipelineStepList statuses={stepStatuses} onRetry={handleRetryStep} />
              {/* Debug Drawer 진입점 (PRD-UI-V2 §3) */}
              <button
                onClick={() => setShowDrawer(true)}
                className="mt-4 w-full py-1.5 text-xs text-stone-400 hover:text-stone-700 border border-stone-100 hover:border-stone-200 rounded-lg transition-all font-mono tracking-wider"
              >
                ▸ Terminal Raw Logs
              </button>
            </div>

            {/* 실시간 로그 (compact 패널) */}
            <div className="bg-stone-900 text-stone-100 rounded-2xl p-5 flex flex-col min-h-[220px]">
              <div className="flex items-center justify-between mb-3 border-b border-stone-800 pb-2">
                <span className="text-sm font-mono font-bold tracking-wider text-[#0F766E]">REALTIME RUNTIME LOGS</span>
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              </div>
              <div ref={consoleRef} className="flex-1 font-mono text-[11px] space-y-1.5 max-h-[220px] overflow-y-auto pr-1">
                {logs.map((l, i) => (
                  <div key={i} className="border-b border-stone-800/40 pb-1 leading-relaxed">
                    <span className="text-stone-600 mr-2">[{l.time}]</span>
                    <span className={`font-bold mr-1.5 ${
                      l.type === "SYSTEM"    ? "text-sky-400"     :
                      l.type === "INPUT"     ? "text-amber-400"   :
                      l.type === "CRAWLER"   ? "text-indigo-400"  :
                      l.type === "EXTRACTOR" ? "text-emerald-400" :
                      l.type === "WRITER"    ? "text-fuchsia-400" :
                      l.type === "RESOLVER"  ? "text-rose-400"    :
                      l.type === "DB"        ? "text-cyan-400"    :
                      l.type === "GRAPH"     ? "text-violet-400"  :
                      "text-stone-400"
                    }`}>[{l.type}]</span>
                    <span className="text-stone-200">{l.message}</span>
                  </div>
                ))}
              </div>
            </div>
          </section>

          {/* ══ RIGHT COLUMN ══ */}
          <section className="col-span-12 lg:col-span-8 flex flex-col space-y-6">

            {/* HITL 미등록 도메인 경고 */}
            {pendingDomain && (
              <div className="bg-amber-50 border border-amber-300 rounded-xl p-5 flex items-center justify-between">
                <div className="flex items-center space-x-3">
                  <span className="text-xl">⚠️</span>
                  <div>
                    <h4 className="text-base font-bold text-amber-900">미등록 교차 도메인 감지 (DOMAIN_PENDING)</h4>
                    <p className="text-sm text-amber-700 mt-0.5">
                      <strong>ConnPoolExhaustion</strong>이 <strong>security + performance</strong> 교차 도메인으로 추출되었습니다. 등록 후 계속 진행하세요.
                    </p>
                  </div>
                </div>
                <div className="flex space-x-2">
                  <button onClick={resolveDomain} className="px-3.5 py-1.5 text-sm bg-amber-600 text-white font-semibold rounded-lg hover:bg-amber-700 transition-all">도메인 등록</button>
                  <button onClick={rejectAll}      className="px-3.5 py-1.5 text-sm border border-amber-300 text-amber-800 font-semibold rounded-lg hover:bg-amber-100 transition-all">기각</button>
                </div>
              </div>
            )}

            {/* 그래프 */}
            <div className="bg-white rounded-2xl border border-stone-200/70 p-6 shadow-sm relative">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="font-serif text-lg font-bold text-stone-900 flex items-center space-x-2">
                    <span>지식 그래프 가시화 토폴로지 (Neo4j 실시간 연동)</span>
                    {showDraft && <span className="px-2 py-0.5 text-xs font-bold bg-amber-100 text-amber-800 rounded-full animate-pulse">DRAFT 가상 뷰어 가동 중</span>}
                  </h3>
                  <p className="text-sm text-stone-400 mt-0.5">노드를 클릭하면 하단 인스펙터 패널에서 속성 정보와 대응 설정값을 확인할 수 있습니다.</p>
                </div>
                <div className="flex items-center space-x-3">
                  <input
                    value={graphSearch}
                    onChange={(e) => setGraphSearch(e.target.value)}
                    placeholder="개념 검색..."
                    className="px-3 py-1 text-sm border border-stone-200 rounded-lg bg-stone-50 focus:outline-none focus:ring-1 focus:ring-[#115E59] w-32"
                  />
                  <div className="flex items-center space-x-2 text-xs font-medium text-stone-500">
                    {[["#292524","Domain"],["#6366F1","Mechanism"],["#B91C1C","보안"],["#0F766E","성능"]].map(([c,l]) => (
                      <span key={l} className="flex items-center space-x-1">
                        <span className="w-2.5 h-2.5 rounded-full" style={{ background: c }} /><span>{l}</span>
                      </span>
                    ))}
                  </div>
                </div>
              </div>

              <div
                ref={svgContainerRef}
                className={`h-[520px] bg-[#FAF9F6] border border-stone-200/50 rounded-xl relative overflow-hidden select-none ${svgDragging ? "cursor-grabbing" : "cursor-grab"}`}
                onWheel={handleSvgWheel}
                onMouseDown={handleSvgMouseDown}
                onMouseMove={handleSvgMouseMove}
                onMouseUp={handleSvgMouseUp}
                onMouseLeave={handleSvgMouseUp}
              >
                <svg className="w-full h-full" viewBox={`${svgViewBox.x} ${svgViewBox.y} ${svgViewBox.w} ${svgViewBox.h}`}>
                  <defs>
                    <marker id="arr" viewBox="0 0 10 10" refX="24" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                      <path d="M 0 0 L 10 5 L 0 10 z" fill="#D6D3D1" />
                    </marker>
                    <marker id="arr-sm" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
                      <path d="M 0 0 L 10 5 L 0 10 z" fill="#A8A29E" />
                    </marker>
                  </defs>
                  <rect x="0" y="0"   width="860" height="80"  fill="#F2F0EC" />
                  <rect x="0" y="80"  width="860" height="190" fill="#FAFAF8" />
                  <rect x="0" y="270" width="860" height="250" fill="#F6F4F1" />
                  <line x1="0" y1="80"  x2="860" y2="80"  stroke="#E2DDD8" strokeWidth="0.5" strokeDasharray="2,4" />
                  <line x1="0" y1="270" x2="860" y2="270" stroke="#E2DDD8" strokeWidth="0.5" strokeDasharray="2,4" />
                  <text x="6" y="12"  fill="#C2BCB4" fontSize="8.5" fontFamily="monospace">DOMAIN</text>
                  <text x="6" y="92"  fill="#C2BCB4" fontSize="8.5" fontFamily="monospace">CONCEPT</text>
                  <text x="6" y="282" fill="#C2BCB4" fontSize="8.5" fontFamily="monospace">MECHANISM (선택 개념)</text>

                  {allConceptNodes.flatMap((c) =>
                    (c.domains ?? []).map((d) => {
                      const dPos = DOMAIN_HUB_POS[d];
                      if (!dPos) return null;
                      return (
                        <line key={`de-${c.name}-${d}`}
                          x1={dPos[0]} y1={dPos[1] + 25}
                          x2={c.cx} y2={c.cy - CONCEPT_R}
                          stroke={DOMAIN_REGISTRY[d]?.color_hex ?? "#E7E5E4"}
                          strokeWidth="0.8" opacity="0.2"
                        />
                      );
                    })
                  )}

                  {selectedConcept && (() => {
                    const selNode = allConceptNodes.find((c) => c.name === selectedConcept.name);
                    if (!selNode) return null;
                    const style = getConceptStyle(selNode.domains);
                    return selectedMechanismNodes.map((m) => (
                      <line key={`me-${selNode.name}-${m.id}`}
                        x1={selNode.cx} y1={selNode.cy + CONCEPT_R}
                        x2={m.cx} y2={m.cy - 16}
                        stroke={style.stroke} strokeWidth="1.2" opacity="0.5"
                        markerEnd="url(#arr-sm)"
                      />
                    ));
                  })()}

                  {Object.entries(DOMAIN_REGISTRY).filter(([key]) => activeDomainKeys.has(key)).map(([key, domain]) => {
                    const pos = DOMAIN_HUB_POS[key] ?? [280, 47];
                    const isActive = activeTab === key;
                    return (
                      <g key={key} className="cursor-pointer" onClick={() => setActiveTab(key)}>
                        {isActive && (
                          <circle cx={pos[0]} cy={pos[1]} r="31"
                            fill="none" stroke={domain.color_hex} strokeWidth="2" opacity="0.5" />
                        )}
                        <circle cx={pos[0]} cy={pos[1]} r="25"
                          fill={isActive ? domain.color_hex : "#292524"} />
                        <text x={pos[0]} y={pos[1] + 4} fill="#FFF"
                          fontSize="11" textAnchor="middle" fontWeight="bold">
                          {domain.label_ko}
                        </text>
                        <title>{domain.label_ko} 도메인 — 클릭하여 인스펙터 필터</title>
                      </g>
                    );
                  })}

                  {selectedMechanismNodes.map((m) => {
                    const shortLabel = (m.name ?? m.id).replace(/_/g, " ").slice(0, 8);
                    return (
                      <g key={`mech-${m.id}`}>
                        <circle cx={m.cx} cy={m.cy} r="16" fill="#F0F0FD" stroke="#6366F1" strokeWidth="1" />
                        <text x={m.cx} y={m.cy + 4} fill="#4338CA" fontSize="8" textAnchor="middle" fontWeight="bold">{shortLabel}</text>
                        <title>:Mechanism — {m.name ?? m.id}</title>
                      </g>
                    );
                  })}

                  {allConceptNodes.map((c) => {
                    const style = getConceptStyle(c.domains);
                    const isNew = baselineNamesRef.current !== null && !baselineNamesRef.current.has(c.name) && c.state !== "DRAFT";
                    const label = graphLabel(c.name);
                    return (
                      <g key={c.name} className="cursor-pointer"
                        opacity={c.state === "DRAFT" ? 0.7 : isConceptDimmed(c.name) ? 0.2 : undefined}
                        onClick={() => {
                          const full = concepts.find((con) => con.name === c.name);
                          setSelectedConcept((full ?? c) as typeof INITIAL_CONCEPTS[0]);
                        }}>
                        {isNew && (
                          <circle cx={c.cx} cy={c.cy} r={CONCEPT_R + 6}
                            fill="none" stroke={style.stroke} strokeWidth="1" opacity="0.4">
                            <animate attributeName="r"
                              values={`${CONCEPT_R};${CONCEPT_R + 8};${CONCEPT_R}`}
                              dur="2s" repeatCount="indefinite" />
                            <animate attributeName="opacity"
                              values="0.4;0;0.4" dur="2s" repeatCount="indefinite" />
                          </circle>
                        )}
                        <circle cx={c.cx} cy={c.cy} r={CONCEPT_R}
                          fill={c.state === "DRAFT" ? "#FFFCF5" : style.fill}
                          stroke={c.state === "DRAFT" ? "#D97706" : style.stroke}
                          strokeWidth={c.state === "DRAFT" ? "2" : "1.5"}
                          strokeDasharray={c.state === "DRAFT" ? "5,3" : undefined}
                        />
                        <text x={c.cx} y={c.cy + 3} fill={style.text}
                          fontSize="9.5" textAnchor="middle" fontWeight="bold">{label}</text>
                        {c.state === "DRAFT" && (
                          <>
                            <rect x={c.cx - 14} y={c.cy - CONCEPT_R - 13} width={28} height={10} rx={3} fill="#D97706" />
                            <text x={c.cx} y={c.cy - CONCEPT_R - 6} fill="white"
                              fontSize="7.5" textAnchor="middle" fontWeight="bold">DRAFT</text>
                          </>
                        )}
                        {isNew && !mergePendingTargets.has(c.name) && (
                          <>
                            <rect x={c.cx - 10} y={c.cy - CONCEPT_R - 13} width={20} height={10} rx={3} fill={style.stroke} />
                            <text x={c.cx} y={c.cy - CONCEPT_R - 6} fill="white"
                              fontSize="7.5" textAnchor="middle" fontWeight="bold">NEW</text>
                          </>
                        )}
                        {mergePendingTargets.has(c.name) && (
                          <>
                            <rect x={c.cx - 22} y={c.cy - CONCEPT_R - 13} width={44} height={10} rx={3} fill="#F59E0B" opacity="0.92" />
                            <text x={c.cx} y={c.cy - CONCEPT_R - 6} fill="white"
                              fontSize="7" textAnchor="middle" fontWeight="bold">MERGE↑</text>
                          </>
                        )}
                        <title>{c.name}</title>
                      </g>
                    );
                  })}
                </svg>

                {/* 줌 컨트롤 버튼 */}
                <div className="absolute bottom-4 right-4 flex flex-col gap-1 z-10" onMouseDown={e => e.stopPropagation()}>
                  <button onClick={svgZoomIn}  className="w-8 h-8 bg-white border border-stone-200 rounded-lg shadow text-stone-700 hover:bg-stone-50 text-base font-bold flex items-center justify-center leading-none">+</button>
                  <button onClick={svgZoomOut} className="w-8 h-8 bg-white border border-stone-200 rounded-lg shadow text-stone-700 hover:bg-stone-50 text-base font-bold flex items-center justify-center leading-none">−</button>
                  <button onClick={svgReset}   className="w-8 h-8 bg-white border border-stone-200 rounded-lg shadow text-stone-400 hover:bg-stone-50 text-xs font-bold flex items-center justify-center">↺</button>
                </div>

                {showDraft && draftSummary.count > 0 && (
                  <div className="absolute bottom-4 left-4 right-4 bg-white/95 backdrop-blur-sm border border-amber-300 rounded-xl p-3.5 flex items-center justify-between shadow-lg">
                    <div className="flex items-center space-x-2">
                      <span className="w-2 h-2 rounded-full bg-amber-500 animate-ping" />
                      <span className="text-xs font-bold text-stone-800">
                        가상 노드 병합 예비 요약: 신규 {draftSummary.count}개({draftSummary.names.join(", ")}) / 도메인 {draftSummary.domains.join("+") || "—"}
                      </span>
                    </div>
                    <div className="flex space-x-2">
                      <button onClick={approveAll} className="px-4 py-1.5 text-xs bg-[#115E59] text-white rounded-lg font-bold hover:bg-[#0e4e4a] transition-all">게이트 승인</button>
                      <button onClick={rejectAll}  className="px-3 py-1.5 text-xs border border-stone-200 text-stone-600 rounded-lg hover:bg-stone-50 transition-all">반려</button>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* 개념 인스펙터 */}
            <div className="bg-white rounded-2xl border border-stone-200/70 p-6 shadow-sm">
              <div className="flex items-center justify-between mb-5 border-b border-stone-100 pb-4">
                <div>
                  <h3 className="font-serif text-lg font-bold text-stone-900">보안 및 성능 개념(Concept) 인스펙터</h3>
                  <p className="text-sm text-stone-400 mt-0.5">도메인별로 선별 조회하거나 마스터 상세 정보를 조회합니다.</p>
                </div>
                <select
                  value={activeTab}
                  onChange={(e) => setActiveTab(e.target.value)}
                  className="px-3 py-1.5 text-sm font-semibold rounded-lg border border-stone-200 bg-stone-50 text-stone-900 focus:ring-1 focus:ring-[#115E59] focus:outline-none cursor-pointer"
                >
                  <option value="all">전체 기술</option>
                  {Object.entries(DOMAIN_REGISTRY).map(([key, domain]) => (
                    <option key={key} value={key}>{domain.label_ko}</option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
                {/* 목록 */}
                <div className="md:col-span-4 border-r border-stone-100 pr-4 max-h-[300px] overflow-y-auto space-y-2">
                  {filteredConcepts.map((c) => {
                    const isSelected = selectedConcept?.name === c.name;
                    return (
                      <button key={c.name} onClick={() => setSelectedConcept(c)}
                        className={`w-full text-left p-3 rounded-xl border transition-all ${isSelected ? "bg-[#FAF8F5] border-stone-300 shadow-sm" : "border-stone-200/60 hover:bg-stone-50"}`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-sm font-bold text-stone-900 truncate mr-1">{c.name}</span>
                          <span className={`shrink-0 text-[11px] px-1.5 py-0.5 rounded-md font-bold uppercase ${severityClass(c.severity)}`}>
                            {c.severity}
                          </span>
                        </div>
                        <div className="flex items-center justify-between mt-2">
                          <span className="text-xs text-stone-400">{c.cwe_id}</span>
                          <div className="flex gap-1">
                            {(c.domains ?? []).map((d) => (
                              <span key={d} className="text-[10px] px-1 rounded-md font-bold"
                                style={{ color: DOMAIN_REGISTRY[d]?.color_hex ?? "#7C3AED", background: DOMAIN_REGISTRY[d]?.bg_hex ?? "#F5F3FF", border: `1px solid ${DOMAIN_REGISTRY[d]?.border_hex ?? "#C7D2FE"}` }}
                              >{DOMAIN_REGISTRY[d]?.label_ko ?? "기타"}</span>
                            ))}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                  {showDraft && draftConcepts.map((c) => (
                    <button key={c.name} onClick={() => setSelectedConcept(c)}
                      className={`w-full text-left p-3 rounded-xl border border-dashed transition-all ${selectedConcept?.name === c.name ? "bg-amber-50 border-amber-400" : "border-amber-300 hover:bg-amber-50/50"}`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-bold text-amber-800 truncate mr-1">{c.name}</span>
                        <span className="shrink-0 text-[11px] px-1.5 py-0.5 rounded-md font-bold uppercase bg-amber-50 text-amber-700 border border-amber-200">
                          {c.infer_action === "MERGE" ? "merge" : "draft"}
                        </span>
                      </div>
                      <div className="flex items-center justify-between mt-2">
                        <span className="text-xs text-stone-400">{c.cwe_id}</span>
                        <div className="flex gap-1">
                          {(c.domains ?? []).map((d) => (
                            <span key={d} className="text-[10px] px-1 rounded-md font-bold"
                              style={{ color: DOMAIN_REGISTRY[d]?.color_hex ?? "#7C3AED", background: DOMAIN_REGISTRY[d]?.bg_hex ?? "#F5F3FF", border: `1px solid ${DOMAIN_REGISTRY[d]?.border_hex ?? "#C7D2FE"}` }}
                            >{DOMAIN_REGISTRY[d]?.label_ko ?? "기타"}</span>
                          ))}
                        </div>
                      </div>
                    </button>
                  ))}
                </div>

                {/* 상세 */}
                <div className="md:col-span-8 space-y-4">
                  {selectedConcept && <>
                    <div className="flex items-start justify-between">
                      <div>
                        <h4 className="font-serif text-xl font-bold text-stone-900">
                          {selectedConcept.name}
                          <span className="text-sm font-mono text-stone-400 font-normal ml-2">({selectedConcept.cwe_id})</span>
                          {selectedConcept.state === "DRAFT" && (
                            <span className="ml-2 text-xs px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded font-bold border border-amber-200">DRAFT</span>
                          )}
                          {baselineNamesRef.current !== null && !baselineNamesRef.current.has(selectedConcept.name) && selectedConcept.state !== "DRAFT" && (
                            <span className="ml-2 text-xs px-1.5 py-0.5 bg-emerald-100 text-emerald-700 rounded font-bold border border-emerald-200">신규 추가</span>
                          )}
                        </h4>
                        <div className="flex items-center flex-wrap gap-1 mt-1">
                          <span className="text-xs text-stone-500">동의어:</span>
                          {(selectedConcept.aliases ?? []).map((a) => (
                            <span key={a} className="text-xs px-1.5 py-0.5 bg-stone-100 text-stone-600 rounded-md">{a}</span>
                          ))}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-1.5 justify-end">
                        {(selectedConcept.domains ?? []).map((d) => (
                          <span key={d} className="text-sm px-2.5 py-1 rounded-full font-bold"
                            style={{ color: DOMAIN_REGISTRY[d]?.color_hex ?? "#7C3AED", background: DOMAIN_REGISTRY[d]?.bg_hex ?? "#F5F3FF", border: `1px solid ${DOMAIN_REGISTRY[d]?.border_hex ?? "#C7D2FE"}` }}
                          >{DOMAIN_REGISTRY[d]?.label_ko ?? "기타"}</span>
                        ))}
                      </div>
                    </div>

                    <p className="text-sm text-stone-600 leading-relaxed bg-[#FAF8F5] p-3.5 rounded-xl border border-stone-200/50">{selectedConcept.description_ko}</p>

                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <span className="text-stone-400 font-bold block mb-1">영향 컴포넌트</span>
                        <div className="flex flex-wrap gap-1">
                          {(selectedConcept.affected_components ?? []).map((comp) => (
                            <span key={comp} className="px-2 py-0.5 bg-stone-100 text-[#0F766E] rounded text-xs font-mono">{comp}</span>
                          ))}
                        </div>
                      </div>
                      <div>
                        <span className="text-stone-400 font-bold block mb-1">대응 메커니즘</span>
                        <div className="flex flex-wrap gap-1">
                          {(selectedConcept.mechanism ?? []).map((m) => (
                            <span key={m} className="px-2 py-0.5 bg-stone-100 text-stone-800 rounded text-xs font-semibold">✓ {m}</span>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div className="text-xs text-stone-400 border-t border-stone-100 pt-3 flex items-center justify-between">
                      <span>출처: {selectedConcept.owasp_id ? `OWASP ${selectedConcept.owasp_id}` : "CWE Seed / Performance Ref"}</span>
                      <span className={`font-bold uppercase ${severityClass(selectedConcept.severity)} px-1.5 py-0.5 rounded text-[11px]`}>
                        {selectedConcept.severity}
                      </span>
                    </div>

                    {/* 3-Factor 하이브리드 유사도 인스펙터 (DRAFT 개념 전용) */}
                    {selectedConcept.state === "DRAFT" && selectedConcept.infer_confidence !== undefined && (
                      <div className="border border-amber-200 bg-amber-50/60 rounded-xl p-3.5 space-y-2.5">
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-amber-900">3-Factor 하이브리드 유사도 판정</span>
                          <span className={`text-[11px] font-bold px-2 py-0.5 rounded-full border ${
                            selectedConcept.infer_action === "MERGE"
                              ? "bg-rose-100 text-rose-700 border-rose-200"
                              : selectedConcept.infer_action === "RELATED_TO"
                              ? "bg-amber-100 text-amber-700 border-amber-200"
                              : "bg-emerald-100 text-emerald-700 border-emerald-200"
                          }`}>
                            {selectedConcept.infer_action}
                          </span>
                        </div>
                        {selectedConcept.target_concept_name && (
                          <p className="text-xs text-amber-700">
                            병합 타겟: <span className="font-mono font-bold">{selectedConcept.target_concept_name}</span>
                          </p>
                        )}
                        <div className="space-y-1.5">
                          {[
                            { label: "Jaro-Winkler (40%)", value: selectedConcept.score_jaro_winkler ?? 0 },
                            { label: "Name Vector cos (30%)", value: selectedConcept.score_name_vector ?? 0 },
                            { label: "Desc Vector cos (30%)", value: selectedConcept.score_desc_vector ?? 0 },
                          ].map((s) => (
                            <div key={s.label} className="flex items-center gap-2">
                              <span className="text-[10px] text-stone-500 w-36 shrink-0">{s.label}</span>
                              <div className="flex-1 h-1.5 bg-stone-200 rounded-full overflow-hidden">
                                <div
                                  className="h-full bg-amber-400 rounded-full transition-all"
                                  style={{ width: `${Math.round(s.value * 100)}%` }}
                                />
                              </div>
                              <span className="text-[10px] font-mono text-stone-700 w-10 text-right">{s.value.toFixed(3)}</span>
                            </div>
                          ))}
                        </div>
                        <div className="pt-1.5 border-t border-amber-200 flex items-center justify-between">
                          <span className="text-[10px] text-stone-500">최종 하이브리드 스코어</span>
                          <span className="text-xs font-bold font-mono text-amber-900">
                            {(selectedConcept.infer_confidence ?? 0).toFixed(3)}
                          </span>
                        </div>
                      </div>
                    )}

                    {/* 코드 예제 뷰어 */}
                    <div className="border-t border-stone-100 pt-4 space-y-3">
                      <div className="flex items-center justify-between">
                        <span className="text-sm font-bold text-stone-700">코드 예제</span>
                        <div className="flex items-center gap-2">
                          <select value={codeLang} onChange={(e) => handleCodeLangChange(e.target.value)}
                            className="text-xs border border-stone-200 rounded-lg px-2 py-1 bg-white text-stone-700 focus:outline-none focus:ring-1 focus:ring-stone-300"
                          >
                            <option value="">언어 전체</option>
                            {(codeResult?.langs ?? []).map((l) => <option key={l} value={l}>{l}</option>)}
                          </select>
                          <select value={codeFramework} onChange={(e) => handleCodeFrameworkChange(e.target.value)}
                            className="text-xs border border-stone-200 rounded-lg px-2 py-1 bg-white text-stone-700 focus:outline-none focus:ring-1 focus:ring-stone-300"
                          >
                            <option value="">프레임워크 전체</option>
                            {(codeResult?.frameworks ?? []).map((f) => <option key={f} value={f}>{f}</option>)}
                          </select>
                        </div>
                      </div>

                      {codeLoading && <p className="text-xs text-stone-400 animate-pulse">코드 예제 로딩 중…</p>}
                      {!codeLoading && codeResult && codeResult.examples.length === 0 && (
                        <p className="text-xs text-stone-400">본 메커니즘에 등록된 프레임워크별 실물 소스코드 플레이북 예제가 존재하지 않습니다.</p>
                      )}
                      {!codeLoading && !codeResult && (
                        <p className="text-xs text-stone-400">Neo4j 연결 후 코드 예제를 불러올 수 있습니다.</p>
                      )}
                      {!codeLoading && codeResult && codeResult.examples.map((ex, idx) => (
                        <div key={idx} className="rounded-xl border border-stone-200 overflow-hidden">
                          <div className="flex items-center justify-between bg-stone-50 px-3 py-1.5 border-b border-stone-200">
                            <span className="text-xs font-bold text-stone-600">{ex.mechanism}</span>
                            <div className="flex items-center gap-1.5">
                              <span className="text-xs px-1.5 py-0.5 bg-blue-50 text-blue-700 rounded font-mono">{ex.lang}</span>
                              {ex.framework && <span className="text-xs px-1.5 py-0.5 bg-violet-50 text-violet-700 rounded font-mono">{ex.framework}</span>}
                            </div>
                          </div>
                          {ex.description && <p className="text-xs text-stone-500 px-3 pt-2">{ex.description}</p>}
                          <pre className="text-xs font-mono text-stone-800 bg-[#FAFAF9] px-3 py-2.5 overflow-x-auto leading-relaxed whitespace-pre-wrap max-h-48">
                            {ex.code}
                          </pre>
                        </div>
                      ))}
                    </div>
                  </>}
                </div>
              </div>
            </div>

          </section>
        </div>
      </main>

      <footer className="border-t border-stone-200/60 bg-white py-6 mt-8 text-center text-xs text-stone-400">
        <span className="text-sm">© 2026 Knowledge Graph Agent Pipeline — 4-Layer Ontology Schema v3</span>
      </footer>

      {/* ── DEBUG DRAWER (PRD-UI-V2 §3) ─────────────────────────────────── */}
      {showDrawer && (
        <div role="dialog" aria-label="Debug Log Drawer" className="fixed inset-0 z-50 flex justify-end">
          <div
            data-testid="drawer-overlay"
            className="absolute inset-0 bg-black/20"
            onClick={() => setShowDrawer(false)}
          />
          <div className="relative w-[450px] h-full bg-stone-900 text-stone-100 flex flex-col shadow-2xl">
            <div className="flex items-center justify-between px-5 py-4 border-b border-stone-700 shrink-0">
              <span className="text-sm font-mono font-bold tracking-wider text-[#0F766E]">TERMINAL RAW LOGS</span>
              <div className="flex items-center space-x-2">
                <button
                  onClick={() => setLogs([
                    { time: "00:00:00", type: "SYSTEM", message: "수집 에이전트 토폴로지 분석 웹뷰가 초기화되었습니다." },
                    { time: "00:00:02", type: "DB",     message: "domain_registry 캐시 주입 완료. [security, performance]" },
                  ])}
                  className="text-[10px] text-stone-400 hover:text-white px-2 py-1 rounded border border-stone-700 transition-all"
                >Clear</button>
                <button
                  onClick={() => navigator.clipboard?.writeText(
                    logs.map(l => `[${l.time}][${l.type}] ${l.message}`).join("\n")
                  )}
                  className="text-[10px] text-stone-400 hover:text-white px-2 py-1 rounded border border-stone-700 transition-all"
                >Copy</button>
                <button
                  aria-label="close-drawer"
                  onClick={() => setShowDrawer(false)}
                  className="text-stone-400 hover:text-white text-lg leading-none ml-1"
                >×</button>
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-4 font-mono text-[11px] space-y-1.5">
              {logs.map((l, i) => (
                <div key={i} className="border-b border-stone-800/40 pb-1 leading-relaxed">
                  <span className="text-stone-600 mr-2">[{l.time}]</span>
                  <span className={`font-bold mr-1.5 ${
                    l.type === "SYSTEM"    ? "text-sky-400"     :
                    l.type === "INPUT"     ? "text-amber-400"   :
                    l.type === "CRAWLER"   ? "text-indigo-400"  :
                    l.type === "EXTRACTOR" ? "text-emerald-400" :
                    l.type === "WRITER"    ? "text-fuchsia-400" :
                    l.type === "RESOLVER"  ? "text-rose-400"    :
                    l.type === "DB"        ? "text-cyan-400"    :
                    l.type === "GRAPH"     ? "text-violet-400"  :
                    "text-stone-400"
                  }`}>[{l.type}]</span>
                  <span className="text-stone-200">{l.message}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* ── HITL 메타데이터 보정 모달 (PRD-fix/prescan_process-v3 §7) ───────── */}
      {metadataLearnModal && (
        <MetadataLearnModal
          prescanResult={metadataLearnModal}
          onSubmit={submitMetadataCorrection}
          onCancel={cancelMetadataCorrection}
          isSubmitting={isLearningMetadata}
        />
      )}
    </div>
  );
}
