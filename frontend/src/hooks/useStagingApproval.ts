import { useCallback, useEffect, useState } from "react";
import type { StagingRecord, DiffSummary } from "@/services/stagingService";
import { stagingService } from "@/services/stagingService";

interface StagingApprovalState {
  records: StagingRecord[];
  diff: DiffSummary | null;
  isLoading: boolean;
  approveAll: () => Promise<void>;
  rejectAll: () => Promise<void>;
  patchNode: (nodeId: string, state: "APPROVED" | "REJECTED") => Promise<void>;
  refresh: () => void;
}

export function useStagingApproval(sessionId: string | null): StagingApprovalState {
  const [records, setRecords] = useState<StagingRecord[]>([]);
  const [diff, setDiff] = useState<DiffSummary | null>(null);
  const [isLoading, setIsLoading] = useState(!sessionId ? false : true);

  const load = useCallback(async () => {
    if (!sessionId) { setIsLoading(false); return; }
    setIsLoading(true);
    try {
      const [recs, d] = await Promise.all([
        stagingService.getDraft(sessionId),
        stagingService.getDiff(sessionId),
      ]);
      setRecords(recs);
      setDiff(d);
    } finally {
      setIsLoading(false);
    }
  }, [sessionId]);

  useEffect(() => { void load(); }, [load]);

  const approveAll = useCallback(async () => {
    if (!sessionId) return;
    await stagingService.approveAll(sessionId);
    await load();
  }, [sessionId, load]);

  const rejectAll = useCallback(async () => {
    if (!sessionId) return;
    await stagingService.rejectAll(sessionId);
    await load();
  }, [sessionId, load]);

  const patchNode = useCallback(async (nodeId: string, state: "APPROVED" | "REJECTED") => {
    if (!sessionId) return;
    await stagingService.patchNode(sessionId, nodeId, state);
    await load();
  }, [sessionId, load]);

  return { records, diff, isLoading, approveAll, rejectAll, patchNode, refresh: load };
}
