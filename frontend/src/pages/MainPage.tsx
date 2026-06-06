import { useState, useEffect, useRef, useCallback } from "react";

// ── 도메인 레지스트리 ────────────────────────────────────────────────────────
const DOMAIN_REGISTRY: Record<string, { label_ko: string; color_hex: string; bg_hex: string; border_hex: string }> = {
  security:    { label_ko: "보안",  color_hex: "#B91C1C", bg_hex: "#FEF2F2", border_hex: "#FCA5A5" },
  performance: { label_ko: "성능",  color_hex: "#0F766E", bg_hex: "#F0FDF4", border_hex: "#86EFAC" },
};

// ── 초기 Concept 시드 ────────────────────────────────────────────────────────
const INITIAL_CONCEPTS = [
  {
    name: "SQLi", concept_type: "vulnerability_root_cause",
    cwe_id: "CWE-89", owasp_id: "A03:2025", severity: "critical",
    description_ko: "사용자 입력값이 SQL 쿼리 문자열에 직접 연결되어 비위생화된 채 실행되는 취약점. 매개변수화 쿼리(Parameterized Query) 인터페이스를 강제하여 예방합니다.",
    aliases: ["SQL Injection", "SQL 인젝션"],
    affected_components: ["database_access_layer", "orm_core_layer"],
    security_mechanisms: ["parameterized_query", "orm_use_rules"],
    domains: ["security"], state: "COMMITTED",
  },
  {
    name: "XSS", concept_type: "vulnerability_root_cause",
    cwe_id: "CWE-79", owasp_id: "A03:2025", severity: "high",
    description_ko: "사용자 입력값이 적절한 이스케이프 없이 웹브라우저 렌더링 컨텍스트에 포함되어 악성 스크립트가 실행되는 취약점. CSP 및 출력 인코딩 필터로 대응합니다.",
    aliases: ["Cross-Site Scripting", "크로스 사이트 스크립팅"],
    affected_components: ["template_rendering_layer", "api_response_serialization"],
    security_mechanisms: ["output_encoding", "content_security_policy"],
    domains: ["security"], state: "COMMITTED",
  },
  {
    name: "CSRF", concept_type: "vulnerability_root_cause",
    cwe_id: "CWE-352", owasp_id: "A01:2025", severity: "high",
    description_ko: "인증된 사용자의 브라우저 쿠키 메커니즘을 신뢰하는 점을 악용하여, 공격자가 변조된 요청을 피해자의 세션 권한으로 강제 전송하는 취약점.",
    aliases: ["Cross-Site Request Forgery", "사이트 간 요청 위조"],
    affected_components: ["authentication_filter", "session_management_layer"],
    security_mechanisms: ["csrf_token_protection", "samesite_cookie_attribute"],
    domains: ["security"], state: "COMMITTED",
  },
  {
    name: "N+1Query", concept_type: "performance_antipattern",
    cwe_id: "CWE-1072", owasp_id: "", severity: "high",
    description_ko: "ORM 지연 로딩(Lazy Loading)으로 인해 하위 엔티티 조회 루프마다 관계 쿼리가 N번 추가 기동되는 성능 병목 현상. join 및 즉시 로딩 기법으로 해결합니다.",
    aliases: ["N+1 Problem", "N+1 쿼리"],
    affected_components: ["orm_layer", "database_layer"],
    security_mechanisms: ["select_related", "prefetch_related"],
    domains: ["performance"], state: "COMMITTED",
  },
];

