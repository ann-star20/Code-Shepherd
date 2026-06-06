import { useState, useEffect, useRef, useCallback } from "react";

// ── 도메인 레지스트리 ────────────────────────────────────────────────────────
const DOMAIN_REGISTRY: Record<string, { label_ko: string; color_hex: string; bg_hex: string; border_hex: string }> = {
  security:    { label_ko: "보안",  color_hex: "#B91C1C", bg_hex: "#FEF2F2", border_hex: "#FCA5A5" },
  performance: { label_ko: "성능",  color_hex: "#0F766E", bg_hex: "#F0FDF4", border_hex: "#86EFAC" },
};

// ── 시드 기반 Concept 초기 데이터 (security_concepts.json + perf_concepts.json) ──
const INITIAL_CONCEPTS = [
  {
    name: "SQLi", concept_type: "vulnerability_root_cause",
    cwe_id: "CWE-89", owasp_id: "A03:2025", severity: "critical",
    description_ko: "SQL 인젝션. 사용자 입력이 SQL 쿼리에 비위생화된 채 삽입되어 임의 쿼리 실행 또는 데이터 탈취가 가능함.",
    aliases: ["SQL Injection", "SQL 인젝션"],
    affected_components: ["database_access_layer", "orm_core_layer"],
    security_mechanisms: ["parameterized_query", "orm_use_rules", "input_validation"],
    domains: ["security"], state: "COMMITTED",
  },
  {
    name: "XSS", concept_type: "vulnerability_root_cause",
    cwe_id: "CWE-79", owasp_id: "A03:2025", severity: "high",
    description_ko: "크로스 사이트 스크립팅. 사용자 입력값이 HTML 컨텍스트에서 이스케이프 처리 없이 출력되어 공격자가 악성 스크립트를 삽입함.",
    aliases: ["Cross-Site Scripting", "크로스 사이트 스크립팅"],
    affected_components: ["template_rendering_layer", "api_response_serialization"],
    security_mechanisms: ["output_encoding", "content_security_policy", "httponly_cookie"],
    domains: ["security"], state: "COMMITTED",
  },
  {
    name: "CSRF", concept_type: "vulnerability_root_cause",
    cwe_id: "CWE-352", owasp_id: "A01:2025", severity: "high",
    description_ko: "크로스 사이트 요청 위조. 인증된 사용자의 브라우저를 통해 공격자가 원하는 요청을 의도치 않게 전송하게 만드는 취약점.",
    aliases: ["Cross-Site Request Forgery", "크로스 사이트 요청 위조"],
    affected_components: ["authentication_filter", "session_management_layer", "api_endpoint"],
    security_mechanisms: ["csrf_token_protection", "samesite_cookie_attribute", "double_submit_cookie"],
    domains: ["security"], state: "COMMITTED",
  },
  {
    name: "N+1Query", concept_type: "performance_antipattern",
    cwe_id: "CWE-1072", owasp_id: "", severity: "high",
    description_ko: "ORM 관계 조회 시 루프마다 추가 쿼리가 N번 실행되어 DB에 과부하를 유발하는 안티패턴. select_related/prefetch_related로 해결.",
    aliases: ["N+1 Problem", "N+1 Query", "N+1 쿼리 문제"],
    affected_components: ["orm_layer", "database_layer"],
    security_mechanisms: ["select_related", "prefetch_related", "eager_loading"],
    domains: ["performance"], state: "COMMITTED",
  },
  {
    name: "BrokenAccessControl", concept_type: "vulnerability_root_cause",
    cwe_id: "CWE-284", owasp_id: "A01:2025", severity: "critical",
    description_ko: "취약한 접근 제어. 최소 권한 원칙 미준수, IDOR 등으로 인증된 사용자가 허용되지 않은 리소스에 접근.",
    aliases: ["Broken Access Control", "IDOR", "취약한 접근 제어"],
    affected_components: ["authentication_filter", "api_endpoint", "database_access_layer"],
    security_mechanisms: ["rbac_rules", "abac_rules", "middleware_authorization"],
    domains: ["security"], state: "COMMITTED",
  },
  {
    name: "MissingIndex", concept_type: "performance_antipattern",
    cwe_id: "CWE-1052", owasp_id: "", severity: "high",
    description_ko: "인덱스 미설정으로 인한 Full Table Scan 발생. 데이터 증가에 비례하여 응답 지연이 급격히 악화됨.",
    aliases: ["Missing Database Index", "인덱스 누락", "Full Table Scan"],
    affected_components: ["database_layer", "query_execution_plan"],
    security_mechanisms: ["composite_index", "explain_analyze", "query_optimizer"],
    domains: ["performance"], state: "COMMITTED",
  },
];

// DRAFT: 교차 도메인(security+performance) — HITL 승인 시연용
const DRAFT_CONCEPT = {
  name: "ConnPoolExhaustion", concept_type: "performance_antipattern",
  cwe_id: "CWE-400", owasp_id: "", severity: "critical",
  description_ko: "커넥션 반환 실패 또는 풀 설정 미흡으로 DB 커넥션 풀이 고갈되어 새로운 요청이 대기 또는 실패. 보안·성능 양 도메인에 걸치는 자원 고갈 취약점.",
  aliases: ["Connection Pool Exhaustion", "커넥션 풀 고갈", "DB Connection Leak"],
  affected_components: ["connection_pool", "database_layer", "middleware"],
  security_mechanisms: ["context_manager_pattern", "pool_monitoring", "connection_timeout"],
  domains: ["security", "performance"], state: "DRAFT",
};

