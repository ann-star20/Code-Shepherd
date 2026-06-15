import { useState, useCallback } from "react";
import type { ToastItem, ToastKind } from "@/types/graphPipeline";

export function useGraphToast() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const addToast = useCallback((kind: ToastKind, message: string) => {
    const id = `t-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setToasts((prev) => [...prev, { id, kind, message }]);
    setTimeout(
      () => setToasts((prev) => prev.filter((t) => t.id !== id)),
      4000
    );
  }, []);

  const dismiss = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  return { toasts, addToast, dismiss };
}
