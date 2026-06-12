import { useEffect, useRef } from "react";

interface GraphLogConsoleProps {
  logs: string[];
  isConnected: boolean;
}

export function GraphLogConsole({ logs, isConnected }: GraphLogConsoleProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div className="flex flex-col rounded-lg border border-gray-700 bg-gray-950 text-sm">
      <div className="flex items-center justify-between border-b border-gray-700 px-3 py-1.5">
        <span className="font-mono text-xs text-gray-400">Runtime Log</span>
        {isConnected ? (
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-green-400" />
        ) : (
          <span className="text-xs text-red-400">연결 끊김</span>
        )}
      </div>
      <div className="h-48 overflow-y-auto p-3 space-y-0.5">
        {logs.map((line, i) => (
          <div key={i} className="font-mono text-xs text-gray-300 leading-relaxed">
            {line}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
