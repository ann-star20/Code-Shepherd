import { useEffect, useMemo, useState } from "react";
import {
  getGraphOverview,
  getConceptGraph,
  getRankedRecommendations,
  type CodeExampleMeta,
  type ConceptGraphResponse,
  type ConceptOverview,
  type MechanismMeta,
  type VideoResult,
} from "../../lib/m5Api";
import type { Domain, GraphEdge, GraphNode } from "@/types/graphPipeline";
import { GraphTopologyViewer } from "@/components/GraphTopologyViewer";
import VideoRankCard from "./VideoRankCard";

// ── 전체 개요 → GraphNode/GraphEdge 변환 (Domain 포함) ───────────────────────

function buildOverviewGraph(
  concepts: ConceptOverview[],
  filterText: string
): { nodes: GraphNode[]; edges: GraphEdge[]; mechToConceptMap: Map<string, string> } {
  const q = filterText.trim().toLowerCase();
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const mechToConceptMap = new Map<string, string>();
  const mechSeen = new Set<string>();
  const domainSeen = new Set<string>();
  const FALLBACK_DOMAIN = "기타";

  for (const c of concepts) {
    const matchesConcept = !q || c.concept_name.toLowerCase().includes(q);
    const matchesMech = !q || c.mechanism_names.some((m) => m.toLowerCase().includes(q));
    if (!matchesConcept && !matchesMech) continue;

    // c.domain_names 값은 "security" | "performance" 등 Domain 타입과 동일
    const conceptDomains = c.domain_names.filter(Boolean) as Domain[];
    nodes.push({
      id: c.concept_name,
      name: c.concept_name,
      status: "COMMITTED",
      domains: conceptDomains,
      node_type: "Concept",
      layer: "L2",
      severity: c.severity ?? undefined,
    });

    // Domain 노드 — 없으면 "기타" 가상 노드로 연결
    const targetDomains = conceptDomains.length > 0 ? conceptDomains : [FALLBACK_DOMAIN];
    for (const domainName of targetDomains) {
      if (!domainSeen.has(domainName)) {
        domainSeen.add(domainName);
        nodes.push({
          id: domainName,
          name: domainName,
          status: "COMMITTED",
          domains: [],
          node_type: "Domain",
          layer: "L1",
        });
      }
      edges.push({ source: c.concept_name, target: domainName as string, type: "BELONGS_TO" });
    }

    // Mechanism 노드
    for (const mechName of c.mechanism_names) {
      mechToConceptMap.set(mechName, c.concept_name);
      if (!mechSeen.has(mechName)) {
        mechSeen.add(mechName);
        nodes.push({
          id: mechName,
          name: mechName,
          status: "COMMITTED",
          domains: [],
          node_type: "Mechanism",
          layer: "L3",
        });
      }
      edges.push({ source: c.concept_name, target: mechName, type: "MITIGATED_BY" });
    }
  }

  return { nodes, edges, mechToConceptMap };
}

// ── 코드예제 중복 제거 — (framework, lang) 쌍 기준 ──────────────────────────

