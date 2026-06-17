import { useState, useCallback, useEffect, useRef } from "react";
import type { Domain, GraphNode, GraphEdge, PipelineState, ToastKind, PrescanResult, StepName } from "@/types/graphPipeline";
import { graphPipelineApi } from "@/lib/graphPipelineApi";
import { useGraphPipelineSSE } from "@/hooks/useGraphPipelineSSE";
import { useGraphStagingApproval } from "@/hooks/useGraphStagingApproval";
import { useGraphMerge } from "@/hooks/useGraphMerge";
import { useGraphDocumentInput } from "@/hooks/useGraphDocumentInput";
import { GraphPipelineStepIndicator } from "./GraphPipelineStepIndicator";
import { GraphApprovalPanel } from "./GraphApprovalPanel";
import { GraphConceptInspector } from "./GraphConceptInspector";
import { GraphTopologyViewer } from "./GraphTopologyViewer";
import { GraphLogConsole } from "./GraphLogConsole";
import { GraphDuplicateDocumentModal } from "./GraphDuplicateDocumentModal";
import { GraphMetadataLearnModal } from "./GraphMetadataLearnModal";
import { GraphDomainSelect } from "./GraphDomainSelect";
import { GraphConceptList } from "./GraphConceptList";
import { GraphButton } from "./GraphBadge";

interface GraphPipelineContainerProps {
  onToast: (kind: ToastKind, message: string) => void;
}

