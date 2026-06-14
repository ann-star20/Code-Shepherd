import { useCallback, useEffect, useRef, useState } from "react";
import { getDocumentStatus } from "../lib/kmsApi";
import type { StatusResponse } from "../types/kms";

export const TERMINAL_STATUSES = new Set([
  "stored",
  "stored_partial",
  "failed",
  "rejected",
  "reprocess_failed",
]);

const POLL_INTERVAL_INITIAL_MS = 2_000;  // 첫 번째 폴링은 2초
const POLL_INTERVAL_MAX_MS     = 15_000; // 최대 15초 (지수 백오프 상한)
const POLL_INTERVAL_HITL_MS    = 10_000; // hitl_pending은 사람이 승인할 때까지 변하지 않으므로 10초
const MAX_POLL_MS              = 10 * 60 * 1000; // 10분

export function useUploadStatus(docId: string | null, pollKey: number = 0) {
  const [status, setStatus] = useState<StatusResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const stop = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
  }, []);

  useEffect(() => {
    if (!docId) return;

    setStatus(null);
    setError(null);

    let cancelled = false;
    let consecutiveErrors = 0;
    let pollCount = 0;
    const startedAt = Date.now();

    const nextInterval = () => {
      // 2s → 4s → 8s → 15s (상한) 지수 백오프
      const ms = Math.min(POLL_INTERVAL_INITIAL_MS * 2 ** pollCount, POLL_INTERVAL_MAX_MS);
      pollCount++;
      return ms;
    };

    const poll = async () => {
      if (Date.now() - startedAt >= MAX_POLL_MS) {
        setError("처리 시간 초과 (10분). 나중에 다시 확인하세요.");
        return;
      }

      try {
        const result = await getDocumentStatus(docId);
        if (cancelled) return;
        consecutiveErrors = 0;
        setStatus(result);

        if (!TERMINAL_STATUSES.has(result.status)) {
          const interval = result.status === "hitl_pending"
            ? POLL_INTERVAL_HITL_MS
            : nextInterval();
          timerRef.current = setTimeout(poll, interval);
        }
      } catch (e) {
        if (!cancelled) {
          consecutiveErrors++;
          if (consecutiveErrors >= 3) {
            setError(e instanceof Error ? e.message : "상태 조회 실패");
          } else {
            timerRef.current = setTimeout(poll, nextInterval());
          }
        }
      }
    };

    poll();

    return () => {
      cancelled = true;
      stop();
    };
  }, [docId, pollKey, stop]);

  return { status, error, stop };
}
