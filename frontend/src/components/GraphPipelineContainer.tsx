import { useState, useCallback, useEffect } from "react";
import type { GraphNode, GraphEdge, PipelineState, ToastKind, PrescanResult } from "@/types/graphPipeline";
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
  const [duplicateUrl, setDuplicateUrl]   = useState<string | null>(null);
  const [prescanResult, setPrescanResult] = useState<PrescanResult | null>(null);

  const addLog = useCallback((line: string) => {
    setLogs((prev) => [...prev, line]);
  }, []);

  const handleFinished = useCallback(() => {
    setPipelineState("WAITING_APPROVAL");
    onToast("success", "파이프라인 완료 — HITL 승인을 진행해 주세요.");
    fetchStaging();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSSEError = useCallback((msg: string) => {
    setPipelineState("ERROR");
    onToast("error", msg);
  }, [onToast]);

  const { stepStatuses, isConnected, reset: resetSSE } = useGraphPipelineSSE({
    sessionId,
    onLog: addLog,
    onFinished: handleFinished,
    onError: handleSSEError,
  });

  const {
    stagingItems,
    diff,
    isLoading: isApprovalLoading,
    fetchStaging,
    approveAll,
    rejectAll,
    commit,
  } = useGraphStagingApproval({ sessionId, onToast });

  const { draftNodes, draftEdges, applyDraftNodes, clearDraft } = useGraphMerge();

  useEffect(() => {
    if (stagingItems.length > 0) {
      applyDraftNodes(stagingItems, baseNodes);
    }
  }, [stagingItems, baseNodes, applyDraftNodes]);

  const handlePipelineStarted = useCallback((sid: string) => {
    setSessionId(sid);
    setLogs([]);
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
    await commit();
    clearDraft();
    await loadTopology();
    setPipelineState("FINISHED");
    onToast("success", "지식 그래프 적재 완료");
  }, [commit, clearDraft, loadTopology, onToast]);

  const allNodes = [
    ...baseNodes,
    ...draftNodes.filter((d) => !baseNodes.find((b) => b.id === d.id)),
  ];
  const allEdges = [...baseEdges, ...draftEdges];

  const isDraftSelected = Boolean(
    selectedNode && stagingItems.find((s) => s.id === selectedNode.id)
  );

  return (
    <div className="flex h-full flex-col gap-4 p-4">
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
      <div className="grid flex-1 grid-cols-[220px_1fr_260px] gap-4 overflow-hidden">
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
              onNodeClick={setSelectedNode}
            />
          )}
        </div>

        {/* Right: HITL 승인 + 인스펙터 */}
        <div className="flex flex-col gap-4 overflow-auto">
          {pipelineState === "WAITING_APPROVAL" && (
            <div className="flex flex-col gap-2">
              <GraphApprovalPanel
                diff={diff}
                isLoading={isApprovalLoading}
                onApproveAll={() => void approveAll()}
                onRejectAll={() => void rejectAll()}
              />
              <GraphButton
                variant="outline"
                onClick={() => void handleCommit()}
                disabled={isApprovalLoading || pipelineState !== "WAITING_APPROVAL"}
              >
                그래프에 반영 (Commit)
              </GraphButton>
            </div>
          )}
          <GraphConceptInspector
            node={selectedNode}
            isDraft={isDraftSelected}
            onApprove={(id) => {
              const item = stagingItems.find((s) => s.id === id);
              if (item) void graphPipelineApi.approveSingle(item.staging_id);
            }}
            onReject={(id) => {
              const item = stagingItems.find((s) => s.id === id);
              if (item) void graphPipelineApi.rejectSingle(item.staging_id);
            }}
            onClose={() => setSelectedNode(null)}
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
      {prescanResult && (prescanResult.infer_confidence ?? 1) < 0.8 && (
        <GraphMetadataLearnModal
          prescanResult={prescanResult}
          suggestions={prescanResult.suggestions ?? []}
          onSubmit={async (payload) => {
            await graphPipelineApi.learnMetadata(payload);
            setPrescanResult(null);
            onToast("success", "메타데이터 학습 완료");
          }}
          onCancel={() => setPrescanResult(null)}
        />
      )}
    </div>
  );
}
