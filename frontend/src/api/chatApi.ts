import { request } from './client';

export interface ChatMessage {
  role: 'user' | 'assistant';
  content: string;
  warnings?: string[];
}

export interface ChatResponse {
  reply: string;
  warnings: string[];
}

export async function sendMessage(
  message: string,
  _history: ChatMessage[],
): Promise<ChatResponse> {
  try {
    return await request<ChatResponse>('/api/chat', {
      method: 'POST',
      body: JSON.stringify({ message }),
    });
  } catch {
    // Mock fallback
    return {
      reply: `您好！我是家庭医生AI助手。您询问的是关于"${message}"的问题。\n\n这是一个演示回复。实际使用时将连接到真实的AI服务，为您提供专业的健康建议。`,
      warnings: [],
    };
  }
}

export async function getChatHistory(): Promise<ChatMessage[]> {
  try {
    return await request<ChatMessage[]>('/api/chat/history');
  } catch {
    return [];
  }
}
