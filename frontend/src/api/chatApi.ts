import { request } from './client';

/** A single reasoning step produced by the safety layers / LLM pipeline. */
export interface ReasoningStep {
  step: string;
  result: string;
}

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  warnings?: string[];
  image?: string;
  /** Structured reasoning trace shown in an expandable panel (spec §8.7). */
  reasoning_trace?: ReasoningStep[];
}

export interface ChatResponse {
  reply: string;
  safety_warning: string | null;
  model_used: string;
  reasoning_trace?: ReasoningStep[];
}

/** One chunk emitted by the SSE stream. Either a content delta, the final
 *  reasoning trace, or both (the backend may attach reasoning_trace to the
 *  terminating `done` event). */
export interface StreamChunk {
  content?: string;
  reasoning_trace?: ReasoningStep[];
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
): AsyncGenerator<StreamChunk> {
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
        const data = JSON.parse(line.slice(6)) as {
          content?: string;
          reasoning_trace?: ReasoningStep[];
          done?: boolean;
        };
        const chunk: StreamChunk = {};
        if (typeof data.content === 'string') chunk.content = data.content;
        if (Array.isArray(data.reasoning_trace)) {
          chunk.reasoning_trace = data.reasoning_trace;
        }
        // Only yield when we actually have something to surface.
        if (chunk.content !== undefined || chunk.reasoning_trace !== undefined) {
          yield chunk;
        }
      } catch {
        void 0;
      }
    }
  }
}

export async function sendMessageWithImage(
  message: string,
  image: File,
): Promise<ChatResponse> {
  const token = localStorage.getItem('token');
  const form = new FormData();
  form.append('message', message);
  form.append('image', image);

  const resp = await fetch('/api/chat/image', {
    method: 'POST',
    headers: token ? { Authorization: `Bearer ${token}` } : {},
    body: form,
  });

  if (!resp.ok) {
    const err = await resp.json().catch(() => ({}));
    throw new Error(err.detail || `请求失败: ${resp.status}`);
  }
  return resp.json();
}

/** Raw conversation row returned by GET /api/chat/history. */
interface ConversationRow {
  id: string;
  title: string | null;
  messages: Array<{ role: string; content: string }>;
  reasoning_trace?: ReasoningStep[];
  model_id: string | null;
}

interface HistoryResponse {
  items: ConversationRow[];
  total: number;
  page: number;
  pageSize: number;
  totalPages: number;
}

/**
 * Load the most recent conversation and flatten it into a flat message list so
 * the chat view can restore the thread on page mount.
 *
 * The backend returns a paginated `{ items, total, ... }` envelope (NOT a bare
 * array). Conversations are ordered by `updated_at DESC`, so `items[0]` is the
 * latest. The conversation-level `reasoning_trace` (if any) is attached to the
 * last assistant message so it can be re-rendered in the expandable panel.
 *
 * Failures degrade silently to an empty list — callers show the welcome state.
 */
export async function getChatHistory(): Promise<ChatMessage[]> {
  try {
    const data = await request<HistoryResponse>('/api/chat/history');
    const latest = data?.items?.[0];
    if (!latest) return [];

    const trace = latest.reasoning_trace?.length ? latest.reasoning_trace : undefined;
    const msgs: ChatMessage[] = (latest.messages ?? []).map((m) => ({
      role: m.role === 'assistant' ? 'assistant' : 'user',
      content: m.content,
    }));

    // Attach the conversation reasoning trace to the last assistant turn so it
    // surfaces in the expandable panel exactly like a fresh reply.
    if (trace) {
      for (let i = msgs.length - 1; i >= 0; i--) {
        const m = msgs[i];
        if (m && m.role === 'assistant') {
          m.reasoning_trace = trace;
          break;
        }
      }
    }
    return msgs;
  } catch {
    return [];
  }
}
