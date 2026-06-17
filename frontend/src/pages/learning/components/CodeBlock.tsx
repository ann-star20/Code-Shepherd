/**
 * 코드 블록 — 라인 넘버 + 세로 스크롤 (T9, FRONTEND_SPEC Section 5).
 */

interface CodeBlockProps {
  code: string;
}

export default function CodeBlock({ code }: CodeBlockProps) {
  const lines = code.split("\n");
  return (
    <div className="rounded-lg bg-[#1e1e1e] text-gray-100 text-sm p-4 overflow-y-auto max-h-80">
      <table className="w-full border-collapse">
        <tbody>
          {lines.map((line, i) => (
            <tr key={i}>
              <td className="select-none text-right pr-4 text-gray-500 w-8 align-top">{i + 1}</td>
              <td className="whitespace-pre-wrap break-all">{line}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
