import type { ChatRequest, ChatResponse } from "../types/chat";

const BASE = "/chat";

export async function fetchChat(req: ChatRequest): Promise<ChatResponse> {
  const res = await fetch(BASE, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`Chat API 오류 (${res.status}): ${err}`);
  }
  return res.json() as Promise<ChatResponse>;
}
