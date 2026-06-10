import { apiClient } from "./api";
import type { ChatRequest, ChatResponse } from "../types/chat";

export async function fetchChat(req: ChatRequest): Promise<ChatResponse> {
  try {
    const { data } = await apiClient.post<ChatResponse>("/chat", req);
    return data;
  } catch (error: unknown) {
    const status = (error as { response?: { status?: number } }).response?.status;
    throw new Error(`Chat API 오류 (${status ?? "unknown"})`);
  }
}
