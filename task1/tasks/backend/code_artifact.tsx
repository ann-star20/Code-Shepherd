import React, { useState, useEffect, useRef } from 'react';

// =========================================================================
// MOCK DATA: 도메인 레지스트리 및 시드 자산 정보 (완전 소문자 통일 스펙 반영)
// =========================================================================
const DOMAIN_REGISTRY = {
  security: {
    label_ko: "보안",
    color_hex: "#B91C1C", // Deep Crimson
    bg_hex: "#FEF2F2",
    border_hex: "#FCA5A5"
  },
  performance: {
    label_ko: "성능",
    color_hex: "#0F766E", // Deep Teal/Sage
    bg_hex: "#F0FDF4",
    border_hex: "#86EFAC"
  }
};

const INITIAL_CONCEPTS = [
  {
    name: "SQLi",
    concept_type: "vulnerability_root_cause",
    cwe_id: "CWE-89",
    owasp_id: "A03:2025",
    severity: "critical",
    description_ko: "사용자 입력값이 SQL 쿼리 문자열에 직접 연결되어 비위생화된 채 실행되는 취약점. 매개변수화 쿼리(Parameterized Query) 인터페이스를 강제하여 예방합니다.",
    aliases: ["SQL Injection", "SQL 인젝션"],
    affected_components: ["database_access_layer", "orm_core_layer"],
    security_mechanisms: ["parameterized_query", "orm_use_rules"],
    domains: ["security"],
    state: "COMMITTED"
  },
  {
    name: "XSS",
    concept_type: "vulnerability_root_cause",
    cwe_id: "CWE-79",
    owasp_id: "A03:2025",
    severity: "high",
    description_ko: "사용자 입력값이 적절한 이스케이프 없이 웹브라우저 렌더링 컨텍스트에 포함되어 악성 스크립트가 실행되는 취약점. CSP 및 출력 인코딩 필터로 대응합니다.",
    aliases: ["Cross-Site Scripting", "크로스 사이트 스크립팅"],
    affected_components: ["template_rendering_layer", "api_response_serialization"],
    security_mechanisms: ["output_encoding", "content_security_policy"],
    domains: ["security"],
    state: "COMMITTED"
  },
  {
    name: "CSRF",
    concept_type: "vulnerability_root_cause",
    cwe_id: "CWE-352",
    owasp_id: "A01:2025",
    severity: "high",
    description_ko: "인증된 사용자의 브라우저 쿠키 메커니즘을 신뢰하는 점을 악용하여, 공격자가 변조된 요청을 피해자의 세션 권한으로 강제 전송하는 취약점.",
    aliases: ["Cross-Site Request Forgery", "사이트 간 요청 위조"],
    affected_components: ["authentication_filter", "session_management_layer"],
    security_mechanisms: ["csrf_token_protection", "samesite_cookie_attribute"],
    domains: ["security"],
    state: "COMMITTED"
  },
  {
    name: "N+1Query",
    concept_type: "performance_antipattern",
    cwe_id: "CWE-1072",
    perf_category: "orm_performance",
    severity: "high",
    description_ko: "ORM 지연 로딩(Lazy Loading)으로 인해 하위 엔티티 조회 루프마다 관계 쿼리가 N번 추가 기동되는 성능 병목 현상. join 및 즉시 로딩 기법으로 해결합니다.",
    aliases: ["N+1 Problem", "N+1 쿼리"],
    affected_components: ["orm_layer", "database_layer"],
    security_mechanisms: ["select_related", "prefetch_related"],
    domains: ["performance"],
    state: "COMMITTED"
  }
];

// 최종 승인 및 클라이언트 가상 병합을 테스트하기 위한 DRAFT 상태의 노드 자산
const DRAFT_CONCEPTS_MOCK = [
  {
    name: "MemoryLeak",
    concept_type: "performance_antipattern",
    cwe_id: "CWE-401",
    perf_category: "resource_management",
    severity: "high",
    description_ko: "객체 참조 소멸 후에도 힙 메모리가 반환되지 않아 GC의 오버헤드를 유발하고 점진적 리소스 다운을 초래하는 교차 영역 결함. 보안(CWE-401 자원 미해제)이자 성능 병목입니다.",
    aliases: ["Memory Leak", "메모리 누수"],
    affected_components: ["heap_memory", "garbage_collector"],
    security_mechanisms: ["explicit_resource_release", "context_manager"],
    domains: ["security", "performance"], // 다중 및 교차 영역 배열 선언
    state: "DRAFT"
  }
];

