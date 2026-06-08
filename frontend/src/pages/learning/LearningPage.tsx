/**
 * 학습 페이지 — 진입 시 "학습 시작" 모달을 자동으로 표시한다 (T9, FRONTEND_SPEC Section 1).
 */

import { useState } from "react";

import LearningCard from "./components/LearningCard"; // [REVIEW] Slice 3에서 신규 추가된 import (Slice 2 종료 시점엔 없었음)
import LearningModal from "./components/LearningModal";
import { useLearningApi } from "./hooks/useLearningApi";

export default function LearningPage() {
  const [modalOpen, setModalOpen] = useState(true);
  const [loading, setLoading] = useState(false);
  const { issues, start } = useLearningApi(); // [REVIEW] 변경됨 — Slice 2 종료 시점엔 `const { start } = ...`였고 issues는 구독하지 않았음

  const handleConfirm = async () => {
    setModalOpen(false);
    setLoading(true);
    await start();
    setLoading(false); // [REVIEW] Slice 3에서 신규 추가 — 카드 도착 후 로딩 문구를 내리기 위함 (Slice 2엔 없었음)
  };

  return (
    <>
      <LearningModal open={modalOpen} onConfirm={handleConfirm} onCancel={() => setModalOpen(false)} />
      {/* [REVIEW] 변경됨 — Slice 2 종료 시점엔 `{loading && <p>...}` 한 줄뿐이었음. issues가 도착하면 로딩 문구를 내리도록 조건 추가 */}
      {loading && !issues && <p>학습 카드를 생성하고 있어요...</p>}
      {/* [REVIEW] 신규 추가 블록 — Slice 3 (Slice 2 종료 시점엔 카드 렌더링 코드가 전혀 없었음) */}
      {issues && (
        <div className="space-y-4 p-6">
          {issues.map((issue) => (
            <LearningCard key={issue.id} issue={issue} />
          ))}
        </div>
      )}
    </>
  );
}
