import { useEffect, useState } from "react";
import { getDocRelated, getDocStats } from "../lib/kmsApi";
import type { DocStats, RelatedDoc } from "../types/kms";

function StatCard({ label, value, sub, color = "#6366f1" }: { label: string; value: string | number; sub?: string; color?: string }) {
  return (
    <div style={{
      flex: 1, minWidth: 0, padding: "12px 14px", borderRadius: 10,
      background: "#fff", border: "1px solid #e2e8f0",
    }}>
      <div style={{ fontSize: 10, color: "#64748b", fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontSize: 22, fontWeight: 700, color, lineHeight: 1 }}>{value}</div>
      {sub && <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 3 }}>{sub}</div>}
    </div>
  );
}

function SkeletonCard() {
  return (
    <div style={{
      flex: 1, height: 72, borderRadius: 10,
      background: "#f1f5f9", animation: "pulse 1.5s ease-in-out infinite",
    }} />
  );
}

interface Props {
  docId: string;
}

export function DocUsagePanel({ docId }: Props) {
  const [stats, setStats]         = useState<DocStats | null>(null);
  const [related, setRelated]     = useState<RelatedDoc[]>([]);
  const [loading, setLoading]     = useState(true);
  const [error, setError]         = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    setStats(null);
    setRelated([]);

    Promise.all([getDocStats(docId), getDocRelated(docId)])
      .then(([s, r]) => {
        if (cancelled) return;
        setStats(s);
        setRelated(r);
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : "조회 실패");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });

    return () => { cancelled = true; };
  }, [docId]);

  if (error) {
    return (
      <div style={{ padding: "10px 14px", borderRadius: 8, background: "#fef2f2", border: "1px solid #fca5a5", color: "#dc2626", fontSize: 13 }}>
        ⚠️ {error}
      </div>
    );
  }

  const lastUsed = stats?.last_used_at
    ? new Date(stats.last_used_at).toLocaleDateString("ko-KR")
    : "없음";

  return (
    <div>
      {/* Stats cards */}
      <div style={{ display: "flex", gap: 8, marginBottom: 20 }}>
        {loading ? (
          <>
            <SkeletonCard />
            <SkeletonCard />
            <SkeletonCard />
          </>
        ) : (
          <>
            <StatCard
              label="RAG 참조 횟수"
              value={stats?.rag_reference_count ?? 0}
              sub="팀 전체"
              color="#6366f1"
            />
            <StatCard
              label="최근 활용일"
              value={lastUsed}
              color="#3b82f6"
            />
            <StatCard
              label="최근 7일 활용"
              value={stats?.recent_search_reflected ? "✓" : "—"}
              color={stats?.recent_search_reflected ? "#22c55e" : "#94a3b8"}
            />
          </>
        )}
      </div>

      {/* Related docs */}
      <div style={{ fontSize: 12, fontWeight: 700, color: "#475569", marginBottom: 10, letterSpacing: "0.02em" }}>
        연관 문서
      </div>

      {loading ? (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {[0, 1, 2].map(i => (
            <div key={i} style={{ height: 54, borderRadius: 8, background: "#f1f5f9" }} />
          ))}
        </div>
      ) : related.length === 0 ? (
        <div style={{ padding: "20px 0", textAlign: "center", color: "#94a3b8", fontSize: 13 }}>
          연관 문서가 없습니다.
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {related.map((r) => (
            <div key={r.doc_id} style={{
              padding: "10px 12px", borderRadius: 8,
              background: "#f8fafc", border: "1px solid #e2e8f0",
              display: "flex", justifyContent: "space-between", alignItems: "center",
            }}>
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "#1e293b", marginBottom: 2 }}>
                  {r.title ?? r.doc_id.slice(0, 24) + "…"}
                </div>
                {r.category && (
                  <span style={{
                    fontSize: 10, fontWeight: 600, color: "#6366f1",
                    background: "#ede9fe", padding: "1px 6px", borderRadius: 6,
                  }}>{r.category}</span>
                )}
              </div>
              <div style={{ fontSize: 11, color: "#94a3b8", flexShrink: 0, marginLeft: 8 }}>
                공통 {r.shared_count}개
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