export default function App() {
  // --- 상태 관리 (States) ---
  const [urls, setUrls] = useState([
    { id: 1, value: "https://docs.djangoproject.com/en/6.0/topics/security/", detected: "Django Core Security 명세 감지", count: "자동추론 ✓" },
    { id: 2, value: "https://docs.spring.io/spring-security/reference/reactive/", detected: "Spring Security Reactive 명세 감지", count: "자동추론 ✓" }
  ]);
  const [newUrl, setNewUrl] = useState("");
  const [pipelineState, setPipelineState] = useState("IDLE"); // IDLE | RUNNING | WAITING_APPROVAL | COMMITTING | FINISHED
  const [currentStep, setCurrentStep] = useState(0); // 0~5 단계 인디케이터
  const [logs, setLogs] = useState([
    { time: "11:24:02", type: "SYSTEM", message: "수집 에이전트 토폴로지 분석 웹뷰가 초기화되었습니다." },
    { time: "11:24:05", type: "DB", message: "로컬 domain_registry 캐시가 성공적으로 주입되었습니다. [security, performance]" }
  ]);
  const [concepts, setConcepts] = useState(INITIAL_CONCEPTS);
  const [selectedConcept, setSelectedConcept] = useState(INITIAL_CONCEPTS[0]);
  const [showDraftMode, setShowDraftMode] = useState(false);
  const [activeTab, setActiveTab] = useState("all"); // all | security | performance
  
  // HITL 미등록 도메인 게이트 시뮬레이션용 상태
  const [pendingDomainError, setPendingDomainError] = useState(false);
  const [pendingDomainName, setPendingDomainName] = useState("");

  const consoleEndRef = useRef(null);

  // 자동 스크롤
  useEffect(() => {
    consoleEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [logs]);

  // --- 로그 기록 유틸 ---
  const addLog = (type, message) => {
    const now = new Date();
    const timeStr = now.toTimeString().split(' ')[0];
    setLogs(prev => [...prev, { time: timeStr, type, message }]);
  };

  // --- 대기열 처리 ---
  const handleAddUrl = (e) => {
    e.preventDefault();
    if (!newUrl) return;
    
    // ETag 중복 발급 및 URL 정규화 클라이언트 동기화 시뮬레이션
    const isDuplicate = urls.some(u => u.value.trim().toLowerCase() === newUrl.trim().toLowerCase());
    if (isDuplicate) {
      addLog("WARNING", `중복된 URL 입력 차단: ${newUrl}`);
      alert("이미 대기열에 등록되었거나 중복 가공된 URL입니다.");
      return;
    }

    const hasSpring = newUrl.toLowerCase().includes("spring");
    const hasDjango = newUrl.toLowerCase().includes("django");
    const detectedStr = hasSpring ? "Spring Framework 명세 자동 추론" : (hasDjango ? "Django Framework 명세 자동 추론" : "범용 가이드라인 분석 패턴 적용");

    setUrls(prev => [
      ...prev,
      { id: Date.now(), value: newUrl, detected: detectedStr, count: "자동추론 ✓" }
    ]);
    addLog("INPUT", `신규 URL 사전 스캔 완료: [EXT] ${newUrl}`);
    setNewUrl("");
  };

  // --- 파이프라인 에이전트 트리거 시뮬레이션 ---
  const startPipeline = () => {
    if (urls.length === 0) {
      alert("대기열에 수집할 URL이 존재하지 않습니다.");
      return;
    }
    setPipelineState("RUNNING");
    setCurrentStep(1);
    addLog("INPUT", "1단계 [Input Agent] 개시: 수집 링크 대기열 사전 ETag 해시 검사 수행 중...");

    // 단계별 순차 진행 시뮬레이션
    setTimeout(() => {
      setCurrentStep(2);
      addLog("CRAWLER", "2단계 [Crawler Agent] 개시: DOM 정제 및 본문 가독 텍스트 블록 파싱 완료.");
    }, 2000);

    setTimeout(() => {
      setCurrentStep(3);
      addLog("EXTRACTOR", "3단계 [Extractor Agent] 개시: Gemini-2.5-Flash 모델 구조화 JSON 스키마 매핑 중...");
    }, 4000);

    setTimeout(() => {
      // 만약 미등록 도메인을 탐지했을 때의 예외적 일시정지(DOMAIN_PENDING) 연출
      const randomTrigger = true; // 가상 미리보기 및 교차 도메인 체감 극대화를 위해 분기 연동
      if (randomTrigger && !showDraftMode) {
        addLog("EXTRACTOR", "⚠️ [HITL Alert] 미등록 다중 도메인 'compliance' 감지됨. DOMAIN_PENDING 상태로 일시 중단.");
        setPendingDomainName("compliance");
        setPendingDomainError(true);
        setPipelineState("WAITING_APPROVAL");
      } else {
        proceedToStaging();
      }
    }, 6000);
  };

  const proceedToStaging = () => {
    setPendingDomainError(false);
    setCurrentStep(4);
    addLog("WRITER", "4단계 [Graph Writer Agent] 개시: PostgreSQL staging_concepts에 DRAFT 보관 완료.");
    addLog("SYSTEM", "🎉 스테이징 적재 완료. 대시보드에서 점선(DRAFT) 미리보기 데이터를 확인 후 승인 게이트를 통과시키세요.");
    setPipelineState("WAITING_APPROVAL");
    setShowDraftMode(true);
  };

  // --- HITL 복구 액션 (신규 도메인 레지스트리 실시간 등록) ---
  const resolvePendingDomain = () => {
    addLog("SYSTEM", `HITL 게이트 인터락 복구: 신규 도메인 [${pendingDomainName}]을 domain_registry에 실시간 영구 등록 완료.`);
    addLog("SYSTEM", `테마 컬러 바인딩 완료 (#7C3AED / Royal Purple).`);
    DOMAIN_REGISTRY[pendingDomainName] = {
      label_ko: "준수성",
      color_hex: "#7C3AED",
      bg_hex: "#F5F3FF",
      border_hex: "#C7D2FE"
    };
    proceedToStaging();
  };

  // --- 최종 승인 게이트 (2단계 크로스 DB 트랜잭션 수립) ---
  const approveAllStaging = () => {
    setPipelineState("COMMITTING");
    addLog("SYSTEM", "최종 승인 감지 ──► 2단계 크로스 DB 원자적 트랜잭션 구동 시작.");
    addLog("DB", "PostgreSQL concepts 테이블 UPSERT 성공. (state -> COMMITTED)");
    
    setTimeout(() => {
      addLog("GRAPH", "Neo4j 마스터 멱등성 MERGE 및 APOC 물리 라벨 물리 결합 성공.");
      // concepts 합병
      const mergedConcepts = [
        ...concepts.map(c => ({ ...c, state: "COMMITTED" })),
        ...DRAFT_CONCEPTS_MOCK.map(dc => ({ ...dc, state: "COMMITTED" }))
      ];
      setConcepts(mergedConcepts);
      setSelectedConcept(mergedConcepts[mergedConcepts.length - 1]); // 방금 가상에서 승인된 MemoryLeak 선택

      // 5단계 자동 트리거
      setCurrentStep(5);
      addLog("RESOLVER", "5단계 [Link Resolver Agent] 가동: aliases 배열 기반 SAME_AS 가상 관계 영속 결합 성공.");
      addLog("SYSTEM", "🎉 4대 마스터 트랜잭션 규칙이 안전하게 종료되었습니다. 모든 데이터가 영속실선으로 치환되었습니다.");
      setPipelineState("FINISHED");
      setShowDraftMode(false);
      setUrls([]); // 대기열 소거
    }, 1500);
  };

  const rejectStaging = () => {
    addLog("SYSTEM", "최종 관리자 거부: staging_concepts의 임시 DRAFT 기록을 완전 소거했습니다.");
    setPipelineState("IDLE");
    setShowDraftMode(false);
    setCurrentStep(0);
  };

  // 필터링된 개념 목록
  const filteredConcepts = concepts.filter(c => {
    if (activeTab === "all") return true;
    return c.domains.includes(activeTab);
  });

  return (
    <div className="min-h-screen bg-[#FAF8F5] text-[#1C1917] font-sans antialiased selection:bg-stone-200">
      {/* --- PREMIUM HEADER --- */}
      <header className="border-b border-stone-200/60 bg-white/80 backdrop-blur-md sticky top-0 z-40 px-8 py-4 flex items-center justify-between">
        <div className="flex items-center space-x-3">
          <div className="w-8 h-8 rounded-lg bg-[#115E59] flex items-center justify-center text-white font-serif font-bold text-lg">
            K
          </div>
          <div>
            <h1 className="font-serif text-lg font-bold tracking-tight text-stone-900">
              수집 에이전트 지식 그래프 실시간 웹뷰
            </h1>
            <p className="text-xs text-stone-500 tracking-wide">
              공식 문서 파싱 → 다중 도메인 지식 그래프 실시간 동기화 관제 패널 (v2 Agile Edition)
            </p>
          </div>
        </div>

        <div className="flex items-center space-x-4">
          <div className="flex items-center space-x-2">
            <span className="relative flex h-2 w-2">
              <span className={`animate-ping absolute inline-flex h-full w-full rounded-full ${pipelineState === "RUNNING" ? 'bg-amber-400' : 'bg-emerald-400'} opacity-75`}></span>
              <span className={`relative inline-flex rounded-full h-2 w-2 ${pipelineState === "RUNNING" ? 'bg-amber-500' : 'bg-emerald-500'}`}></span>
            </span>
            <span className="text-xs font-medium text-stone-600">
              {pipelineState === "RUNNING" ? "에이전트 작동 중" : "파이프라인 준비 완료"}
            </span>
          </div>
          <span className="px-2.5 py-1 text-xs font-serif italic bg-stone-100 rounded-full text-stone-700">
            Django & Spring 하이브리드 대응
          </span>
        </div>
      </header>

      {/* --- MAIN GRID LAYOUT --- */}
      <main className="max-w-[1600px] mx-auto p-8 grid grid-cols-12 gap-8">
        
        {/* ==================== LEFT COLUMN: CONTROL & PIPELINE ==================== */}
        <section className="col-span-12 lg:col-span-4 flex flex-col space-y-8">
          
          {/* 1. LINK INGESTION 대기열 */}
          <div className="bg-white rounded-2xl border border-stone-200/70 p-6 shadow-sm shadow-stone-100">
            <h2 className="font-serif text-base font-bold text-stone-900 mb-4 flex items-center justify-between">
              <span>수집 대상 링크 대기열</span>
              <span className="text-xs font-sans text-stone-400 font-normal">MAX 5 URLs</span>
            </h2>

            <form onSubmit={handleAddUrl} className="flex gap-2 mb-4">
              <input
                type="url"
                value={newUrl}
                onChange={(e) => setNewUrl(e.target.value)}
                placeholder="공식 가이드 및 보안 URL을 입력하세요..."
                className="flex-1 px-4 py-2.5 text-sm bg-stone-50 border border-stone-200 rounded-xl focus:outline-none focus:ring-1 focus:ring-[#115E59] focus:bg-white transition-all placeholder:text-stone-400"
              />
              <button
                type="submit"
                className="px-4 py-2 text-sm bg-[#115E59] text-white rounded-xl hover:bg-[#0f4e4a] transition-all font-medium active:scale-95"
              >
                추가
              </button>
            </form>

            <div className="space-y-2.5 max-h-[180px] overflow-y-auto mb-4 pr-1">
              {urls.map((u) => (
                <div key={u.id} className="p-3 bg-stone-50/60 rounded-xl border border-stone-200/50 flex flex-col space-y-1">
                  <span className="text-xs font-mono text-stone-700 break-all select-all font-semibold">
                    {u.value}
                  </span>
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] text-[#0F766E] font-medium">{u.detected}</span>
                    <span className="text-[10px] px-1.5 py-0.5 bg-stone-200/60 text-stone-600 rounded-md font-medium">
                      {u.count}
                    </span>
                  </div>
                </div>
              ))}
              {urls.length === 0 && (
                <div className="text-center py-6 text-stone-400 text-sm italic">
                  대기열이 비어 있습니다.
                </div>
              )}
            </div>

            <button
              onClick={startPipeline}
              disabled={pipelineState === "RUNNING" || urls.length === 0}
              className={`w-full py-3.5 rounded-xl font-medium text-sm transition-all flex items-center justify-center space-x-2 ${
                pipelineState === "RUNNING" || urls.length === 0
                  ? "bg-stone-100 text-stone-400 cursor-not-allowed"
                  : "bg-stone-900 text-white hover:bg-stone-800 active:scale-98 shadow-sm"
              }`}
            >
              <span>에이전트 통합 크롤러 기동하기</span>
              <span>✦</span>
            </button>
          </div>

          {/* 2. PIPELINE Flow STEPS */}
          <div className="bg-white rounded-2xl border border-stone-200/70 p-6 shadow-sm shadow-stone-100">
            <h3 className="font-serif text-base font-bold text-stone-900 mb-4">
              에이전트 파이프라인 흐름 상태
            </h3>

            <div className="relative border-l border-stone-200 ml-3 space-y-6 py-1">
              {[
                { step: 1, title: "Input Agent", desc: "링크 유효성 및 ETag 캐싱 분석" },
                { step: 2, title: "Crawler Agent", desc: "DOM 파싱 및 텍스트 블록 정제" },
                { step: 3, title: "Extractor Agent", desc: "Gemini 구조화 의미 스키마 추출" },
                { step: 4, title: "Graph Writer Agent", desc: "PostgreSQL / Neo4j 멱등 적재" },
                { step: 5, title: "Link Resolver Agent", desc: "동의어 및 SAME_AS 유사도 병합" }
              ].map((s) => {
                const isActive = currentStep >= s.step;
                const isCurrent = currentStep === s.step;
                return (
                  <div key={s.step} className="relative pl-6">
                    <span className={`absolute left-[-5px] top-1.5 w-2.5 h-2.5 rounded-full transition-all ${
                      isCurrent 
                        ? 'bg-[#115E59] ring-4 ring-teal-100' 
                        : isActive 
                          ? 'bg-[#115E59]' 
                          : 'bg-stone-200'
                    }`}></span>
                    <h4 className={`text-xs font-bold transition-all ${isActive ? 'text-stone-900' : 'text-stone-400'}`}>
                      {s.step}. {s.title}
                    </h4>
                    <p className={`text-[11px] transition-all ${isActive ? 'text-stone-500' : 'text-stone-300'}`}>
                      {s.desc}
                    </p>
                  </div>
                );
              })}
            </div>
          </div>

          {/* 3. SSE RUNTIME CONSOLE */}
          <div className="bg-stone-900 text-stone-100 rounded-2xl p-6 shadow-inner flex-1 flex flex-col min-h-[250px]">
            <div className="flex items-center justify-between mb-3 border-b border-stone-800 pb-2">
              <span className="text-xs font-mono font-bold tracking-wider text-[#0F766E]">REALTIME RUNTIME LOGS</span>
              <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse"></span>
            </div>

            <div className="flex-1 font-mono text-[11px] space-y-2 max-h-[240px] overflow-y-auto pr-1">
              {logs.map((l, idx) => (
                <div key={idx} className="leading-relaxed border-b border-stone-800/40 pb-1.5">
                  <span className="text-[#78716C] mr-2">[{l.time}]</span>
                  <span className={`font-bold mr-1.5 ${
                    l.type === "SYSTEM" ? "text-sky-400" :
                    l.type === "INPUT" ? "text-amber-400" :
                    l.type === "CRAWLER" ? "text-indigo-400" :
                    l.type === "EXTRACTOR" ? "text-emerald-400" :
                    l.type === "WRITER" ? "text-fuchsia-400" : "text-rose-400"
                  }`}>
                    [{l.type}]
                  </span>
                  <span className="text-stone-200">{l.message}</span>
                </div>
              ))}
              <div ref={consoleEndRef} />
            </div>
            <div className="text-[10px] text-stone-500 font-mono text-right mt-2 pt-2 border-t border-stone-800">
              Console Buffer: Idempotency Checked
            </div>
          </div>

        </section>

        {/* ==================== RIGHT COLUMN: TOPO GRAPH & INSPECTOR ==================== */}
        <section className="col-span-12 lg:col-span-8 flex flex-col space-y-8">
          
          {/* METRICS ROW */}
          <div className="grid grid-cols-5 gap-4">
            {[
              { label: "스캔 문서", value: urls.length > 0 ? "2" : "0", change: "URL Queue" },
              { label: "신규 생성", value: showDraftMode || pipelineState === "FINISHED" ? "1" : "0", change: "Drafts 포함" },
              { label: "필드 보완", value: "0", change: "자동 정규화" },
              { label: "단순 스킵", value: "0", change: "ETag 일치" },
              { label: "총 적재 개념", value: concepts.length, change: "Committed" }
            ].map((m, idx) => (
              <div key={idx} className="bg-white rounded-xl border border-stone-200/70 p-4 shadow-sm">
                <span className="text-[11px] font-medium text-stone-500 block">{m.label}</span>
                <span className="font-serif text-2xl font-bold text-stone-900 block mt-1">{m.value}</span>
                <span className="text-[9px] text-[#0F766E] font-medium block mt-1">✓ {m.change}</span>
              </div>
            ))}
          </div>

          {/* HITL DOMAIN PENDING INTERLOCK WARNING */}
          {pendingDomainError && (
            <div className="bg-amber-50 border border-amber-300 rounded-xl p-5 flex items-center justify-between animate-fade-in">
              <div className="flex items-center space-x-3">
                <span className="text-xl">⚠️</span>
                <div>
                  <h4 className="text-sm font-bold text-amber-900">미등록 다중 도메인 감지 (DOMAIN_PENDING)</h4>
                  <p className="text-xs text-amber-700 mt-0.5">
                    Extractor가 추출한 데이터 중 '<strong>{pendingDomainName}</strong>'은 현재 레지스트리에 존재하지 않습니다.
                  </p>
                </div>
              </div>
              <div className="flex space-x-2">
                <button
                  onClick={resolvePendingDomain}
                  className="px-3.5 py-1.5 text-xs bg-amber-600 text-white font-semibold rounded-lg hover:bg-amber-700 transition-all active:scale-95"
                >
                  도메인 즉시 등록 및 복구
                </button>
                <button
                  onClick={rejectStaging}
                  className="px-3.5 py-1.5 text-xs border border-amber-300 text-amber-800 font-semibold rounded-lg hover:bg-amber-100 transition-all"
                >
                  기각 및 폐기
                </button>
              </div>
            </div>
          )}

          {/* GRAPH VISUALIZATION BOARD */}
          <div className="bg-white rounded-2xl border border-stone-200/70 p-6 shadow-sm shadow-stone-100 relative">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="font-serif text-base font-bold text-stone-900 flex items-center space-x-2">
                  <span>지식 그래프 가시화 토폴로지 (Neo4j 실시간 연동)</span>
                  {showDraftMode && (
                    <span className="px-2 py-0.5 text-[10px] font-bold bg-amber-100 text-amber-800 rounded-full animate-pulse">
                      DRAFT 가상 뷰어 가동 중
                    </span>
                  )}
                </h3>
                <p className="text-xs text-stone-400 mt-0.5">
                  각 노드를 클릭하면 하단 인스펙터 패널에서 속성 정보와 대응 설정값을 확인할 수 있습니다.
                </p>
              </div>

              {/* Legend */}
              <div className="flex items-center space-x-2.5 text-[10px] font-medium text-stone-500">
                <span className="flex items-center space-x-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-stone-300"></span>
                  <span>Domain</span>
                </span>
                <span className="flex items-center space-x-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-stone-400"></span>
                  <span>CWE</span>
                </span>
                <span className="flex items-center space-x-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#B91C1C]"></span>
                  <span>보안</span>
                </span>
                <span className="flex items-center space-x-1">
                  <span className="w-2.5 h-2.5 rounded-full bg-[#0F766E]"></span>
                  <span>성능</span>
                </span>
              </div>
            </div>

            {/* INTERACTIVE SVG GRAPH GRAPHIC */}
            <div className="h-[320px] bg-[#FAF9F6] border border-stone-200/50 rounded-xl relative overflow-hidden flex items-center justify-center">
              <svg className="w-full h-full" viewBox="0 0 800 320">
                <defs>
                  <marker id="arrow" viewBox="0 0 10 10" refX="24" refY="5" markerWidth="6" markerHeight="6" orient="auto-start-reverse">
                    <path d="M 0 0 L 10 5 L 0 10 z" fill="#D6D3D1" />
                  </marker>
                </defs>

                {/* ─── EDGES (실선 / 가상 병합 점선) ─── */}
                {/* Security -> OWASP Link */}
                <line x1="400" y1="280" x2="250" y2="200" stroke="#E7E5E4" strokeWidth="2" markerEnd="url(#arrow)" />
                <line x1="400" y1="280" x2="400" y2="180" stroke="#E7E5E4" strokeWidth="2" markerEnd="url(#arrow)" />
                <line x1="400" y1="280" x2="550" y2="200" stroke="#E7E5E4" strokeWidth="2" markerEnd="url(#arrow)" />

                {/* OWASP -> CWE -> Concept Link */}
                <line x1="250" y1="200" x2="160" y2="130" stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arrow)" />
                <line x1="160" y1="130" x2="100" y2="60" stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arrow)" />
                <line x1="160" y1="130" x2="210" y2="60" stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arrow)" />

                <line x1="400" y1="180" x2="400" y2="100" stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arrow)" />
                <line x1="400" y1="100" x2="330" y2="40" stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arrow)" />
                <line x1="400" y1="100" x2="470" y2="40" stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arrow)" />

                {/* Performance -> CWE -> Concept Link */}
                <line x1="550" y1="200" x2="640" y2="130" stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arrow)" />
                <line x1="640" y1="130" x2="580" y2="60" stroke="#E7E5E4" strokeWidth="1.5" markerEnd="url(#arrow)" />

                {/* ─── DRAFT 가상 병합 점선 관계선 (교차 영역 MemoryLeak) ─── */}
                {showDraftMode && (
                  <>
                    {/* Security(A01) -> MemoryLeak */}
                    <line 
                      x1="250" y1="200" x2="700" y2="60" 
                      stroke="#F59E0B" strokeWidth="1.5" strokeDasharray="4,4" 
                      markerEnd="url(#arrow)" 
                    />
                    {/* Performance(Resource Management) -> MemoryLeak */}
                    <line 
                      x1="640" y1="130" x2="700" y2="60" 
                      stroke="#F59E0B" strokeWidth="1.5" strokeDasharray="4,4" 
                      markerEnd="url(#arrow)" 
                    />
                    <text x="500" y="110" fill="#D97706" fontSize="10" fontWeight="bold" className="animate-pulse">
                      병합 예정 (SAME_AS)
                    </text>
                  </>
                )}

                {/* COMMITTED 전환 완료 시 실선 연결 */}
                {pipelineState === "FINISHED" && (
                  <>
                    <line x1="250" y1="200" x2="700" y2="60" stroke="#0F766E" strokeWidth="1.5" markerEnd="url(#arrow)" />
                    <line x1="640" y1="130" x2="700" y2="60" stroke="#0F766E" strokeWidth="1.5" markerEnd="url(#arrow)" />
                  </>
                )}

                {/* ─── NODES ─── */}
                {/* Root Domain */}
                <g className="cursor-pointer" onClick={() => addLog("SYSTEM", "Security 마스터 도메인 노드입니다.")}>
                  <circle cx="400" cy="280" r="22" fill="#292524" stroke="#78716C" strokeWidth="1" />
                  <text x="400" y="284" fill="#FFFFFF" fontSize="10" textAnchor="middle" fontWeight="bold">Security</text>
                </g>

                {/* OWASP Categories */}
                <g className="cursor-pointer" onClick={() => addLog("SYSTEM", "A01: Broken Access Control 카테고리입니다.")}>
                  <circle cx="250" cy="200" r="18" fill="#78716C" />
                  <text x="250" y="203" fill="#FFFFFF" fontSize="9" textAnchor="middle" fontWeight="bold">A01</text>
                </g>
                <g className="cursor-pointer" onClick={() => addLog("SYSTEM", "A03: Injection 카테고리입니다.")}>
                  <circle cx="400" cy="180" r="18" fill="#78716C" />
                  <text x="400" y="183" fill="#FFFFFF" fontSize="9" textAnchor="middle" fontWeight="bold">A03</text>
                </g>
                <g className="cursor-pointer" onClick={() => addLog("SYSTEM", "P01: Resource Management 성능 카테고리입니다.")}>
                  <circle cx="550" cy="200" r="18" fill="#57534E" />
                  <text x="550" y="203" fill="#FFFFFF" fontSize="9" textAnchor="middle" fontWeight="bold">P01</text>
                </g>

                {/* CWE Nodes */}
                <g className="cursor-pointer">
                  <circle cx="160" cy="130" r="14" fill="#D6D3D1" />
                  <text x="160" y="133" fill="#1C1917" fontSize="7" textAnchor="middle">CWE-284</text>
                </g>
                <g className="cursor-pointer">
                  <circle cx="400" cy="100" r="14" fill="#D6D3D1" />
                  <text x="400" y="103" fill="#1C1917" fontSize="7" textAnchor="middle">CWE-89</text>
                </g>
                <g className="cursor-pointer">
                  <circle cx="640" cy="130" r="14" fill="#D6D3D1" />
                  <text x="640" y="133" fill="#1C1917" fontSize="7" textAnchor="middle">CWE-401</text>
                </g>

                {/* Concepts (COMMITTED) */}
                <g className="cursor-pointer group" onClick={() => setSelectedConcept(concepts.find(c => c.name === "CSRF") || concepts[2])}>
                  <circle cx="100" cy="60" r="16" fill="#FEF2F2" stroke="#B91C1C" strokeWidth="1.5" />
                  <text x="100" y="63" fill="#B91C1C" fontSize="8" textAnchor="middle" fontWeight="bold">CSRF</text>
                </g>
                <g className="cursor-pointer" onClick={() => setSelectedConcept(concepts[0])}>
                  <circle cx="330" cy="40" r="16" fill="#FEF2F2" stroke="#B91C1C" strokeWidth="1.5" />
                  <text x="330" y="43" fill="#B91C1C" fontSize="8" textAnchor="middle" fontWeight="bold">SQLi</text>
                </g>
                <g className="cursor-pointer" onClick={() => setSelectedConcept(concepts[1])}>
                  <circle cx="470" cy="40" r="16" fill="#FEF2F2" stroke="#B91C1C" strokeWidth="1.5" />
                  <text x="470" y="43" fill="#B91C1C" fontSize="8" textAnchor="middle" fontWeight="bold">XSS</text>
                </g>
                <g className="cursor-pointer" onClick={() => setSelectedConcept(concepts[3])}>
                  <circle cx="580" cy="60" r="16" fill="#F0FDF4" stroke="#0F766E" strokeWidth="1.5" />
                  <text x="580" y="63" fill="#0F766E" fontSize="7" textAnchor="middle" fontWeight="bold">N+1Q</text>
                </g>

                {/* --- DRAFT 가상 노드 (MemoryLeak) 미리보기 스타일 구현 --- */}
                {showDraftMode && (
                  <g 
                    className="cursor-pointer animate-pulse" 
                    onClick={() => {
                      setSelectedConcept(DRAFT_CONCEPTS_MOCK[0]);
                      addLog("SYSTEM", "가상 DRAFT 노드 MemoryLeak을 선택했습니다. 우측 패널에서 상세 정보를 사전 확인하세요.");
                    }}
                  >
                    <circle 
                      cx="700" cy="60" r="18" 
                      fill="#FEF3C7" 
                      stroke="#D97706" 
                      strokeWidth="2" 
                      strokeDasharray="4,4" 
                    />
                    <text x="700" y="63" fill="#D97706" fontSize="8" textAnchor="middle" fontWeight="bold">Leak</text>
                    <rect x="670" y="25" width="60" height="12" rx="3" fill="#D97706" />
                    <text x="700" y="34" fill="#FFFFFF" fontSize="6" textAnchor="middle" fontWeight="bold">병합 대기</text>
                  </g>
                )}

                {/* COMMITTED 전환 완료 시 노드 스타일 갱신 */}
                {pipelineState === "FINISHED" && (
                  <g className="cursor-pointer" onClick={() => setSelectedConcept(concepts[4] || concepts[3])}>
                    <circle cx="700" cy="60" r="18" fill="#F5F3FF" stroke="#7D52F4" strokeWidth="2" />
                    <text x="700" y="63" fill="#7D52F4" fontSize="8" textAnchor="middle" fontWeight="bold">Leak</text>
                    <rect x="670" y="25" width="60" height="12" rx="3" fill="#7D52F4" />
                    <text x="700" y="34" fill="#FFFFFF" fontSize="6" textAnchor="middle" fontWeight="bold">교차 도메인</text>
                  </g>
                )}
              </svg>

              {/* Staging Control Floating Bar */}
              {showDraftMode && (
                <div className="absolute bottom-4 left-4 right-4 bg-white/95 backdrop-blur-sm border border-amber-300 rounded-xl p-3.5 flex items-center justify-between shadow-lg">
                  <div className="flex items-center space-x-2">
                    <span className="w-2 h-2 rounded-full bg-amber-500 animate-ping"></span>
                    <span className="text-xs font-bold text-stone-800">
                      가상 노드 병합 예비 요약: 신규 1개 / 병합 예약 1개
                    </span>
                  </div>
                  <div className="flex space-x-2">
                    <button
                      onClick={approveAllStaging}
                      className="px-4 py-1.5 text-xs bg-[#115E59] text-white rounded-lg font-bold hover:bg-[#0e4e4a] transition-all"
                    >
                      최종 승인 게이트 통과
                    </button>
                    <button
                      onClick={rejectStaging}
                      className="px-3 py-1.5 text-xs border border-stone-200 text-stone-600 rounded-lg hover:bg-stone-50 transition-all"
                    >
                      전체 반려
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>

          {/* CONCEPT INSPECTOR (보안 및 성능 개념 인스펙터) */}
          <div className="bg-white rounded-2xl border border-stone-200/70 p-6 shadow-sm shadow-stone-100">
            <div className="flex items-center justify-between mb-6 border-b border-stone-100 pb-4">
              <div>
                <h3 className="font-serif text-base font-bold text-stone-900">
                  보안 및 성능 개념(Concept) 인스펙터
                </h3>
                <p className="text-xs text-stone-400 mt-0.5">
                  도메인별로 선별 조회하거나 고유 식별 명칭의 마스터 상세 정보들을 조회합니다.
                </p>
              </div>

              {/* Tabs */}
              <div className="flex bg-stone-100 p-0.5 rounded-lg border border-stone-200/60">
                {[
                  { id: "all", label: "전체 기술" },
                  { id: "security", label: "보안 취약점" },
                  { id: "performance", label: "성능 안티패턴" }
                ].map((t) => (
                  <button
                    key={t.id}
                    onClick={() => setActiveTab(t.id)}
                    className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${
                      activeTab === t.id 
                        ? 'bg-white text-stone-900 shadow-xs' 
                        : 'text-stone-500 hover:text-stone-950'
                    }`}
                  >
                    {t.label}
                  </button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
              
              {/* Concept Selector Panel */}
              <div className="md:col-span-4 border-r border-stone-100 pr-4 max-h-[280px] overflow-y-auto space-y-2">
                {filteredConcepts.map((c) => {
                  const isSelected = selectedConcept.name === c.name;
                  return (
                    <button
                      key={c.name}
                      onClick={() => setSelectedConcept(c)}
                      className={`w-full text-left p-3 rounded-xl border transition-all ${
                        isSelected 
                          ? 'bg-[#FAF8F5] border-stone-300 shadow-xs' 
                          : 'bg-white border-stone-200/60 hover:bg-stone-50/50'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-stone-900 font-serif">{c.name}</span>
                        <span className={`text-[9px] px-1.5 py-0.5 rounded-md font-bold uppercase ${
                          c.severity === "critical" 
                            ? "bg-rose-50 text-rose-700 border border-rose-200" 
                            : "bg-amber-50 text-amber-700 border border-amber-200"
                        }`}>
                          {c.severity}
                        </span>
                      </div>
                      <div className="flex items-center justify-between mt-2">
                        <span className="text-[10px] text-stone-400">{c.cwe_id}</span>
                        <div className="flex gap-1">
                          {c.domains.map(d => (
                            <span 
                              key={d} 
                              className="text-[8px] px-1 rounded-md font-bold"
                              style={{
                                color: DOMAIN_REGISTRY[d]?.color_hex || '#7C3AED',
                                backgroundColor: DOMAIN_REGISTRY[d]?.bg_hex || '#F5F3FF',
                                border: `1px solid ${DOMAIN_REGISTRY[d]?.border_hex || '#C7D2FE'}`
                              }}
                            >
                              {DOMAIN_REGISTRY[d]?.label_ko || "기타"}
                            </span>
                          ))}
                        </div>
                      </div>
                    </button>
                  );
                })}
              </div>

              {/* Concept Details Panel */}
              <div className="md:col-span-8 flex flex-col justify-between">
                {selectedConcept ? (
                  <div className="space-y-4">
                    <div className="flex items-start justify-between">
                      <div>
                        <h4 className="font-serif text-lg font-bold text-stone-900 flex items-center space-x-2">
                          <span>{selectedConcept.name}</span>
                          <span className="text-xs font-mono text-stone-400 font-normal">({selectedConcept.cwe_id})</span>
                        </h4>
                        <div className="flex items-center space-x-2 mt-1">
                          <span className="text-xs text-stone-500">동의어:</span>
                          {selectedConcept.aliases.map((a, idx) => (
                            <span key={idx} className="text-[10px] px-1.5 py-0.5 bg-stone-100 text-stone-600 rounded-md font-medium">
                              {a}
                            </span>
                          ))}
                        </div>
                      </div>
                      <div className="flex space-x-1.5">
                        {selectedConcept.domains.map(d => (
                          <span 
                            key={d} 
                            className="text-xs px-2.5 py-1 rounded-full font-bold"
                            style={{
                              color: DOMAIN_REGISTRY[d]?.color_hex || '#7C3AED',
                              backgroundColor: DOMAIN_REGISTRY[d]?.bg_hex || '#F5F3FF',
                              border: `1px solid ${DOMAIN_REGISTRY[d]?.border_hex || '#C7D2FE'}`
                            }}
                          >
                            {DOMAIN_REGISTRY[d]?.label_ko || "기타"}
                          </span>
                        ))}
                      </div>
                    </div>

                    <p className="text-xs text-stone-600 leading-relaxed bg-[#FAF8F5] p-3.5 rounded-xl border border-stone-200/50">
                      {selectedConcept.description_ko}
                    </p>

                    <div className="grid grid-cols-2 gap-4 text-xs">
                      <div>
                        <span className="text-stone-400 font-bold block mb-1">근본 원인 (Root Cause)</span>
                        <p className="text-stone-700 font-medium">{selectedConcept.root_cause}</p>
                      </div>
                      <div>
                        <span className="text-stone-400 font-bold block mb-1">영향 컴포넌트</span>
                        <div className="flex flex-wrap gap-1 mt-1">
                          {selectedConcept.affected_components.map((c, i) => (
                            <span key={i} className="px-2 py-0.5 bg-stone-100 text-[#0F766E] rounded text-[10px] font-mono">
                              {c}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>

                    <div className="border-t border-stone-100 pt-3">
                      <span className="text-xs text-stone-400 font-bold block mb-1.5">대응 보안 메커니즘 / 권장 기술</span>
                      <div className="flex flex-wrap gap-1.5">
                        {selectedConcept.security_mechanisms.map((m, i) => (
                          <span key={i} className="px-2.5 py-1 bg-stone-100 text-stone-800 rounded-lg text-xs font-semibold">
                            ✓ {m}
                          </span>
                        ))}
                      </div>
                    </div>

                  </div>
                ) : (
                  <div className="text-center py-12 text-stone-400 italic text-sm">
                    상세 속성을 조회할 개념(Concept) 노드를 선택하세요.
                  </div>
                )}

                <div className="text-[10px] text-stone-400 border-t border-stone-100 pt-3 mt-4 flex items-center justify-between">
                  <span>추출 출처: {selectedConcept?.owasp_id ? `OWASP Category ${selectedConcept.owasp_id}` : "Performance Autonomic Seed Source"}</span>
                  <span>신입사원 코드 검수 대응용 지식 자산</span>
                </div>
              </div>

            </div>

          </div>

        </section>

      </main>

      {/* --- FOOTER --- */}
      <footer className="border-t border-stone-200/60 bg-white py-6 mt-12 text-center text-xs text-stone-400">
        <p>© 2026 Knowledge Graph Agent Pipeline. All rights reserved. (Consistent Multi-Domain Schema v2)</p>
      </footer>
    </div>
  );
}