type PipelineState = "IDLE" | "RUNNING" | "WAITING_APPROVAL" | "COMMITTING" | "FINISHED";

function detectFramework(url: string): string {
  const u = url.toLowerCase();
  if (u.includes("spring"))  return "Spring Framework 명세 자동 추론";
  if (u.includes("django"))  return "Django Framework 명세 자동 추론";
  if (u.includes("react"))   return "React 문서 패턴 적용";
  if (u.includes("fastapi")) return "FastAPI 명세 자동 추론";
  return "범용 가이드라인 분석 패턴 적용";
}

type ApiConcept = {
  id: string; state: string; concept_name: string; domains: string[];
  concept_type?: string; cwe_id?: string; owasp_id?: string; severity?: string;
  description_ko?: string; aliases?: string[]; affected_components?: string[];
  security_mechanisms?: string[];
};

function mapApiConcept(item: ApiConcept) {
  return {
    name: item.concept_name, concept_type: item.concept_type ?? "vulnerability_root_cause",
    cwe_id: item.cwe_id ?? "", owasp_id: item.owasp_id ?? "",
    severity: item.severity ?? "medium", description_ko: item.description_ko ?? "",
    aliases: item.aliases ?? [], affected_components: item.affected_components ?? [],
    security_mechanisms: item.security_mechanisms ?? [],
    domains: item.domains, state: item.state,
  };
}

const DOC_STATE_TO_STEP: Record<string, number> = {
  CRAWLING: 2, EXTRACTED: 3, COMMITTED: 5, FAILED: 0,
};

