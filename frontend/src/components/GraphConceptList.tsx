import type { Domain, GraphNode } from "@/types/graphPipeline";

interface GraphConceptListProps {
  nodes: GraphNode[];
  selectedDomain: Domain | "all";
  selectedConceptId: string | null;
  onSelect: (id: string) => void;
}

export function GraphConceptList({
  nodes,
  selectedDomain,
  selectedConceptId,
  onSelect,
}: GraphConceptListProps) {
  const concepts = nodes.filter(
    (n) =>
      n.node_type === "Concept" &&
      (selectedDomain === "all" || n.domains?.includes(selectedDomain))
  );

  if (concepts.length === 0) {
    return <p className="px-1 text-xs italic text-gray-400">개념이 없습니다</p>;
  }

  return (
    <ul className="flex flex-col gap-1 overflow-auto">
      {concepts.map((c) => (
        <li key={c.id}>
          <button
            type="button"
            onClick={() => onSelect(c.id)}
            className={`w-full rounded-md px-2 py-1.5 text-left text-sm transition-colors ${
              c.id === selectedConceptId
                ? "bg-blue-50 font-medium text-blue-700"
                : "text-gray-700 hover:bg-gray-50"
            }`}
          >
            {c.name}
          </button>
        </li>
      ))}
    </ul>
  );
}
