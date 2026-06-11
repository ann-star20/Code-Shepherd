/**
 * 코드 블록 — 다크 테마 코드 표시 (T9, FRONTEND_SPEC Section 5).
 */

interface CodeBlockProps {
  code: string;
}

export default function CodeBlock({ code }: CodeBlockProps) {
  return (
    <pre className="rounded-lg bg-[#1e1e1e] text-gray-100 text-sm p-4 overflow-x-auto">
      <code>{code}</code>
    </pre>
  );
}