export function MainPage() {
  const [urls, setUrls] = useState([
    { id: 1, value: "https://docs.djangoproject.com/en/6.0/topics/security/",      label: "Django Core Security 명세 감지" },
    { id: 2, value: "https://docs.spring.io/spring-security/reference/reactive/", label: "Spring Security Reactive 명세 감지" },
  ]);
  const [newUrl, setNewUrl]               = useState("");
  const [pipelineState, setPipelineState] = useState<PipelineState>("IDLE");
  const [currentStep, setCurrentStep]     = useState(0);
  const [logs, setLogs] = useState([
    { time: "00:00:00", type: "SYSTEM", message: "수집 에이전트 토폴로지 분석 웹뷰가 초기화되었습니다." },
    { time: "00:00:02", type: "DB",     message: "domain_registry 캐시 주입 완료. [security, performance]" },
  ]);
  const [concepts, setConcepts]           = useState(INITIAL_CONCEPTS);
  const [selectedConcept, setSelectedConcept] = useState<typeof INITIAL_CONCEPTS[0] | typeof DRAFT_CONCEPT>(INITIAL_CONCEPTS[0]);
  const [showDraft, setShowDraft]         = useState(false);
  const [activeTab, setActiveTab]         = useState("all");
  const [pendingDomain, setPendingDomain] = useState(false);
  const consoleRef   = useRef<HTMLDivElement>(null);
  const pollRef      = useRef<ReturnType<typeof setInterval> | null>(null);
  const sessionIdRef = useRef<string | null>(null);
  const docIdRef     = useRef<string | null>(null);

  useEffect(() => { consoleRef.current?.scrollIntoView({ behavior: "smooth" }); }, [logs]);
  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  function addLog(type: string, message: string) {
    const t = new Date().toTimeString().slice(0, 8);
    setLogs((prev) => [...prev, { time: t, type, message }]);
  }

  const startPolling = useCallback((sessionId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/pipeline/logs/${sessionId}`);
        if (!res.ok) return;
        const data = await res.json();
        const docState: string | null = data.doc_state;

        const newEntries: { time: string; type: string; message: string }[] = [];
        for (const l of data.logs ?? []) {
          newEntries.push({ time: l.ts.slice(11, 19), type: l.agent.toUpperCase(), message: l.message });
        }
        setLogs((prev) => {
          const existing = new Set(prev.map((e) => e.message));
          return [...prev, ...newEntries.filter((e) => !existing.has(e.message))];
        });

        if (docState && DOC_STATE_TO_STEP[docState] !== undefined) {
          setCurrentStep(DOC_STATE_TO_STEP[docState]);
        }

        if (docState === "EXTRACTED") {
          clearInterval(pollRef.current!);
          pollRef.current = null;
          const sRes = await fetch(`/api/staging/${sessionId}?all_states=true`);
          if (sRes.ok) {
            const sData = await sRes.json();
            const drafted = (sData.items as ApiConcept[]).map(mapApiConcept);
            if (drafted.length > 0) {
              setConcepts((prev) => {
                const names = new Set(prev.map((c) => c.name));
                return [...prev, ...drafted.filter((d) => !names.has(d.name))] as typeof INITIAL_CONCEPTS;
              });
              setSelectedConcept(drafted[0] as typeof DRAFT_CONCEPT);
            }
          }
          addLog("SYSTEM", "스테이징 적재 완료. 점선(DRAFT) 미리보기를 확인 후 승인하세요.");
          setCurrentStep(4);
          setPipelineState("WAITING_APPROVAL");
          setShowDraft(true);
        }

        if (docState === "COMMITTED") {
          clearInterval(pollRef.current!);
          pollRef.current = null;
          setConcepts((prev) => prev.map((c) => ({ ...c, state: "COMMITTED" })) as typeof INITIAL_CONCEPTS);
          setCurrentStep(5);
          addLog("SYSTEM", "파이프라인 완료 — COMMITTED");
          setPipelineState("FINISHED");
          setShowDraft(false);
          setUrls([]);
        }

        if (docState === "FAILED") {
          clearInterval(pollRef.current!);
          pollRef.current = null;
          addLog("ERROR", "파이프라인 오류 — FAILED");
          setPipelineState("IDLE");
        }
      } catch { /* 네트워크 오류 무시 */ }
    }, 2000);
  }, []);

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

  async function startPipeline() {
    if (urls.length === 0) return;
    setPipelineState("RUNNING");
    setCurrentStep(1);
    addLog("INPUT", "1단계 [Input Agent] 개시: 수집 링크 대기열 ETag 해시 검사 수행 중...");

    try {
      let docId = docIdRef.current;
      if (!docId) {
        const regRes = await fetch("/api/documents", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ urls: [urls[0].value] }),
        });
        if (!regRes.ok) throw new Error("문서 등록 실패");
        const regData = await regRes.json();
        docId = regData.documents[0].doc_id;
        docIdRef.current = docId;
      }

      const psRes = await fetch(`/api/documents/${docId}/prescan`, { method: "POST" });
      if (psRes.ok) {
        const ps = await psRes.json();
        addLog("INPUT", `프리스캔 완료: framework=${ps.framework ?? "unknown"}, confidence=${ps.infer_confidence?.toFixed(2)}`);
      }

      const trigRes = await fetch("/api/pipeline/trigger", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ doc_id: docId }),
      });
      if (!trigRes.ok) throw new Error(`트리거 실패: ${trigRes.status}`);
      const trigData = await trigRes.json();
      sessionIdRef.current = trigData.session_id;
      addLog("CRAWLER", `2단계 [Crawler Agent] 개시 — session: ${trigData.session_id.slice(0, 8)}...`);
      setCurrentStep(2);
      startPolling(trigData.session_id);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err);
      addLog("ERROR", `파이프라인 시작 실패: ${msg} — 시뮬레이션 모드로 전환`);
      setTimeout(() => { setCurrentStep(2); addLog("CRAWLER", "2단계 [Crawler Agent] DOM 파싱 완료."); }, 1500);
      setTimeout(() => { setCurrentStep(3); addLog("EXTRACTOR", "3단계 [Extractor Agent] 스키마 매핑 중..."); }, 3000);
      setTimeout(() => {
        addLog("EXTRACTOR", "DOMAIN_PENDING 감지 — ConnPoolExhaustion (security+performance 교차 도메인) 발견.");
        setPendingDomain(true);
        setPipelineState("WAITING_APPROVAL");
      }, 5000);
    }
  }

  function resolveDomain() {
    addLog("SYSTEM", "HITL 게이트 복구: ConnPoolExhaustion 교차 도메인 domain_registry 등록 완료.");
    setPendingDomain(false);
    setCurrentStep(4);
    addLog("WRITER", "4단계 [Graph Writer Agent] 개시: staging_concepts DRAFT 보관 완료.");
    setPipelineState("WAITING_APPROVAL");
    setShowDraft(true);
    setSelectedConcept(DRAFT_CONCEPT);
  }

  async function approveAll() {
    const sessionId = sessionIdRef.current;
    setPipelineState("COMMITTING");
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
          startPolling(sessionId);
          return;
        }
      } catch { /* 폴백으로 진행 */ }
    }

    setTimeout(() => {
      addLog("GRAPH", "Neo4j MERGE + APOC 라벨 결합 성공 — ConnPoolExhaustion [:Concept:security:performance]");
      const merged = [
        ...concepts.map((c) => ({ ...c, state: "COMMITTED" })),
        { ...DRAFT_CONCEPT, state: "COMMITTED" },
      ];
      setConcepts(merged as typeof INITIAL_CONCEPTS);
      setSelectedConcept({ ...DRAFT_CONCEPT, state: "COMMITTED" });
      setCurrentStep(5);
      addLog("RESOLVER", "5단계 [Link Resolver Agent] SAME_AS 결합 성공.");
      addLog("SYSTEM", "파이프라인 완료.");
      setPipelineState("FINISHED");
      setShowDraft(false);
      setUrls([]);
    }, 1500);
  }

  function rejectAll() {
    if (sessionIdRef.current) {
      fetch(`/api/staging/${sessionIdRef.current}/reject`, { method: "POST" }).catch(() => {});
    }
    addLog("SYSTEM", "관리자 거부: staging_concepts DRAFT 소거 완료.");
    setPipelineState("IDLE");
    setShowDraft(false);
    setCurrentStep(0);
    sessionIdRef.current = null;
    docIdRef.current = null;
  }

  const filteredConcepts = concepts.filter((c) =>
    activeTab === "all" || c.domains.includes(activeTab),
  );

  const STEPS = [
    { step: 1, title: "Input Agent",        desc: "링크 유효성 및 ETag 캐싱 분석" },
    { step: 2, title: "Crawler Agent",       desc: "DOM 파싱 및 텍스트 블록 정제" },
    { step: 3, title: "Extractor Agent",     desc: "Gemini 구조화 의미 스키마 추출" },
    { step: 4, title: "Graph Writer Agent",  desc: "PostgreSQL / Neo4j 멱등 적재" },
    { step: 5, title: "Link Resolver Agent", desc: "동의어 및 SAME_AS 유사도 병합" },
  ];

  const severityClass = (s: string) =>
    s === "critical" ? "bg-rose-50 text-rose-700 border border-rose-200"
    : s === "high"   ? "bg-amber-50 text-amber-700 border border-amber-200"
    :                  "bg-stone-50 text-stone-600 border border-stone-200";

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-[#1C1917] font-sans antialiased">

      {/* ── HEADER (fixed) ── */}
      <header className="fixed top-0 left-0 right-0 z-40 border-b border-stone-200/60 bg-white/90 backdrop-blur-md px-8 py-4 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-lg bg-[#115E59] flex items-center justify-center text-white font-bold text-lg">K</div>
          <div>
            <h1 className="font-serif text-lg font-bold tracking-tight text-stone-900">수집 에이전트 지식 그래프 실시간 웹뷰</h1>
            <p className="text-xs text-stone-500">공식 문서 파싱 → 다중 도메인 지식 그래프 실시간 동기화 관제 패널</p>
          </div>
        </div>
        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <span className="relative flex h-2 w-2">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${pipelineState === "RUNNING" ? "bg-amber-400" : "bg-emerald-400"} opacity-75`} />
              <span className={`relative inline-flex rounded-full h-2 w-2 ${pipelineState === "RUNNING" ? "bg-amber-500" : "bg-emerald-500"}`} />
            </span>
            <span className="text-xs font-medium text-stone-600">
              {pipelineState === "RUNNING" ? "에이전트 작동 중" : "파이프라인 준비 완료"}
            </span>
          </div>
          <span className="px-2.5 py-1 text-xs italic bg-stone-100 rounded-full text-stone-700">Django & Spring 하이브리드 대응</span>
        </div>
      </header>

      {/* ── MAIN: pt-20 = fixed 헤더 높이(~72px) 확보 ── */}
      <main className="max-w-[1600px] mx-auto px-8 pt-20 pb-8">

        {/* ── 지표 카드 (full-width, 두 컬럼 위) ── */}
        <div className="grid grid-cols-5 gap-4 mb-6">
          {[
            { label: "스캔 문서",    value: urls.length,                                          sub: "URL Queue" },
            { label: "신규 생성",    value: showDraft || pipelineState === "FINISHED" ? 1 : 0,   sub: "Draft 포함" },
            { label: "필드 보완",    value: 0,                                                    sub: "자동 정규화" },
            { label: "단순 스킵",    value: 0,                                                    sub: "ETag 일치" },
            { label: "총 적재 개념", value: concepts.length,                                     sub: "Committed" },
          ].map((m) => (
            <div key={m.label} className="bg-white rounded-xl border border-stone-200/70 p-4 shadow-sm">
              <span className="text-[11px] font-medium text-stone-500 block">{m.label}</span>
              <span className="font-serif text-2xl font-bold text-stone-900 block mt-1">{m.value}</span>
              <span className="text-[9px] text-[#0F766E] font-medium block mt-1">✓ {m.sub}</span>
            </div>
          ))}
        </div>

        {/* ── 2-컬럼 그리드 ── */}
        <div className="grid grid-cols-12 gap-8">

          {/* ══ LEFT COLUMN ══ */}
          <section className="col-span-12 lg:col-span-4 flex flex-col space-y-6">

            {/* URL 대기열 */}
            <div className="bg-white rounded-2xl border border-stone-200/70 p-6 shadow-sm">
              <h2 className="font-serif text-base font-bold text-stone-900 mb-4 flex items-center justify-between">
                <span>수집 대상 링크 대기열</span>
                <span className="text-xs font-sans text-stone-400 font-normal">MAX 5 URLs</span>
              </h2>
              <form onSubmit={handleAddUrl} className="flex gap-2 mb-4">
                <input
                  type="text" value={newUrl} onChange={(e) => setNewUrl(e.target.value)}
                  placeholder="공식 가이드 및 보안 URL을 입력하세요..."
                  className="flex-1 px-4 py-2.5 text-sm bg-stone-50 border border-stone-200 rounded-xl focus:outline-none focus:ring-1 focus:ring-[#115E59] focus:bg-white transition-all placeholder:text-stone-400"
                />
                <button type="submit" className="px-4 py-2 text-sm bg-[#115E59] text-white rounded-xl hover:bg-[#0f4e4a] transition-all font-medium">추가</button>
              </form>
              <div className="space-y-2 max-h-[180px] overflow-y-auto mb-4">
                {urls.map((u) => (
                  <div key={u.id} className="p-3 bg-stone-50/60 rounded-xl border border-stone-200/50 flex flex-col space-y-1">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-xs font-mono text-stone-700 break-all font-semibold flex-1">{u.value}</span>
                      <button type="button" onClick={() => setUrls((p) => p.filter((x) => x.id !== u.id))}
                        className="shrink-0 text-stone-400 hover:text-red-500 text-sm">✕</button>
                    </div>
                    <span className="text-[11px] text-[#0F766E] font-medium">{u.label}</span>
                  </div>
                ))}
                {urls.length === 0 && <div className="text-center py-6 text-stone-400 text-sm italic">대기열이 비어 있습니다.</div>}
              </div>
              <button
                onClick={startPipeline}
                disabled={pipelineState === "RUNNING" || pipelineState === "COMMITTING" || urls.length === 0}
                className="w-full py-3.5 rounded-xl font-medium text-sm transition-all flex items-center justify-center space-x-2 bg-stone-900 text-white hover:bg-stone-800 disabled:bg-stone-100 disabled:text-stone-400 disabled:cursor-not-allowed"
              >
                <span>에이전트 통합 크롤러 기동하기</span><span>✦</span>
              </button>
            </div>

            {/* 파이프라인 흐름 */}
            <div className="bg-white rounded-2xl border border-stone-200/70 p-6 shadow-sm">
              <h3 className="font-serif text-base font-bold text-stone-900 mb-4">에이전트 파이프라인 흐름 상태</h3>
              <div className="relative border-l border-stone-200 ml-3 space-y-5 py-1">
                {STEPS.map((s) => {
                  const isActive  = currentStep >= s.step;
                  const isCurrent = currentStep === s.step && pipelineState === "RUNNING";
                  return (
                    <div key={s.step} className="relative pl-6">
                      <span className={`absolute left-[-5px] top-1.5 w-2.5 h-2.5 rounded-full transition-all ${
                        isCurrent ? "bg-[#115E59] ring-4 ring-teal-100" : isActive ? "bg-[#115E59]" : "bg-stone-200"
                      }`} />
                      <h4 className={`text-xs font-bold transition-all ${isActive ? "text-stone-900" : "text-stone-400"}`}>{s.step}. {s.title}</h4>
                      <p  className={`text-[11px] transition-all ${isActive ? "text-stone-500" : "text-stone-300"}`}>{s.desc}</p>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* 실시간 로그 */}
            <div className="bg-stone-900 text-stone-100 rounded-2xl p-5 flex flex-col min-h-[220px]">
              <div className="flex items-center justify-between mb-3 border-b border-stone-800 pb-2">
                <span className="text-xs font-mono font-bold tracking-wider text-[#0F766E]">REALTIME RUNTIME LOGS</span>
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              </div>
              <div className="flex-1 font-mono text-[11px] space-y-1.5 max-h-[220px] overflow-y-auto pr-1">
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
                <div ref={consoleRef} />
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
                    <h4 className="text-sm font-bold text-amber-900">미등록 교차 도메인 감지 (DOMAIN_PENDING)</h4>
                    <p className="text-xs text-amber-700 mt-0.5">
                      <strong>ConnPoolExhaustion</strong>이 <strong>security + performance</strong> 교차 도메인으로 추출되었습니다. 등록 후 계속 진행하세요.
                    </p>
                  </div>
                </div>
                <div className="flex space-x-2">
                  <button onClick={resolveDomain} className="px-3.5 py-1.5 text-xs bg-amber-600 text-white font-semibold rounded-lg hover:bg-amber-700 transition-all">도메인 즉시 등록 및 복구</button>
                  <button onClick={rejectAll}      className="px-3.5 py-1.5 text-xs border border-amber-300 text-amber-800 font-semibold rounded-lg hover:bg-amber-100 transition-all">기각 및 폐기</button>
                </div>
              </div>
            )}

            {/* 그래프 */}
            <div className="bg-white rounded-2xl border border-stone-200/70 p-6 shadow-sm relative">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="font-serif text-base font-bold text-stone-900 flex items-center space-x-2">
                    <span>지식 그래프 가시화 토폴로지 (Neo4j 실시간 연동)</span>
                    {showDraft && <span className="px-2 py-0.5 text-[10px] font-bold bg-amber-100 text-amber-800 rounded-full animate-pulse">DRAFT 가상 뷰어 가동 중</span>}
                  </h3>
                  <p className="text-xs text-stone-400 mt-0.5">노드를 클릭하면 하단 인스펙터 패널에서 속성 정보와 대응 설정값을 확인할 수 있습니다.</p>
                </div>
                <div className="flex items-center space-x-2 text-[10px] font-medium text-stone-500">
                  {[["#292524","Domain"],["#D6D3D1","CWE"],["#B91C1C","보안"],["#0F766E","성능"]].map(([c,l]) => (
                    <span key={l} className="flex items-center space-x-1">
                      <span className="w-2.5 h-2.5 rounded-full" style={{ background: c }} /><span>{l}</span>
                    </span>
                  ))}
                </div>
              </div>

              <div className="h-[340px] bg-[#FAF9F6] border border-stone-200/50 rounded-xl relative overflow-hidden">
                <svg className="w-full h-full" viewBox="0 0 860 340">
                  <defs>
                    <marker id="arr" viewBox="0 0 10 10" refX="24" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                      <path d="M 0 0 L 10 5 L 0 10 z" fill="#D6D3D1" />
                    </marker>
                  </defs>
                  {/* 도메인 → OWASP */}
                  <line x1="280" y1="295" x2="165" y2="215" stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arr)" />
                  <line x1="280" y1="295" x2="375" y2="215" stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arr)" />
                  <line x1="570" y1="295" x2="630" y2="215" stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arr)" />
                  {/* OWASP → CWE */}
                  <line x1="165" y1="215" x2="95"  y2="150" stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arr)" />
                  <line x1="165" y1="215" x2="220" y2="150" stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arr)" />
                  <line x1="375" y1="215" x2="375" y2="150" stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arr)" />
                  <line x1="630" y1="215" x2="590" y2="150" stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arr)" />
                  <line x1="630" y1="215" x2="685" y2="150" stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arr)" />
                  {/* CWE → Concept */}
                  <line x1="95"  y1="150" x2="70"  y2="75"  stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arr)" />
                  <line x1="220" y1="150" x2="195" y2="75"  stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arr)" />
                  <line x1="375" y1="150" x2="330" y2="75"  stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arr)" />
                  <line x1="375" y1="150" x2="445" y2="75"  stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arr)" />
                  <line x1="590" y1="150" x2="560" y2="75"  stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arr)" />
                  <line x1="685" y1="150" x2="685" y2="75"  stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arr)" />
                  {/* DRAFT 점선 — ConnPool (교차 도메인) */}
                  {showDraft && <>
                    <line x1="95"  y1="150" x2="790" y2="68" stroke="#F59E0B" strokeWidth="1.5" strokeDasharray="4,4" markerEnd="url(#arr)" />
                    <line x1="590" y1="150" x2="790" y2="68" stroke="#F59E0B" strokeWidth="1.5" strokeDasharray="4,4" markerEnd="url(#arr)" />
                    <text x="610" y="100" fill="#D97706" fontSize="9" fontWeight="bold">교차 도메인 병합 예정</text>
                  </>}
                  {/* FINISHED 실선 */}
                  {pipelineState === "FINISHED" && <>
                    <line x1="95"  y1="150" x2="790" y2="68" stroke="#7C3AED" strokeWidth="1.5" markerEnd="url(#arr)" />
                    <line x1="590" y1="150" x2="790" y2="68" stroke="#7C3AED" strokeWidth="1.5" markerEnd="url(#arr)" />
                  </>}

                  {/* 도메인 허브 */}
                  <g className="cursor-pointer" onClick={() => addLog("SYSTEM", "Security 마스터 도메인 노드입니다.")}>
                    <circle cx="280" cy="295" r="25" fill="#292524" />
                    <text x="280" y="299" fill="#FFF" fontSize="9" textAnchor="middle" fontWeight="bold">Security</text>
                  </g>
                  <g className="cursor-pointer" onClick={() => addLog("SYSTEM", "Performance 마스터 도메인 노드입니다.")}>
                    <circle cx="570" cy="295" r="25" fill="#115E59" />
                    <text x="570" y="299" fill="#FFF" fontSize="9" textAnchor="middle" fontWeight="bold">Perf</text>
                  </g>

                  {/* OWASP */}
                  <g><circle cx="165" cy="215" r="20" fill="#78716C"/><text x="165" y="219" fill="#FFF" fontSize="8" textAnchor="middle" fontWeight="bold">A01</text></g>
                  <g><circle cx="375" cy="215" r="20" fill="#78716C"/><text x="375" y="219" fill="#FFF" fontSize="8" textAnchor="middle" fontWeight="bold">A03</text></g>
                  <g><circle cx="630" cy="215" r="20" fill="#0F766E"/><text x="630" y="219" fill="#FFF" fontSize="8" textAnchor="middle" fontWeight="bold">P01</text></g>

                  {/* CWE */}
                  <g><circle cx="95"  cy="150" r="15" fill="#D6D3D1"/><text x="95"  y="154" fill="#1C1917" fontSize="6.5" textAnchor="middle">CWE-352</text></g>
                  <g><circle cx="220" cy="150" r="15" fill="#D6D3D1"/><text x="220" y="154" fill="#1C1917" fontSize="6.5" textAnchor="middle">CWE-284</text></g>
                  <g><circle cx="375" cy="150" r="15" fill="#D6D3D1"/><text x="375" y="154" fill="#1C1917" fontSize="6.5" textAnchor="middle">CWE-89</text></g>
                  <g><circle cx="590" cy="150" r="15" fill="#D6D3D1"/><text x="590" y="154" fill="#1C1917" fontSize="6" textAnchor="middle">CWE-1072</text></g>
                  <g><circle cx="685" cy="150" r="15" fill="#D6D3D1"/><text x="685" y="154" fill="#1C1917" fontSize="6" textAnchor="middle">CWE-1052</text></g>

                  {/* Concept 노드 — index 순서: SQLi[0] XSS[1] CSRF[2] N+1Q[3] BAC[4] Idx[5] */}
                  <g className="cursor-pointer" onClick={() => setSelectedConcept(concepts[2])}>
                    <circle cx="70" cy="75" r="18" fill="#FEF2F2" stroke="#B91C1C" strokeWidth="1.5"/>
                    <text x="70" y="79" fill="#B91C1C" fontSize="8" textAnchor="middle" fontWeight="bold">CSRF</text>
                  </g>
                  <g className="cursor-pointer" onClick={() => setSelectedConcept(concepts[4])}>
                    <circle cx="195" cy="75" r="18" fill="#FEF2F2" stroke="#B91C1C" strokeWidth="1.5"/>
                    <text x="195" y="72" fill="#B91C1C" fontSize="6.5" textAnchor="middle" fontWeight="bold">BAC</text>
                    <title>BrokenAccessControl</title>
                  </g>
                  <g className="cursor-pointer" onClick={() => setSelectedConcept(concepts[0])}>
                    <circle cx="330" cy="75" r="18" fill="#FEF2F2" stroke="#B91C1C" strokeWidth="1.5"/>
                    <text x="330" y="79" fill="#B91C1C" fontSize="8" textAnchor="middle" fontWeight="bold">SQLi</text>
                  </g>
                  <g className="cursor-pointer" onClick={() => setSelectedConcept(concepts[1])}>
                    <circle cx="445" cy="75" r="18" fill="#FEF2F2" stroke="#B91C1C" strokeWidth="1.5"/>
                    <text x="445" y="79" fill="#B91C1C" fontSize="8" textAnchor="middle" fontWeight="bold">XSS</text>
                  </g>
                  <g className="cursor-pointer" onClick={() => setSelectedConcept(concepts[3])}>
                    <circle cx="560" cy="75" r="18" fill="#F0FDF4" stroke="#0F766E" strokeWidth="1.5"/>
                    <text x="560" y="79" fill="#0F766E" fontSize="7" textAnchor="middle" fontWeight="bold">N+1Q</text>
                  </g>
                  <g className="cursor-pointer" onClick={() => setSelectedConcept(concepts[5])}>
                    <circle cx="685" cy="75" r="18" fill="#F0FDF4" stroke="#0F766E" strokeWidth="1.5"/>
                    <text x="685" y="79" fill="#0F766E" fontSize="7" textAnchor="middle" fontWeight="bold">Idx</text>
                    <title>MissingIndex</title>
                  </g>

                  {/* DRAFT: ConnPoolExhaustion */}
                  {showDraft && (
                    <g className="cursor-pointer" onClick={() => { setSelectedConcept(DRAFT_CONCEPT); addLog("SYSTEM", "가상 DRAFT 노드 ConnPoolExhaustion (security+performance) 선택."); }}>
                      <circle cx="790" cy="68" r="21" fill="#FEF3C7" stroke="#D97706" strokeWidth="2" strokeDasharray="4,4"/>
                      <text x="790" y="64" fill="#D97706" fontSize="7" textAnchor="middle" fontWeight="bold">Pool</text>
                      <text x="790" y="74" fill="#D97706" fontSize="6" textAnchor="middle">Exhaust</text>
                      <rect x="758" y="28" width="64" height="14" rx="3" fill="#D97706"/>
                      <text x="790" y="38" fill="#FFF" fontSize="6.5" textAnchor="middle" fontWeight="bold">교차 도메인</text>
                    </g>
                  )}
                  {/* FINISHED: ConnPoolExhaustion COMMITTED */}
                  {pipelineState === "FINISHED" && (
                    <g className="cursor-pointer" onClick={() => setSelectedConcept((concepts[6] as typeof DRAFT_CONCEPT | undefined) ?? { ...DRAFT_CONCEPT, state: "COMMITTED" })}>
                      <circle cx="790" cy="68" r="21" fill="#F5F3FF" stroke="#7C3AED" strokeWidth="2"/>
                      <text x="790" y="64" fill="#7C3AED" fontSize="7" textAnchor="middle" fontWeight="bold">Pool</text>
                      <text x="790" y="74" fill="#7C3AED" fontSize="6" textAnchor="middle">Exhaust</text>
                      <rect x="758" y="28" width="64" height="14" rx="3" fill="#7C3AED"/>
                      <text x="790" y="38" fill="#FFF" fontSize="6.5" textAnchor="middle" fontWeight="bold">교차 도메인</text>
                    </g>
                  )}
                </svg>

                {showDraft && (
                  <div className="absolute bottom-4 left-4 right-4 bg-white/95 backdrop-blur-sm border border-amber-300 rounded-xl p-3.5 flex items-center justify-between shadow-lg">
                    <div className="flex items-center space-x-2">
                      <span className="w-2 h-2 rounded-full bg-amber-500 animate-ping" />
                      <span className="text-xs font-bold text-stone-800">가상 노드 병합 예비 요약: 신규 1개(ConnPoolExhaustion) / 교차 도메인 security+performance</span>
                    </div>
                    <div className="flex space-x-2">
                      <button onClick={approveAll} className="px-4 py-1.5 text-xs bg-[#115E59] text-white rounded-lg font-bold hover:bg-[#0e4e4a] transition-all">최종 승인 게이트 통과</button>
                      <button onClick={rejectAll}  className="px-3 py-1.5 text-xs border border-stone-200 text-stone-600 rounded-lg hover:bg-stone-50 transition-all">전체 반려</button>
                    </div>
                  </div>
                )}
              </div>
            </div>

            {/* 개념 인스펙터 */}
            <div className="bg-white rounded-2xl border border-stone-200/70 p-6 shadow-sm">
              <div className="flex items-center justify-between mb-5 border-b border-stone-100 pb-4">
                <div>
                  <h3 className="font-serif text-base font-bold text-stone-900">보안 및 성능 개념(Concept) 인스펙터</h3>
                  <p className="text-xs text-stone-400 mt-0.5">도메인별로 선별 조회하거나 마스터 상세 정보를 조회합니다.</p>
                </div>
                <div className="flex bg-stone-100 p-0.5 rounded-lg border border-stone-200/60">
                  {[["all","전체 기술"],["security","보안 취약점"],["performance","성능 안티패턴"]].map(([id,label]) => (
                    <button key={id} onClick={() => setActiveTab(id)}
                      className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${activeTab === id ? "bg-white text-stone-900 shadow-sm" : "text-stone-500 hover:text-stone-700"}`}
                    >{label}</button>
                  ))}
                </div>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
                {/* 목록 */}
                <div className="md:col-span-4 border-r border-stone-100 pr-4 max-h-[300px] overflow-y-auto space-y-2">
                  {filteredConcepts.map((c) => {
                    const isSelected = selectedConcept.name === c.name;
                    return (
                      <button key={c.name} onClick={() => setSelectedConcept(c)}
                        className={`w-full text-left p-3 rounded-xl border transition-all ${isSelected ? "bg-[#FAF8F5] border-stone-300 shadow-sm" : "border-stone-200/60 hover:bg-stone-50"}`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="text-xs font-bold text-stone-900 truncate mr-1">{c.name}</span>
                          <span className={`shrink-0 text-[9px] px-1.5 py-0.5 rounded-md font-bold uppercase ${severityClass(c.severity)}`}>
                            {c.severity}
                          </span>
                        </div>
                        <div className="flex items-center justify-between mt-2">
                          <span className="text-[10px] text-stone-400">{c.cwe_id}</span>
                          <div className="flex gap-1">
                            {c.domains.map((d) => (
                              <span key={d} className="text-[8px] px-1 rounded-md font-bold"
                                style={{ color: DOMAIN_REGISTRY[d]?.color_hex ?? "#7C3AED", background: DOMAIN_REGISTRY[d]?.bg_hex ?? "#F5F3FF", border: `1px solid ${DOMAIN_REGISTRY[d]?.border_hex ?? "#C7D2FE"}` }}
                              >{DOMAIN_REGISTRY[d]?.label_ko ?? "기타"}</span>
                            ))}
                          </div>
                        </div>
                      </button>
                    );
                  })}
                  {/* DRAFT 노드 */}
                  {showDraft && (
                    <button onClick={() => setSelectedConcept(DRAFT_CONCEPT)}
                      className={`w-full text-left p-3 rounded-xl border border-dashed transition-all ${selectedConcept.name === DRAFT_CONCEPT.name ? "bg-amber-50 border-amber-400" : "border-amber-300 hover:bg-amber-50/50"}`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-amber-800 truncate mr-1">{DRAFT_CONCEPT.name}</span>
                        <span className="shrink-0 text-[9px] px-1.5 py-0.5 rounded-md font-bold uppercase bg-amber-50 text-amber-700 border border-amber-200">draft</span>
                      </div>
                      <div className="flex items-center justify-between mt-2">
                        <span className="text-[10px] text-stone-400">{DRAFT_CONCEPT.cwe_id}</span>
                        <div className="flex gap-1">
                          {DRAFT_CONCEPT.domains.map((d) => (
                            <span key={d} className="text-[8px] px-1 rounded-md font-bold"
                              style={{ color: DOMAIN_REGISTRY[d]?.color_hex ?? "#7C3AED", background: DOMAIN_REGISTRY[d]?.bg_hex ?? "#F5F3FF", border: `1px solid ${DOMAIN_REGISTRY[d]?.border_hex ?? "#C7D2FE"}` }}
                            >{DOMAIN_REGISTRY[d]?.label_ko ?? "기타"}</span>
                          ))}
                        </div>
                      </div>
                    </button>
                  )}
                </div>

                {/* 상세 */}
                <div className="md:col-span-8 space-y-4">
                  {selectedConcept && <>
                    <div className="flex items-start justify-between">
                      <div>
                        <h4 className="font-serif text-lg font-bold text-stone-900">
                          {selectedConcept.name}
                          <span className="text-xs font-mono text-stone-400 font-normal ml-2">({selectedConcept.cwe_id})</span>
                          {selectedConcept.state === "DRAFT" && (
                            <span className="ml-2 text-[10px] px-1.5 py-0.5 bg-amber-100 text-amber-700 rounded font-bold border border-amber-200">DRAFT</span>
                          )}
                        </h4>
                        <div className="flex items-center flex-wrap gap-1 mt-1">
                          <span className="text-xs text-stone-500">동의어:</span>
                          {selectedConcept.aliases.map((a) => (
                            <span key={a} className="text-[10px] px-1.5 py-0.5 bg-stone-100 text-stone-600 rounded-md">{a}</span>
                          ))}
                        </div>
                      </div>
                      <div className="flex flex-wrap gap-1.5 justify-end">
                        {selectedConcept.domains.map((d) => (
                          <span key={d} className="text-xs px-2.5 py-1 rounded-full font-bold"
                            style={{ color: DOMAIN_REGISTRY[d]?.color_hex ?? "#7C3AED", background: DOMAIN_REGISTRY[d]?.bg_hex ?? "#F5F3FF", border: `1px solid ${DOMAIN_REGISTRY[d]?.border_hex ?? "#C7D2FE"}` }}
                          >{DOMAIN_REGISTRY[d]?.label_ko ?? "기타"}</span>
                        ))}
                      </div>
                    </div>

                    <p className="text-xs text-stone-600 leading-relaxed bg-[#FAF8F5] p-3.5 rounded-xl border border-stone-200/50">{selectedConcept.description_ko}</p>

                    <div className="grid grid-cols-2 gap-4 text-xs">
                      <div>
                        <span className="text-stone-400 font-bold block mb-1">영향 컴포넌트</span>
                        <div className="flex flex-wrap gap-1">
                          {selectedConcept.affected_components.map((comp) => (
                            <span key={comp} className="px-2 py-0.5 bg-stone-100 text-[#0F766E] rounded text-[10px] font-mono">{comp}</span>
                          ))}
                        </div>
                      </div>
                      <div>
                        <span className="text-stone-400 font-bold block mb-1">대응 메커니즘</span>
                        <div className="flex flex-wrap gap-1">
                          {selectedConcept.security_mechanisms.map((m) => (
                            <span key={m} className="px-2 py-0.5 bg-stone-100 text-stone-800 rounded text-[10px] font-semibold">✓ {m}</span>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div className="text-[10px] text-stone-400 border-t border-stone-100 pt-3 flex items-center justify-between">
                      <span>출처: {selectedConcept.owasp_id ? `OWASP ${selectedConcept.owasp_id}` : "CWE Seed / Performance Ref"}</span>
                      <span className={`font-bold uppercase ${severityClass(selectedConcept.severity)} px-1.5 py-0.5 rounded text-[9px]`}>
                        {selectedConcept.severity}
                      </span>
                    </div>
                  </>}
                </div>
              </div>
            </div>

          </section>
        </div>
      </main>

      <footer className="border-t border-stone-200/60 bg-white py-6 mt-8 text-center text-xs text-stone-400">
        © 2026 Knowledge Graph Agent Pipeline — Consistent Multi-Domain Schema v2
      </footer>
    </div>
  );
}