export function GraphPipelineContainer({ onToast }: GraphPipelineContainerProps) {
  const [pipelineState, setPipelineState] = useState<PipelineState>("IDLE");
  const [sessionId, setSessionId]         = useState<string | null>(null);
  const [logs, setLogs]                   = useState<string[]>([]);
  const [baseNodes, setBaseNodes]         = useState<GraphNode[]>([]);
  const [baseEdges, setBaseEdges]         = useState<GraphEdge[]>([]);
  const [selectedNode, setSelectedNode]   = useState<GraphNode | null>(null);
  const [selectedDomain, setSelectedDomain]     = useState<Domain | "all">("all");
  const [selectedConceptId, setSelectedConceptId] = useState<string | null>(null);
  const [duplicateUrl, setDuplicateUrl]   = useState<string | null>(null);
  const [prescanResult, setPrescanResult] = useState<PrescanResult | null>(null);
  const [errorMessage, setErrorMessage]   = useState<string | null>(null);
  const errorMessageRef = useRef<string | null>(null);

  const addLog = useCallback((line: string) => {
    setLogs((prev) => [...prev, line]);
  }, []);

  const {
    stagingItems,
    diff,
    isLoading: isApprovalLoading,
    fetchStaging,
    approveAll,
    rejectAll,
    approveSingle,
    rejectSingle,
    commit,
  } = useGraphStagingApproval({ sessionId, onToast });

  const fetchStagingRef = useRef(fetchStaging);
  useEffect(() => {
    fetchStagingRef.current = fetchStaging;
  }, [fetchStaging]);

  const skippedRef = useRef(false);

  const handleFinished = useCallback(() => {
    if (skippedRef.current) {
      skippedRef.current = false;
      // 에러가 있으면 ERROR 상태 유지 (handleStepFailed가 이미 설정)
      if (!errorMessageRef.current) {
        setPipelineState("IDLE");
      }
      return;
    }
    setPipelineState("WAITING_APPROVAL");
    onToast("success", "파이프라인 완료 — HITL 승인을 진행해 주세요.");
    fetchStagingRef.current();
  }, [onToast]);

  const handleSSEError = useCallback((msg: string) => {
    setPipelineState("ERROR");
    onToast("error", msg);
  }, [onToast]);

  const handleSkipped = useCallback((reason: string) => {
    skippedRef.current = true;
    onToast("warning", reason);
  }, [onToast]);

  const handleStepFailed = useCallback((step: StepName, reason: string) => {
    skippedRef.current = true;
    errorMessageRef.current = reason;
    setErrorMessage(reason);
    setPipelineState("ERROR");
    onToast("error", reason);
  }, [onToast]);

  const handleMetadataRequired = useCallback(
    (payload: { doc_id: string; url: string; suggestions: string[] }) => {
      setPrescanResult({
        original_url: payload.url,
        doc_id: payload.doc_id,
        suggestions: payload.suggestions,
      });
      onToast("warning", "프레임워크를 자동으로 인식하지 못했습니다. 메타데이터를 입력해 주세요.");
    },
    [onToast]
  );

  const { stepStatuses, isConnected, reset: resetSSE, setStepStatus } = useGraphPipelineSSE({
    sessionId,
    onLog: addLog,
    onFinished: handleFinished,
    onError: handleSSEError,
    onSkipped: handleSkipped,
    onMetadataRequired: handleMetadataRequired,
    onStepFailed: handleStepFailed,
  });

  const { draftNodes, draftEdges, applyDraftNodes, clearDraft } = useGraphMerge();

  useEffect(() => {
    if (stagingItems.length > 0) {
      applyDraftNodes(stagingItems, baseNodes);
    }
  }, [stagingItems, baseNodes, applyDraftNodes]);

  const handlePipelineStarted = useCallback((sid: string) => {
    skippedRef.current = false;
    errorMessageRef.current = null;
    setSessionId(sid);
    setLogs([]);
    setErrorMessage(null);
    resetSSE();
    setPipelineState("RUNNING");
    onToast("info", "파이프라인 시작됨");
  }, [onToast, resetSSE]);

  const { url, setUrl, isChecking, handleSubmit } = useGraphDocumentInput({
    onToast,
    onPipelineStarted: handlePipelineStarted,
    onDuplicateDetected: (u) => setDuplicateUrl(u),
  });

  const loadTopology = useCallback(async () => {
    try {
      const res = await graphPipelineApi.getTopology();
      setBaseNodes(res.data.nodes as GraphNode[]);
      setBaseEdges(res.data.edges as GraphEdge[]);
    } catch {
      onToast("warning", "토폴로지 로드에 실패했습니다.");
    }
  }, [onToast]);

  useEffect(() => {
    void loadTopology();
  }, [loadTopology]);

  const handleCommit = useCallback(async () => {
    setPipelineState("COMMITTING");
    setStepStatus("Writer", "RUNNING");
    const success = await commit();
    if (success) {
      setStepStatus("Writer", "DONE");
      await fetchStagingRef.current();
      clearDraft();
      await loadTopology();
      setPipelineState("FINISHED");
    } else {
      setStepStatus("Writer", "FAILED");
      setPipelineState("ERROR");
    }
  }, [commit, clearDraft, loadTopology, setStepStatus]);

  const handleRejectAll = useCallback(async () => {
    await rejectAll();
    clearDraft();
    setStepStatus("Writer", "FAILED");
    setPipelineState("ERROR");
  }, [rejectAll, clearDraft, setStepStatus]);

  const handleApproveAll = useCallback(async () => {
    await approveAll();
    await handleCommit();
  }, [approveAll, handleCommit]);

  const allNodes = [
    ...baseNodes,
    ...draftNodes.filter((d) => !baseNodes.find((b) => b.id === d.id)),
  ];
  const allEdges = [...baseEdges, ...draftEdges];

  const isDraftSelected = Boolean(
    selectedNode &&
      stagingItems.find((s) => s.id === selectedNode.id && s.state === "DRAFT")
  );

  const handleNodeClick = useCallback((node: GraphNode) => {
    setSelectedNode(node);
    if (node.node_type === "Concept") {
      setSelectedConceptId(node.id);
    }
  }, []);

  const handleConceptSelect = useCallback(
    (id: string) => {
      setSelectedConceptId(id);
      const node = allNodes.find((n) => n.id === id);
      if (node) setSelectedNode(node);
    },
    [allNodes]
  );

  return (
    <div className="flex h-full flex-col gap-4 p-4">
      {/* 에러 배너 */}
      {pipelineState === "ERROR" && errorMessage && (
        <div className="flex items-center gap-3 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm">
          <span className="flex-1 text-red-700">{errorMessage}</span>
          <button
            type="button"
            onClick={() => void handleSubmit()}
            className="rounded-md bg-red-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-red-700 active:bg-red-800"
          >
            재시도
          </button>
          <button
            type="button"
            aria-label="에러 닫기"
            onClick={() => { errorMessageRef.current = null; setErrorMessage(null); setPipelineState("IDLE"); }}
            className="text-red-400 hover:text-red-600"
          >
            ✕
          </button>
        </div>
      )}

      {/* URL 입력 바 */}
      <div className="flex gap-2">
        <input
          type="url"
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") void handleSubmit(); }}
          placeholder="https://docs.example.com/..."
          disabled={pipelineState === "RUNNING" || pipelineState === "COMMITTING"}
          className="flex-1 rounded-lg border border-gray-300 px-3 py-2 text-sm
                     focus:outline-none focus:ring-2 focus:ring-blue-500
                     disabled:bg-gray-100 disabled:cursor-not-allowed"
        />
        <GraphButton
          variant="primary"
          onClick={() => void handleSubmit()}
          disabled={isChecking || pipelineState === "RUNNING" || pipelineState === "COMMITTING"}
        >
          {isChecking ? "확인 중..." : "지식화 시작"}
        </GraphButton>
      </div>

      {/* 3-Column Layout */}
      <div className="grid flex-1 grid-cols-[220px_1fr_400px] gap-4 overflow-hidden">
        {/* Left: 파이프라인 단계 + 로그 */}
        <div className="flex flex-col gap-4 overflow-auto">
          <div className="rounded-lg border bg-white p-3 shadow-sm">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
              Pipeline
            </h2>
            <GraphPipelineStepIndicator statuses={stepStatuses} />
          </div>
          <GraphLogConsole logs={logs} isConnected={isConnected} />
        </div>

        {/* Center: 토폴로지 뷰어 */}
        <div className="relative overflow-hidden rounded-lg border shadow-sm" style={{ minHeight: 400 }}>
          {allNodes.length === 0 ? (
            <div className="flex h-full items-center justify-center text-sm text-gray-400">
              적재된 개념이 없습니다
            </div>
          ) : (
            <GraphTopologyViewer
              nodes={allNodes}
              edges={allEdges}
              onNodeClick={handleNodeClick}
              focusNodeId={selectedConceptId}
            />
          )}
        </div>

        {/* Right: 도메인/개념 선택 + HITL 승인 + 인스펙터 */}
        <div className="flex flex-col gap-4 overflow-auto">
          {pipelineState === "WAITING_APPROVAL" && (
            <GraphApprovalPanel
              diff={diff}
              isLoading={isApprovalLoading}
              stagingItems={stagingItems}
              onApproveAll={() => void handleApproveAll()}
              onRejectAll={() => void handleRejectAll()}
              onSelectItem={handleNodeClick}
            />
          )}
          <div className="rounded-lg border bg-white p-3 shadow-sm">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
              도메인
            </h2>
            <GraphDomainSelect value={selectedDomain} onChange={setSelectedDomain} />
          </div>
          <div className="flex max-h-48 flex-col rounded-lg border bg-white p-3 shadow-sm">
            <h2 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
              개념 (Concept)
            </h2>
            <div className="overflow-y-auto">
              <GraphConceptList
                nodes={allNodes}
                selectedDomain={selectedDomain}
                selectedConceptId={selectedConceptId}
                onSelect={handleConceptSelect}
              />
            </div>
          </div>
          <GraphConceptInspector
            node={selectedNode}
            allNodes={allNodes}
            edges={allEdges}
            isDraft={isDraftSelected}
            onApprove={(id) => {
              const item = stagingItems.find((s) => s.id === id);
              if (item) void approveSingle(item.staging_id);
            }}
            onReject={(id) => {
              const item = stagingItems.find((s) => s.id === id);
              if (item) void rejectSingle(item.staging_id);
            }}
            onClose={() => {
              setSelectedNode(null);
              setSelectedConceptId(null);
            }}
          />
        </div>
      </div>

      {/* Modals */}
      {duplicateUrl && (
        <GraphDuplicateDocumentModal
          url={duplicateUrl}
          onClose={() => setDuplicateUrl(null)}
        />
      )}
      {prescanResult && (
        <GraphMetadataLearnModal
          prescanResult={prescanResult}
          suggestions={prescanResult.suggestions ?? []}
          onSubmit={async (payload) => {
            await graphPipelineApi.learnMetadata(payload);
            if (sessionId && prescanResult.doc_id) {
              await graphPipelineApi.resumeMetadata({
                session_id: sessionId,
                doc_id: prescanResult.doc_id,
                url: prescanResult.original_url,
                framework: payload.framework,
                lang: payload.default_lang ?? payload.supported_langs[0],
              });
            }
            setPrescanResult(null);
            onToast("success", "메타데이터 학습 완료 — 파이프라인을 재개합니다.");
          }}
          onCancel={() => {
            if (sessionId && prescanResult.doc_id) {
              void graphPipelineApi.resumeMetadata({
                session_id: sessionId,
                doc_id: prescanResult.doc_id,
                url: prescanResult.original_url,
              });
            }
            setPrescanResult(null);
            onToast("info", "빈 값으로 파이프라인을 진행합니다.");
          }}
        />
      )}
    </div>
  );
}
