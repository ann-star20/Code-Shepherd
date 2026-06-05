import { useRef, useState } from "react";
import type { PreScanResult } from "@/services/pipelineService";
import { pipelineService } from "@/services/pipelineService";
import type { FormMetadata } from "@/components/molecules/MetadataForm";

export interface DocumentInputState {
  urls: string[];
  prescanResult: PreScanResult | null;
  confidence: number;
  isScanning: boolean;
  isPending: boolean;
  addUrl: (url: string) => void;
  removeUrl: (idx: number) => void;
  confirmMetadata: (meta: FormMetadata) => void;
  triggerPipeline: () => Promise<string>;
}

export function useDocumentInput(): DocumentInputState {
  const [urls, setUrls] = useState<string[]>([]);
  const urlCountRef = useRef(0);
  const [prescanResult, setPrescanResult] = useState<PreScanResult | null>(null);
  const [confidence, setConfidence] = useState(0);
  const [isScanning, setIsScanning] = useState(false);
  const [isPending, setIsPending] = useState(false);
  const [metadata, setMetadata] = useState<FormMetadata>({});

  function addUrl(url: string) {
    if (urlCountRef.current >= 5) return;
    urlCountRef.current += 1;
    setUrls((prev) => [...prev, url]);

    setIsScanning(true);
    pipelineService
      .prescan(url)
      .then((result) => {
        setPrescanResult(result);
        setConfidence(result.confidence);
        setIsPending(result.confidence < 0.5);
      })
      .finally(() => setIsScanning(false));
  }

  function removeUrl(idx: number) {
    urlCountRef.current -= 1;
    setUrls((prev) => prev.filter((_, i) => i !== idx));
  }

  function confirmMetadata(meta: FormMetadata) {
    setMetadata(meta);
    setIsPending(false);
  }

  async function triggerPipeline(): Promise<string> {
    const { session_id } = await pipelineService.trigger({
      urls,
      metadata,
    });
    return session_id;
  }

  return { urls, prescanResult, confidence, isScanning, isPending, addUrl, removeUrl, confirmMetadata, triggerPipeline };
}