function deduplicateCodes(codes: CodeExampleMeta[]): CodeExampleMeta[] {
  const seen = new Set<string>();
  return codes.filter((ce) => {
    const key = `${ce.framework ?? ""}|${ce.lang ?? ""}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

const SEVERITY_COLOR: Record<string, string> = {
  CRITICAL: "text-red-600",
  HIGH: "text-orange-500",
  MEDIUM: "text-yellow-600",
  LOW: "text-green-600",
};

// ── 컴포넌트 ─────────────────────────────────────────────────────────────────

type Selection = {
  concept: ConceptGraphResponse | null;
  mechanism: MechanismMeta | null;
  code: CodeExampleMeta | null;
};

export default function YoutubeRecommendPage() {
  const [overview, setOverview] = useState<ConceptOverview[]>([]);
  const [overviewError, setOverviewError] = useState<string | null>(null);
  const [filterText, setFilterText] = useState("");

  const [selection, setSelection] = useState<Selection>({ concept: null, mechanism: null, code: null });
  const [isLoadingDetail, setIsLoadingDetail] = useState(false);

  const [isRecommending, setIsRecommending] = useState(false);
  const [recommendError, setRecommendError] = useState<string | null>(null);
  const [videos, setVideos] = useState<VideoResult[]>([]);
  const [hasSearched, setHasSearched] = useState(false);

  // 마운트 시 전체 그래프 로드
  useEffect(() => {
    getGraphOverview()
      .then((resp) => setOverview(resp.concepts))
      .catch((err) => setOverviewError((err as Error).message));
  }, []);

  // 그래프 데이터
  const { nodes, edges, mechToConceptMap } = useMemo(
    () => buildOverviewGraph(overview, filterText),
    [overview, filterText]
  );

  const focusNodeId = useMemo(() => {
    if (selection.mechanism) return selection.mechanism.mechanism_name;
    if (selection.concept) return selection.concept.concept_name;
    if (filterText.trim()) {
      const q = filterText.trim().toLowerCase();
      return overview.find((c) => c.concept_name.toLowerCase().includes(q))?.concept_name ?? null;
    }
    return null;
  }, [selection, filterText, overview]);

  // 그래프 노드 클릭
  async function handleNodeClick(node: GraphNode) {
    if (node.node_type === "Domain") return;
    setIsLoadingDetail(true);
    setVideos([]);
    setHasSearched(false);
    try {
      if (node.node_type === "Concept") {
        const detail = await getConceptGraph(node.name);
        setSelection({ concept: detail, mechanism: null, code: null });
      } else if (node.node_type === "Mechanism") {
        const parentName = mechToConceptMap.get(node.id);
        if (!parentName) return;
        const detail = await getConceptGraph(parentName);
        const mech = detail.mechanisms.find((m) => m.mechanism_name === node.id) ?? null;
        setSelection({ concept: detail, mechanism: mech, code: null });
      }
    } catch (err) {
      setOverviewError((err as Error).message);
    } finally {
      setIsLoadingDetail(false);
    }
  }

  // 매커니즘 클릭 (패널)
  function handleMechanismClick(mech: MechanismMeta) {
    setSelection((prev) => ({
      ...prev,
      mechanism: prev.mechanism?.mechanism_name === mech.mechanism_name ? null : mech,
      code: null,
    }));
    setVideos([]);
    setHasSearched(false);
  }

  // 코드 선택
  function selectCode(ce: CodeExampleMeta) {
    setSelection((prev) => ({
      ...prev,
      code: prev.code?.unq_id === ce.unq_id ? null : ce,
    }));
    setVideos([]);
    setHasSearched(false);
  }

  // YouTube 추천
  async function handleRecommend() {
    if (!selection.concept) return;
    setIsRecommending(true);
    setRecommendError(null);
    setVideos([]);
    setHasSearched(true);
    try {
      const resp = await getRankedRecommendations({
        concept_name: selection.concept.concept_name,
        mechanism_name: selection.mechanism?.mechanism_name ?? null,
        code_id: selection.code?.unq_id ?? null,
        code_lang: selection.code?.lang ?? null,
        code_framework: selection.code?.framework ?? null,
      });
      setVideos(resp.videos);
    } catch (err) {
      setRecommendError((err as Error).message);
    } finally {
      setIsRecommending(false);
    }
  }

  const { concept, mechanism, code } = selection;
  const uniqueCodes = useMemo(
    () => (mechanism ? deduplicateCodes(mechanism.code_examples) : []),
    [mechanism]
  );
  const canRecommend = !!concept && !isRecommending && !isLoadingDetail;

  return (
    <div className="flex h-full min-h-0">
      {/* ── 왼쪽 영역 ── */}
      <div className="flex flex-col flex-1 min-w-0 min-h-0">

        {/* ── 상단 필터 바 ── */}
        <div className="flex-shrink-0 flex items-center gap-2 px-3 py-2 border-b border-notion-border bg-white">
          <input
            type="text"
            value={filterText}
            onChange={(e) => setFilterText(e.target.value)}
            placeholder="개념·매커니즘 필터"
            className="w-44 px-2.5 py-1 text-xs border border-notion-border rounded bg-white focus:outline-none focus:ring-1 focus:ring-notion-text-secondary"
          />
          {isLoadingDetail && (
            <span className="text-xs text-notion-text-secondary animate-pulse">불러오는 중…</span>
          )}
        </div>

        {/* ── 정보 패널 3열: [컨셉 설명] [매커니즘] [프레임워크/언어] ── */}
        <div className="flex-shrink-0 flex border-b border-notion-border" style={{ height: "200px" }}>

          {/* 1열: 컨셉 설명 */}
          <div className="flex-1 min-w-0 p-3 overflow-y-auto border-r border-notion-border">
            {concept ? (
              <div className="flex flex-col gap-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-sm font-semibold text-notion-text">
                    {concept.concept_name}
                  </span>
                  {concept.severity && (
                    <span className={`text-xs font-medium ${SEVERITY_COLOR[concept.severity] ?? "text-notion-text-secondary"}`}>
                      {concept.severity}
                    </span>
                  )}
                  {concept.cwe_id && (
                    <span className="text-xs px-1.5 py-0.5 rounded bg-notion-bg-secondary text-notion-text-secondary">
                      {concept.cwe_id}
                    </span>
                  )}
                  {concept.owasp_id && (
                    <span className="text-xs px-1.5 py-0.5 rounded bg-notion-bg-secondary text-notion-text-secondary">
                      OWASP {concept.owasp_id}
                    </span>
                  )}
                </div>
                {concept.concept_desc && (
                  <p className="text-xs text-notion-text-secondary leading-relaxed">
                    {concept.concept_desc}
                  </p>
                )}
                {concept.affected_components.length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {concept.affected_components.map((comp) => (
                      <span key={comp} className="text-xs px-1.5 py-0.5 rounded bg-blue-50 text-blue-600">
                        {comp}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-xs text-notion-text-secondary mt-2">
                그래프에서 개념 노드를 클릭하세요.
              </p>
            )}
          </div>

          {/* 2열: 매커니즘 리스트 */}
          <div className="w-56 flex-shrink-0 p-3 overflow-y-auto flex flex-col gap-1 border-r border-notion-border">
            {concept && concept.mechanisms.length > 0 ? (
              <>
                <p className="text-xs font-medium text-notion-text-secondary uppercase tracking-wide mb-0.5">
                  매커니즘
                </p>
                {concept.mechanisms.map((mech) => {
                  const isSelected = mechanism?.mechanism_name === mech.mechanism_name;
                  return (
                    <button
                      key={mech.mechanism_name}
                      onClick={() => handleMechanismClick(mech)}
                      className={`text-left text-xs px-2 py-1.5 rounded border transition-colors ${
                        isSelected
                          ? "border-notion-text bg-notion-text text-white"
                          : "border-notion-border bg-white text-notion-text hover:bg-notion-bg-secondary"
                      }`}
                    >
                      {mech.mechanism_name}
                      {mech.code_examples.length > 0 && (
                        <span className="ml-1 opacity-50">({mech.code_examples.length})</span>
                      )}
                    </button>
                  );
                })}
              </>
            ) : (
              <p className="text-xs text-notion-text-secondary mt-2">
                {concept ? "매커니즘 없음" : "컨셉을 선택하세요"}
              </p>
            )}
          </div>

          {/* 3열: 프레임워크 / 언어 선택 */}
          <div className="w-56 flex-shrink-0 p-3 overflow-y-auto flex flex-col gap-1">
            <p className="text-xs font-medium text-notion-text-secondary uppercase tracking-wide mb-0.5">
              언어 / 프레임워크
            </p>
            {uniqueCodes.length > 0 ? (
              uniqueCodes.map((ce) => {
                const label = [ce.framework, ce.lang].filter(Boolean).join(" / ") || ce.unq_id;
                const isSelected = code?.unq_id === ce.unq_id;
                return (
                  <button
                    key={ce.unq_id}
                    onClick={() => selectCode(ce)}
                    className={`text-left text-xs px-2 py-1.5 rounded border transition-colors ${
                      isSelected
                        ? "border-blue-500 bg-blue-50 text-blue-700"
                        : "border-notion-border bg-white text-notion-text hover:bg-notion-bg-secondary"
                    }`}
                  >
                    {label}
                  </button>
                );
              })
            ) : (
              <p className="text-xs text-notion-text-secondary mt-1">
                {mechanism ? "코드예제 없음" : "매커니즘을 선택하세요"}
              </p>
            )}
          </div>
        </div>

        {/* ── 그래프 ── */}
        <div className="flex-1 min-h-0 p-3">
          {overviewError ? (
            <div className="flex h-full items-center justify-center text-red-500 text-sm">
              {overviewError}
            </div>
          ) : nodes.length === 0 ? (
            <div className="flex h-full items-center justify-center rounded-lg border border-notion-border bg-gray-50 text-notion-text-secondary text-sm animate-pulse">
              그래프 로딩 중…
            </div>
          ) : (
            <GraphTopologyViewer
              nodes={nodes}
              edges={edges}
              onNodeClick={handleNodeClick}
              focusNodeId={focusNodeId}
            />
          )}
        </div>
      </div>

      {/* ── 오른쪽: YouTube 추천 ── */}
      <div className="w-[494px] flex-shrink-0 flex flex-col border-l border-notion-border">
        {/* 추천 버튼 바 */}
        <div className="flex-shrink-0 px-3 py-2 border-b border-notion-border bg-white flex items-center gap-2">
          {concept ? (
            <div className="flex flex-wrap gap-1.5 items-center flex-1 min-w-0">
              <span className="text-xs font-medium text-notion-text truncate">
                {concept.concept_name}
              </span>
              {mechanism && (
                <span className="text-xs px-1.5 py-0.5 rounded-full bg-notion-text text-white">
                  {mechanism.mechanism_name}
                </span>
              )}
              {code && (
                <span className="text-xs px-1.5 py-0.5 rounded-full bg-blue-100 text-blue-700">
                  {[code.framework, code.lang].filter(Boolean).join("/")}
                </span>
              )}
            </div>
          ) : (
            <p className="text-xs text-notion-text-secondary flex-1">개념을 선택하세요</p>
          )}
          <button
            onClick={handleRecommend}
            disabled={!canRecommend}
            className={`flex-shrink-0 px-3 py-1 rounded text-xs font-medium transition-colors ${
              canRecommend
                ? "bg-orange-500 hover:bg-orange-600 text-white"
                : "bg-notion-bg-secondary text-notion-text-secondary cursor-not-allowed"
            }`}
          >
            {isRecommending ? "추천 중…" : "▶ 추천 받기"}
          </button>
        </div>

        {/* 영상 목록 */}
        <div className="flex-1 overflow-y-auto p-3 flex flex-col gap-3">
          {recommendError && <p className="text-sm text-red-500">{recommendError}</p>}

          {isRecommending &&
            Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="flex gap-3 p-3 rounded-lg border border-notion-border animate-pulse">
                <div className="w-28 h-16 rounded bg-notion-bg-secondary flex-shrink-0" />
                <div className="flex-1 flex flex-col gap-2 justify-center">
                  <div className="h-3 rounded bg-notion-bg-secondary w-2/5" />
                  <div className="h-3 rounded bg-notion-bg-secondary w-full" />
                  <div className="h-3 rounded bg-notion-bg-secondary w-[80%]" />
                </div>
              </div>
            ))}

          {!isRecommending && videos.length === 0 && !recommendError && (
            <div className="flex flex-col items-center justify-center h-full text-notion-text-secondary gap-2">
              {hasSearched ? (
                <>
                  <p className="text-2xl">📭</p>
                  <p className="text-sm font-medium text-notion-text">영상을 찾지 못했습니다</p>
                  <p className="text-xs text-center">YOUTUBE_API_KEY를 확인해 주세요.</p>
                </>
              ) : (
                <>
                  <p className="text-2xl">{concept ? "🎬" : "▶️"}</p>
                  <p className="text-xs text-center leading-relaxed">
                    {concept ? "추천 버튼을 눌러 주세요." : "왼쪽 그래프에서\n개념 노드를 클릭하세요."}
                  </p>
                </>
              )}
            </div>
          )}

          {!isRecommending &&
            videos.length > 0 &&
            videos.map((v) => (
              <VideoRankCard key={v.rank} video={v} animationDelay={(v.rank - 1) * 80} />
            ))}
        </div>
      </div>
    </div>
  );
}
