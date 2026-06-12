import { useState, useCallback } from "react";
import type { ToastKind } from "@/types/graphPipeline";
import { graphPipelineApi } from "@/lib/graphPipelineApi";

interface UseGraphDocumentInputOptions {
  onToast: (kind: ToastKind, message: string) => void;
  onPipelineStarted: (sessionId: string, docId: string) => void;
  onDuplicateDetected: (url: string) => void;
}

export function useGraphDocumentInput({
  onToast,
  onPipelineStarted,
  onDuplicateDetected,
}: UseGraphDocumentInputOptions) {
  const [url, setUrl]           = useState("");
  const [isChecking, setIsChecking] = useState(false);

  const isValidUrl = useCallback((value: string): boolean => {
    try {
      new URL(value);
      return true;
    } catch {
      return false;
    }
  }, []);

  const handleSubmit = useCallback(async () => {
    if (!isValidUrl(url)) {
      onToast("error", "유효한 URL을 입력해 주세요.");
      return;
    }

    setIsChecking(true);
    try {
      const dupRes = await graphPipelineApi.checkDuplicate(url);
      if (dupRes.data.is_duplicate) {
        onDuplicateDetected(url);
        return;
      }

      const docId = dupRes.data.doc_id ?? url;
      const trigRes = await graphPipelineApi.triggerPipeline(docId);
      onToast("info", "파이프라인을 시작합니다...");
      onPipelineStarted(trigRes.data.session_id, docId);
    } catch {
      onToast("error", "파이프라인 시작에 실패했습니다.");
    } finally {
      setIsChecking(false);
    }
  }, [url, isValidUrl, onToast, onPipelineStarted, onDuplicateDetected]);

  return { url, setUrl, isChecking, handleSubmit };
}