const DRAFT_CONCEPT = {
  name: "MemoryLeak", concept_type: "performance_antipattern",
  cwe_id: "CWE-401", owasp_id: "", severity: "high",
  description_ko: "객체 참조 소멸 후에도 힙 메모리가 반환되지 않아 GC의 오버헤드를 유발하고 점진적 리소스 다운을 초래하는 교차 영역 결함.",
  aliases: ["Memory Leak", "메모리 누수"],
  affected_components: ["heap_memory", "garbage_collector"],
  security_mechanisms: ["explicit_resource_release", "context_manager"],
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

// ── 스테이징 개념 타입 ────────────────────────────────────────────────────────
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
    { id: 1, value: "https://docs.djangoproject.com/en/6.0/topics/security/",       label: "Django Core Security 명세 감지" },
    { id: 2, value: "https://docs.spring.io/spring-security/reference/reactive/", label: "Spring Security Reactive 명세 감지" },
  ]);
  const [newUrl, setNewUrl]               = useState("");
  const [pipelineState, setPipelineState] = useState<PipelineState>("IDLE");
  const [currentStep, setCurrentStep]     = useState(0);
  const [logs, setLogs] = useState([
    { time: "00:00:00", type: "SYSTEM",  message: "수집 에이전트 토폴로지 분석 웹뷰가 초기화되었습니다." },
    { time: "00:00:02", type: "DB",      message: "domain_registry 캐시 주입 완료. [security, performance]" },
  ]);
  const [concepts, setConcepts]           = useState(INITIAL_CONCEPTS);
  const [selectedConcept, setSelectedConcept] = useState<typeof INITIAL_CONCEPTS[0] | typeof DRAFT_CONCEPT>(INITIAL_CONCEPTS[0]);
  const [showDraft, setShowDraft]         = useState(false);
  const [activeTab, setActiveTab]         = useState("all");
  const [pendingDomain, setPendingDomain] = useState(false);
  const consoleRef    = useRef<HTMLDivElement>(null);
  const pollRef       = useRef<ReturnType<typeof setInterval> | null>(null);
  const sessionIdRef  = useRef<string | null>(null);
  const docIdRef      = useRef<string | null>(null);

  useEffect(() => {
    consoleRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  useEffect(() => () => { if (pollRef.current) clearInterval(pollRef.current); }, []);

  function addLog(type: string, message: string) {
    const t = new Date().toTimeString().slice(0, 8);
    setLogs((prev) => [...prev, { time: t, type, message }]);
  }

  // ── 폴링 핸들러 ────────────────────────────────────────────────────────────
  const startPolling = useCallback((sessionId: string) => {
    if (pollRef.current) clearInterval(pollRef.current);
    pollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`/api/pipeline/logs/${sessionId}`);
        if (!res.ok) return;
        const data = await res.json();
        const docState: string | null = data.doc_state;

        // 새 로그만 추가 (마지막 message 기준 중복 방지)
        const newEntries: { time: string; type: string; message: string }[] = [];
        for (const l of data.logs ?? []) {
          const agentType = l.agent.toUpperCase();
          newEntries.push({ time: l.ts.slice(11, 19), type: agentType, message: l.message });
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
          // 스테이징 개념 로드
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
      } catch { /* 네트워크 오류 무시, 다음 틱에서 재시도 */ }
    }, 2000);
  }, []);

  // ── URL 추가 ───────────────────────────────────────────────────────────────
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
        const label = detectFramework(newUrl);
        setUrls((prev) => [...prev, { id: Date.now(), value: newUrl.trim(), label }]);
        addLog("INPUT", `[EXT] 문서 등록 완료: ${doc.doc_id}`);
      }
    } catch (err) {
      // 백엔드 미기동 시 로컬 등록으로 폴백
      const label = detectFramework(newUrl);
      setUrls((prev) => [...prev, { id: Date.now(), value: newUrl.trim(), label }]);
      addLog("INPUT", `[로컬] URL 대기열 추가: ${newUrl}`);
    }
    setNewUrl("");
  }

  // ── 파이프라인 트리거 ───────────────────────────────────────────────────────
  async function startPipeline() {
    if (urls.length === 0) return;
    setPipelineState("RUNNING");
    setCurrentStep(1);
    addLog("INPUT", "1단계 [Input Agent] 개시: 수집 링크 대기열 ETag 해시 검사 수행 중...");

    try {
      // 첫 번째 URL을 문서로 등록 (미등록 경우)
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

      // Prescan
      const psRes = await fetch(`/api/documents/${docId}/prescan`, { method: "POST" });
      if (psRes.ok) {
        const ps = await psRes.json();
        addLog("INPUT", `프리스캔 완료: framework=${ps.framework ?? "unknown"}, confidence=${ps.infer_confidence?.toFixed(2)}`);
      }

      // Pipeline trigger
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
      // 백엔드 미기동 시 기존 시뮬레이션 폴백
      setTimeout(() => { setCurrentStep(2); addLog("CRAWLER", "2단계 [Crawler Agent] DOM 파싱 완료."); }, 2000);
      setTimeout(() => { setCurrentStep(3); addLog("EXTRACTOR", "3단계 [Extractor Agent] 스키마 매핑 중..."); }, 4000);
      setTimeout(() => {
        addLog("EXTRACTOR", "DOMAIN_PENDING 상태 감지.");
        setPendingDomain(true);
        setPipelineState("WAITING_APPROVAL");
      }, 6000);
    }
  }

  function resolveDomain() {
    addLog("SYSTEM", "HITL 게이트 복구: 신규 도메인 domain_registry 등록 완료.");
    DOMAIN_REGISTRY["compliance"] = { label_ko: "준수성", color_hex: "#7C3AED", bg_hex: "#F5F3FF", border_hex: "#C7D2FE" };
    setPendingDomain(false);
    setCurrentStep(4);
    addLog("WRITER", "4단계 [Graph Writer Agent] 개시: staging_concepts DRAFT 보관 완료.");
    setPipelineState("WAITING_APPROVAL");
    setShowDraft(true);
  }

  // ── 최종 승인 ──────────────────────────────────────────────────────────────
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

    // 폴백: 시뮬레이션
    setTimeout(() => {
      addLog("GRAPH", "Neo4j MERGE + APOC 라벨 결합 성공.");
      const merged = [...concepts.map((c) => ({ ...c, state: "COMMITTED" })), { ...DRAFT_CONCEPT, state: "COMMITTED" }];
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
    { step: 1, title: "Input Agent",         desc: "링크 유효성 및 ETag 캐싱 분석" },
    { step: 2, title: "Crawler Agent",        desc: "DOM 파싱 및 텍스트 블록 정제" },
    { step: 3, title: "Extractor Agent",      desc: "Gemini 구조화 의미 스키마 추출" },
    { step: 4, title: "Graph Writer Agent",   desc: "PostgreSQL / Neo4j 멱등 적재" },
    { step: 5, title: "Link Resolver Agent",  desc: "동의어 및 SAME_AS 유사도 병합" },
  ];

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-[#1C1917] font-sans antialiased">

      {/* ── HEADER ── */}
      <header className="sticky top-0 z-40 border-b border-stone-200/60 bg-white/80 backdrop-blur-md px-8 py-4 flex items-center justify-between">
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

      {/* ── MAIN GRID ── */}
      <main className="max-w-[1600px] mx-auto p-8 grid grid-cols-12 gap-8">

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
                type="text"
                value={newUrl}
                onChange={(e) => setNewUrl(e.target.value)}
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
                    <button
                      type="button"
                      onClick={() => { setUrls((p) => p.filter((x) => x.id !== u.id)); }}
                      className="shrink-0 text-stone-400 hover:text-red-500 text-sm"
                    >✕</button>
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

          {/* 지표 */}
          <div className="grid grid-cols-5 gap-4">
            {[
              { label: "스캔 문서",   value: urls.length,                                          sub: "URL Queue" },
              { label: "신규 생성",   value: showDraft || pipelineState === "FINISHED" ? 1 : 0,   sub: "Drafts 포함" },
              { label: "필드 보완",   value: 0,                                                    sub: "자동 정규화" },
              { label: "단순 스킵",   value: 0,                                                    sub: "ETag 일치" },
              { label: "총 적재 개념", value: concepts.length,                                     sub: "Committed" },
            ].map((m) => (
              <div key={m.label} className="bg-white rounded-xl border border-stone-200/70 p-4 shadow-sm">
                <span className="text-[11px] font-medium text-stone-500 block">{m.label}</span>
                <span className="font-serif text-2xl font-bold text-stone-900 block mt-1">{m.value}</span>
                <span className="text-[9px] text-[#0F766E] font-medium block mt-1">✓ {m.sub}</span>
              </div>
            ))}
          </div>

          {/* HITL 미등록 도메인 경고 */}
          {pendingDomain && (
            <div className="bg-amber-50 border border-amber-300 rounded-xl p-5 flex items-center justify-between">
              <div className="flex items-center space-x-3">
                <span className="text-xl">⚠️</span>
                <div>
                  <h4 className="text-sm font-bold text-amber-900">미등록 다중 도메인 감지 (DOMAIN_PENDING)</h4>
                  <p className="text-xs text-amber-700 mt-0.5">Extractor가 추출한 '<strong>compliance</strong>'는 현재 레지스트리에 존재하지 않습니다.</p>
                </div>
              </div>
              <div className="flex space-x-2">
                <button onClick={resolveDomain}  className="px-3.5 py-1.5 text-xs bg-amber-600 text-white font-semibold rounded-lg hover:bg-amber-700 transition-all">도메인 즉시 등록 및 복구</button>
                <button onClick={rejectAll}       className="px-3.5 py-1.5 text-xs border border-amber-300 text-amber-800 font-semibold rounded-lg hover:bg-amber-100 transition-all">기각 및 폐기</button>
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

            <div className="h-[320px] bg-[#FAF9F6] border border-stone-200/50 rounded-xl relative overflow-hidden">
              <svg className="w-full h-full" viewBox="0 0 800 320">
                <defs>
                  <marker id="arr" viewBox="0 0 10 10" refX="24" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="#D6D3D1" />
                  </marker>
                </defs>
                {/* 엣지 */}
                {[["400","280","250","200"],["400","280","400","180"],["400","280","550","200"],
                  ["250","200","160","130"],["160","130","100","60"],["160","130","210","60"],
                  ["400","180","400","100"],["400","100","330","40"],["400","100","470","40"],
                  ["550","200","640","130"],["640","130","580","60"]].map(([x1,y1,x2,y2], i) => (
                  <line key={i} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arr)" />
                ))}
                {/* DRAFT 점선 */}
                {showDraft && <>
                  <line x1="250" y1="200" x2="700" y2="60" stroke="#F59E0B" strokeWidth="1.5" strokeDasharray="4,4" markerEnd="url(#arr)" />
                  <line x1="640" y1="130" x2="700" y2="60" stroke="#F59E0B" strokeWidth="1.5" strokeDasharray="4,4" markerEnd="url(#arr)" />
                  <text x="500" y="110" fill="#D97706" fontSize="10" fontWeight="bold">병합 예정 (SAME_AS)</text>
                </>}
                {pipelineState === "FINISHED" && <>
                  <line x1="250" y1="200" x2="700" y2="60" stroke="#0F766E" strokeWidth="1.5" markerEnd="url(#arr)" />
                  <line x1="640" y1="130" x2="700" y2="60" stroke="#0F766E" strokeWidth="1.5" markerEnd="url(#arr)" />
                </>}
                {/* 노드 */}
                <g className="cursor-pointer" onClick={() => addLog("SYSTEM","Security 마스터 도메인 노드입니다.")}>
                  <circle cx="400" cy="280" r="22" fill="#292524" /><text x="400" y="284" fill="#FFF" fontSize="10" textAnchor="middle" fontWeight="bold">Security</text>
                </g>
                <g className="cursor-pointer"><circle cx="250" cy="200" r="18" fill="#78716C"/><text x="250" y="203" fill="#FFF" fontSize="9" textAnchor="middle" fontWeight="bold">A01</text></g>
                <g className="cursor-pointer"><circle cx="400" cy="180" r="18" fill="#78716C"/><text x="400" y="183" fill="#FFF" fontSize="9" textAnchor="middle" fontWeight="bold">A03</text></g>
                <g className="cursor-pointer"><circle cx="550" cy="200" r="18" fill="#57534E"/><text x="550" y="203" fill="#FFF" fontSize="9" textAnchor="middle" fontWeight="bold">P01</text></g>
                <g className="cursor-pointer"><circle cx="160" cy="130" r="14" fill="#D6D3D1"/><text x="160" y="133" fill="#1C1917" fontSize="7" textAnchor="middle">CWE-284</text></g>
                <g className="cursor-pointer"><circle cx="400" cy="100" r="14" fill="#D6D3D1"/><text x="400" y="103" fill="#1C1917" fontSize="7" textAnchor="middle">CWE-89</text></g>
                <g className="cursor-pointer"><circle cx="640" cy="130" r="14" fill="#D6D3D1"/><text x="640" y="133" fill="#1C1917" fontSize="7" textAnchor="middle">CWE-401</text></g>
                <g className="cursor-pointer" onClick={() => setSelectedConcept(concepts[2])}>
                  <circle cx="100" cy="60" r="16" fill="#FEF2F2" stroke="#B91C1C" strokeWidth="1.5"/><text x="100" y="63" fill="#B91C1C" fontSize="8" textAnchor="middle" fontWeight="bold">CSRF</text>
                </g>
                <g className="cursor-pointer" onClick={() => setSelectedConcept(concepts[0])}>
                  <circle cx="330" cy="40" r="16" fill="#FEF2F2" stroke="#B91C1C" strokeWidth="1.5"/><text x="330" y="43" fill="#B91C1C" fontSize="8" textAnchor="middle" fontWeight="bold">SQLi</text>
                </g>
                <g className="cursor-pointer" onClick={() => setSelectedConcept(concepts[1])}>
                  <circle cx="470" cy="40" r="16" fill="#FEF2F2" stroke="#B91C1C" strokeWidth="1.5"/><text x="470" y="43" fill="#B91C1C" fontSize="8" textAnchor="middle" fontWeight="bold">XSS</text>
                </g>
                <g className="cursor-pointer" onClick={() => setSelectedConcept(concepts[3])}>
                  <circle cx="580" cy="60" r="16" fill="#F0FDF4" stroke="#0F766E" strokeWidth="1.5"/><text x="580" y="63" fill="#0F766E" fontSize="7" textAnchor="middle" fontWeight="bold">N+1Q</text>
                </g>
                {showDraft && (
                  <g className="cursor-pointer" onClick={() => { setSelectedConcept(DRAFT_CONCEPT); addLog("SYSTEM","가상 DRAFT 노드 MemoryLeak 선택."); }}>
                    <circle cx="700" cy="60" r="18" fill="#FEF3C7" stroke="#D97706" strokeWidth="2" strokeDasharray="4,4"/>
                    <text x="700" y="63" fill="#D97706" fontSize="8" textAnchor="middle" fontWeight="bold">Leak</text>
                    <rect x="670" y="25" width="60" height="12" rx="3" fill="#D97706"/>
                    <text x="700" y="34" fill="#FFF" fontSize="6" textAnchor="middle" fontWeight="bold">병합 대기</text>
                  </g>
                )}
                {pipelineState === "FINISHED" && (
                  <g className="cursor-pointer" onClick={() => setSelectedConcept(concepts[4])}>
                    <circle cx="700" cy="60" r="18" fill="#F5F3FF" stroke="#7D52F4" strokeWidth="2"/>
                    <text x="700" y="63" fill="#7D52F4" fontSize="8" textAnchor="middle" fontWeight="bold">Leak</text>
                    <rect x="670" y="25" width="60" height="12" rx="3" fill="#7D52F4"/>
                    <text x="700" y="34" fill="#FFF" fontSize="6" textAnchor="middle" fontWeight="bold">교차 도메인</text>
                  </g>
                )}
              </svg>

              {showDraft && (
                <div className="absolute bottom-4 left-4 right-4 bg-white/95 backdrop-blur-sm border border-amber-300 rounded-xl p-3.5 flex items-center justify-between shadow-lg">
                  <div className="flex items-center space-x-2">
                    <span className="w-2 h-2 rounded-full bg-amber-500 animate-ping" />
                    <span className="text-xs font-bold text-stone-800">가상 노드 병합 예비 요약: 신규 1개 / 병합 예약 1개</span>
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
              <div className="md:col-span-4 border-r border-stone-100 pr-4 max-h-[280px] overflow-y-auto space-y-2">
                {filteredConcepts.map((c) => {
                  const isSelected = selectedConcept.name === c.name;
                  return (
                    <button key={c.name} onClick={() => setSelectedConcept(c)}
                      className={`w-full text-left p-3 rounded-xl border transition-all ${isSelected ? "bg-[#FAF8F5] border-stone-300 shadow-sm" : "border-stone-200/60 hover:bg-stone-50"}`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-stone-900">{c.name}</span>
                        <span className={`text-[9px] px-1.5 py-0.5 rounded-md font-bold uppercase ${c.severity === "critical" ? "bg-rose-50 text-rose-700 border border-rose-200" : "bg-amber-50 text-amber-700 border border-amber-200"}`}>
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
              </div>

              {/* 상세 */}
              <div className="md:col-span-8 space-y-4">
                {selectedConcept && <>
                  <div className="flex items-start justify-between">
                    <div>
                      <h4 className="font-serif text-lg font-bold text-stone-900">
                        {selectedConcept.name}
                        <span className="text-xs font-mono text-stone-400 font-normal ml-2">({selectedConcept.cwe_id})</span>
                      </h4>
                      <div className="flex items-center space-x-2 mt-1">
                        <span className="text-xs text-stone-500">동의어:</span>
                        {selectedConcept.aliases.map((a) => (
                          <span key={a} className="text-[10px] px-1.5 py-0.5 bg-stone-100 text-stone-600 rounded-md">{a}</span>
                        ))}
                      </div>
                    </div>
                    <div className="flex space-x-1.5">
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
                      <span className="text-stone-400 font-bold block mb-1">대응 보안 메커니즘</span>
                      <div className="flex flex-wrap gap-1">
                        {selectedConcept.security_mechanisms.map((m) => (
                          <span key={m} className="px-2 py-0.5 bg-stone-100 text-stone-800 rounded text-[10px] font-semibold">✓ {m}</span>
                        ))}
                      </div>
                    </div>
                  </div>

                  <div className="text-[10px] text-stone-400 border-t border-stone-100 pt-3 flex items-center justify-between">
                    <span>출처: {selectedConcept.owasp_id ? `OWASP ${selectedConcept.owasp_id}` : "Performance Seed Source"}</span>
                    <span>신입사원 코드 검수 대응용 지식 자산</span>
                  </div>
                </>}
              </div>
            </div>
          </div>

        </section>
      </main>

      <footer className="border-t border-stone-200/60 bg-white py-6 mt-8 text-center text-xs text-stone-400">
        © 2026 Knowledge Graph Agent Pipeline — Consistent Multi-Domain Schema v2
      </footer>
    </div>
  );
}
