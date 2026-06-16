import { request } from './client';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  warnings?: string[];
}

export interface ChatResponse {
  reply: string;
  safety_warning: string | null;
  model_used: string;
  reasoning_trace?: { step: string; result: string }[];
}

export async function sendMessage(
  message: string,
  history?: ChatMessage[],
): Promise<ChatResponse> {
  return request<ChatResponse>('/api/chat', {
    method: 'POST',
    body: JSON.stringify({
      message,
      history: (history ?? []).map((m) => ({ role: m.role, content: m.content })),
    }),
  });
}

export async function* sendMessageStream(
  message: string,
  history?: ChatMessage[],
): AsyncGenerator<string> {
  const token = localStorage.getItem('token');
  const resp = await fetch('/api/chat/stream', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({
      message,
      history: (history ?? []).map((m) => ({ role: m.role, content: m.content })),
    }),
  });

  if (!resp.ok) throw new Error(`Stream failed: ${resp.status}`);
  const reader = resp.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    const lines = buffer.split('\n');
    buffer = lines.pop() ?? '';

    for (const line of lines) {
      if (!line.startsWith('data: ')) continue;
      try {
        const data = JSON.parse(line.slice(6));
        if (data.content) yield data.content as string;
      } catch {
        void 0;
      }
    }
  }
}

export async function getChatHistory(): Promise<ChatMessage[]> {
  try {
    return await request<ChatMessage[]>('/api/chat/history');
  } catch {
    return [];
  }
}
