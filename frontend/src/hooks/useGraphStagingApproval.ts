import { useState, useCallback } from "react";
import type { StagingConcept, DiffSummary, ToastKind } from "@/types/graphPipeline";
import { graphPipelineApi } from "@/lib/graphPipelineApi";
import axios from "axios";

interface UseGraphStagingApprovalOptions {
  sessionId: string | null;
  onToast: (kind: ToastKind, message: string) => void;
}

const COMMIT_POLL_INTERVAL_MS = 1000;
const COMMIT_POLL_MAX_ATTEMPTS = 30;

export function useGraphStagingApproval({ sessionId, onToast }: UseGraphStagingApprovalOptions) {
  const [stagingItems, setStagingItems] = useState<StagingConcept[]>([]);
  const [diff, setDiff]                 = useState<DiffSummary | null>(null);
  const [isLoading, setIsLoading]       = useState(false);

  const fetchStaging = useCallback(async () => {
    if (!sessionId) return;
    try {
      const [stagingRes, diffRes] = await Promise.all([
        graphPipelineApi.getStaging(sessionId),
        graphPipelineApi.getDiff(sessionId),
      ]);
      setStagingItems(stagingRes.data.items);
      setDiff(diffRes.data);
    } catch {
      onToast("error", "스테이징 데이터를 불러오지 못했습니다.");
    }
  }, [sessionId, onToast]);

  const approveAll = useCallback(async () => {
    if (!sessionId) return;
    setIsLoading(true);
    const snapshot = stagingItems;
    setStagingItems((prev) =>
      prev.map((item) => ({ ...item, state: "APPROVED" as const }))
    );
    try {
      await graphPipelineApi.approveAll(sessionId);
      onToast("success", "전체 승인 완료");
    } catch (err) {
      setStagingItems(snapshot);
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        onToast("warning", "다른 사용자가 처리 중입니다. 잠시 후 다시 시도해 주세요.");
      } else {
        onToast("error", "승인 처리에 실패했습니다.");
      }
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, stagingItems, onToast]);

  const rejectAll = useCallback(async () => {
    if (!sessionId) return;
    setIsLoading(true);
    const snapshot = stagingItems;
    setStagingItems((prev) =>
      prev.map((item) => ({ ...item, state: "REJECTED" as const }))
    );
    try {
      await graphPipelineApi.rejectAll(sessionId);
      onToast("info", "전체 거부 완료");
    } catch {
      setStagingItems(snapshot);
      onToast("error", "거부 처리에 실패했습니다.");
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, stagingItems, onToast]);

  const approveSingle = useCallback(async (stagingId: number) => {
    const snapshot = stagingItems;
    setStagingItems((prev) =>
      prev.map((item) =>
        item.staging_id === stagingId ? { ...item, state: "APPROVED" as const } : item
      )
    );
    try {
      await graphPipelineApi.approveSingle(stagingId);
      onToast("success", "개념을 승인했습니다.");
    } catch (err) {
      setStagingItems(snapshot);
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        onToast("warning", "다른 사용자가 처리 중입니다. 잠시 후 다시 시도해 주세요.");
      } else {
        onToast("error", "승인 처리에 실패했습니다.");
      }
    }
  }, [stagingItems, onToast]);

  const rejectSingle = useCallback(async (stagingId: number) => {
    const snapshot = stagingItems;
    setStagingItems((prev) =>
      prev.map((item) =>
        item.staging_id === stagingId ? { ...item, state: "REJECTED" as const } : item
      )
    );
    try {
      await graphPipelineApi.rejectSingle(stagingId);
      onToast("info", "개념을 거부했습니다.");
    } catch (err) {
      setStagingItems(snapshot);
      if (axios.isAxiosError(err) && err.response?.status === 409) {
        onToast("warning", "다른 사용자가 처리 중입니다. 잠시 후 다시 시도해 주세요.");
      } else {
        onToast("error", "거부 처리에 실패했습니다.");
      }
    }
  }, [stagingItems, onToast]);

  const commit = useCallback(async (): Promise<boolean> => {
    if (!sessionId) return false;
    setIsLoading(true);
    try {
      await graphPipelineApi.commit(sessionId);
      for (let attempt = 0; attempt < COMMIT_POLL_MAX_ATTEMPTS; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, COMMIT_POLL_INTERVAL_MS));
        const diffRes = await graphPipelineApi.getDiff(sessionId);
        setDiff(diffRes.data);
        if (diffRes.data.approved === 0) {
          onToast("success", "그래프 적재가 완료되었습니다.");
          return true;
        }
      }
      onToast("error", "최종 적재 확인이 시간 초과되었습니다.");
      return false;
    } catch {
      onToast("error", "최종 적재에 실패했습니다.");
      return false;
    } finally {
      setIsLoading(false);
    }
  }, [sessionId, onToast]);

  return {
    stagingItems,
    diff,
    isLoading,
    fetchStaging,
    approveAll,
    rejectAll,
    approveSingle,
    rejectSingle,
    commit,
  };
}
