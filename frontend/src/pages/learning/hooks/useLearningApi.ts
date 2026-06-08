/**
 * 학습 카드 생성 흐름 — POST /api/learn 호출 후 scan_id로 GET /api/pr/{scan_id}를 폴링한다
 * (T9, FRONTEND_SPEC Section 2/3: 2초 간격, 이슈 3개의 plan.status가 모두 종료 상태가 되면 중단).
 */

import { useCallback, useRef, useState } from "react";

import { m4Api } from "../lib/m4Api";

const POLL_INTERVAL_MS = 2000;
const TERMINAL_STATUSES = new Set(["completed", "failed"]);

export interface CardHeader {
  keyword: string;
  name_of_function: string;
  sub_category: string;
  language: string;
  framework: string;
  framework_version: string;
  depth: "quick" | "deep";
}

export interface LearningRecommendation {
  title: string;
  description: string;
}

export interface CardContent {
  header: CardHeader;
  before_code: string | null;
  after_code: string;
  explanation: string;
  why_dangerous: string;
  core_summary: string;
  learning_recommendations: LearningRecommendation[];
}

export interface PlanStatus {
  id: string;
  status: "pending" | "running" | "completed" | "failed";
  llm_fallback: boolean;
  error_message: string | null;
  card_content: CardContent | null;
  ragas_reason: string | null;
  attempt_count: number;
}

export interface IssueWithPlan {
  id: string;
  keyword: string;
  severity: string;
  plan: PlanStatus;
}

interface UseLearningApiResult {
  issues: IssueWithPlan[] | null;
  start: () => Promise<void>;
}

function isAllTerminal(issues: IssueWithPlan[]): boolean {
  return issues.every((issue) => TERMINAL_STATUSES.has(issue.plan.status));
}

export function useLearningApi(): UseLearningApiResult {
  const [issues, setIssues] = useState<IssueWithPlan[] | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const fetchStatus = useCallback(async (scanId: string) => {
    const response = await m4Api.get(`/api/pr/${scanId}`);
    const fetchedIssues = response.data.issues as IssueWithPlan[];
    setIssues(fetchedIssues);

    if (!isAllTerminal(fetchedIssues)) {
      timerRef.current = setTimeout(() => {
        void fetchStatus(scanId);
      }, POLL_INTERVAL_MS);
    }
  }, []);

  const start = useCallback(async () => {
    const response = await m4Api.post("/api/learn", {});
    const { scan_id: scanId } = response.data;
    await fetchStatus(scanId);
  }, [fetchStatus]);

  return { issues, start };
}
