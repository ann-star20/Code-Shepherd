/**
 * 학습 페이지 — 진입 시 "학습 시작" 모달을 자동으로 표시한다 (T9, FRONTEND_SPEC Section 1).
 */

import axios from "axios";
import { useState } from "react";

import LearningCard from "./components/LearningCard"; // [REVIEW] Slice 3에서 신규 추가된 import (Slice 2 종료 시점엔 없었음)
import LearningModal from "./components/LearningModal";
import { useLearningApi } from "./hooks/useLearningApi";

type StartError = "not_found" | "other" | null;

export default function LearningPage() {
  const [modalOpen, setModalOpen] = useState(true);
  const [loading, setLoading] = useState(false);
  const [startError, setStartError] = useState<StartError>(null);
  const [dismissed, setDismissed] = useState(false);
  const { issues, start } = useLearningApi();

  const handleCancel = () => {
    setModalOpen(false);
    setDismissed(true);
  }; // [REVIEW] 변경됨 — Slice 2 종료 시점엔 `const { start } = ...`였고 issues는 구독하지 않았음

  const handleConfirm = async () => {
    setModalOpen(false);
    setLoading(true);
    setStartError(null);
    try {
      await start();
    } catch (err) {
      // FRONTEND_SPEC Section 8 — 404(PR 없음)는 안내 화면, 그 외(network/500 등)는 일반 오류 메시지
      setStartError(axios.isAxiosError(err) && err.response?.status === 404 ? "not_found" : "other");
    } finally {
      setLoading(false); // [REVIEW] Slice 3에서 신규 추가 — 카드 도착 후 로딩 문구를 내리기 위함 (Slice 2엔 없었음)
    }
  };

  return (
    <>
      <LearningModal open={modalOpen} onConfirm={handleConfirm} onCancel={handleCancel} />
      {/* [REVIEW] 변경됨 — Slice 2 종료 시점엔 `{loading && <p>...}` 한 줄뿐이었음. issues가 도착하면 로딩 문구를 내리도록 조건 추가 */}
      {loading && !issues && <p>학습 카드를 생성하고 있어요...</p>}
      {dismissed && (
        <div className="flex flex-col items-center justify-center gap-1 p-12 text-center text-notion-text-secondary">
          <p>학습은 준비되셨을 때 시작해도 괜찮아요</p>
          <p>페이지를 새로고침하면 언제든 다시 안내가 떠요</p>
        </div>
      )}
      {startError === "not_found" && (
        <div className="flex flex-col items-center justify-center gap-2 p-12 text-center text-notion-text-secondary">
          <p className="text-lg font-medium text-notion-text">📋 아직 등록된 PR이 없습니다</p>
          <p>
            PR을 제출하면 자동으로 코드 리뷰가 진행되고
            <br />
            맞춤형 학습 카드가 생성됩니다.
          </p>
        </div>
      )}
      {startError === "other" && (
        <div className="flex flex-col items-center justify-center gap-1 p-12 text-center text-notion-text-secondary">
          <p>학습 카드를 불러오는 중 문제가 발생했어요</p>
          <p>잠시 후 다시 시도해주세요</p>
        </div>
      )}
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
