import { useEffect, useRef } from "react";

interface LogConsoleProps {
  logs: string[];
  isConnected: boolean;
}

export function LogConsole({ logs, isConnected }: LogConsoleProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs]);

  return (
    <div className="flex flex-col rounded-lg border border-gray-700 bg-gray-950 text-sm">
      <div className="flex items-center justify-between border-b border-gray-700 px-3 py-1.5">
        <span className="font-mono text-xs text-gray-400">Runtime Log</span>
        {!isConnected && (
          <span className="text-xs text-red-400">연결 끊김</span>
        )}
        {isConnected && (
          <span className="inline-block h-2 w-2 animate-pulse rounded-full bg-green-400" />
        )}
      </div>
      <div className="h-48 overflow-y-auto p-3">
        {logs.map((line, i) => (
          <div key={i} className="font-mono text-xs text-gray-300">
            {line}
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
