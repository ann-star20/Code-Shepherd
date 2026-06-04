import { useCallback, useEffect, useRef, useState } from "react";
import { getDocumentStatus } from "../api/kmsApi";
import type { StatusResponse } from "../types/kms";

// 폴링 중단 기준 — 이 상태에 도달하면 더 이상 API를 호출하지 않는다.
// hitl_pending·approved·reprocessing 은 비종료 (HITL 승인 후 파이프라인이 재개되면 자동 감지).
// rejected·reprocess_failed 는 최종 상태 — 추가 진행 없으므로 폴링 중단.
export const TERMINAL_STATUSES = new Set([
  "stored",
  "stored_partial",
  "failed",
  "rejected",
  "reprocess_failed",
]);
const POLL_INTERVAL_MS = 1000;
const MAX_POLL_MS = 10 * 60 * 1000; // 10분

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

    // 새 폴링 사이클 시작 시 이전 상태/오류 초기화
    setStatus(null);
    setError(null);

    let cancelled = false;
    let consecutiveErrors = 0;
    const startedAt = Date.now();

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
          timerRef.current = setTimeout(poll, POLL_INTERVAL_MS);
        }
      } catch (e) {
        if (!cancelled) {
          // 네트워크 오류(ECONNREFUSED 등)는 일시적일 수 있으므로 폴링을 중단하지 않고 재시도.
          // 3번 이상 연속 실패 시에만 에러 상태로 전환한다.
          consecutiveErrors++;
          if (consecutiveErrors >= 3) {
            setError(e instanceof Error ? e.message : "상태 조회 실패");
          } else {
            timerRef.current = setTimeout(poll, POLL_INTERVAL_MS * 2);
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
