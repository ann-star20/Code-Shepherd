import { useState } from "react";
import type { ConceptNode } from "@/types/concept";
import type { GraphNode } from "@/types/graph";
import { useDocumentInput } from "@/hooks/useDocumentInput";
import { usePipelineSSE } from "@/hooks/usePipelineSSE";
import { useStagingApproval } from "@/hooks/useStagingApproval";
import { DashboardLayout } from "@/components/templates/DashboardLayout";
import { MetadataForm } from "@/components/molecules/MetadataForm";
import { PipelineStepIndicator } from "@/components/molecules/PipelineStepIndicator";
import { LogConsole } from "@/components/organisms/LogConsole";
import { TopologyViewer } from "@/components/organisms/TopologyViewer";
import { ApprovalPanel } from "@/components/organisms/ApprovalPanel";
import { ConceptInspector } from "@/components/organisms/ConceptInspector";
import { Button } from "@/components/atoms/Button";

export function MainPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [selectedNode, setSelectedNode] = useState<ConceptNode | null>(null);
  const [urlInput, setUrlInput] = useState("");

  const input = useDocumentInput();
  const sse = usePipelineSSE(sessionId);
  const approval = useStagingApproval(sessionId);

  async function handleTrigger() {
    const sid = await input.triggerPipeline();
    setSessionId(sid);
  }

  function handleNodeClick(gn: GraphNode) {
    const record = approval.records.find((r) => r.id === gn.id);
    if (record) {
      setSelectedNode(record.concept_json);
    } else {
      setSelectedNode({
        id: gn.id,
        name: gn.name,
        domain: gn.domain,
        status: gn.status,
        aliases: [],
        tags: [],
      });
    }
  }

  const sidebar = (
    <div className="flex flex-col gap-4 p-4">
      <h1 className="text-sm font-semibold text-gray-700">Knowledge Graph Agent</h1>
      <div className="flex gap-2">
        <input
          type="text"
          value={urlInput}
          onChange={(e) => setUrlInput(e.target.value)}
          placeholder="URL 입력"
          className="flex-1 rounded border px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-blue-400"
        />
      </div>
      <MetadataForm
        urls={input.urls}
        prescanResult={input.prescanResult ?? undefined}
        confidence={input.confidence}
        onConfirm={input.confirmMetadata}
        onAddUrl={() => {
          if (urlInput.trim()) {
            input.addUrl(urlInput.trim());
            setUrlInput("");
          }
        }}
        onRemoveUrl={input.removeUrl}
      />
      <Button
        variant="primary"
        onClick={handleTrigger}
        disabled={input.urls.length === 0 || input.isPending}
      >
        파이프라인 시작
      </Button>
      <PipelineStepIndicator steps={sse.steps} />
      <LogConsole logs={sse.logs} isConnected={sse.isConnected} />
    </div>
  );

  const main = (
    <TopologyViewer sessionId={sessionId} onNodeClick={handleNodeClick} />
  );

  const inspector = (
    <div className="flex flex-col gap-4 p-4">
      <ApprovalPanel
        sessionId={sessionId}
        diff={approval.diff}
        isLoading={approval.isLoading}
        onApproveAll={approval.approveAll}
        onRejectAll={approval.rejectAll}
      />
      <ConceptInspector
        node={selectedNode}
        sessionId={sessionId}
        onApprove={(id) => approval.patchNode(id, "APPROVED")}
        onReject={(id) => approval.patchNode(id, "REJECTED")}
        onClose={() => setSelectedNode(null)}
      />
    </div>
  );

  return <DashboardLayout sidebar={sidebar} main={main} inspector={inspector} />;
}
