import type { AgentAskResponse, DocumentsResponse } from '@/types/api';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8080';
const API_KEY = import.meta.env.VITE_API_KEY ?? '';

class ApiClientError extends Error {
  constructor(
    message: string,
    public errorCode: string,
    public status: number,
  ) {
    super(message);
    this.name = 'ApiClientError';
  }
}

async function request<T>(path: string, options: RequestInit & { timeoutMs?: number } = {}): Promise<T> {
  const { timeoutMs, ...fetchOptions } = options;
  const headers: Record<string, string> = {
    ...(fetchOptions.headers as Record<string, string>),
  };

  if (API_KEY) {
    headers['X-API-Key'] = API_KEY;
  }

  // Only set Content-Type for non-FormData bodies
  if (fetchOptions.body && !(fetchOptions.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const controller = timeoutMs ? new AbortController() : undefined;
  const timeout = timeoutMs && controller
    ? setTimeout(() => controller.abort(), timeoutMs)
    : undefined;

  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      ...fetchOptions,
      headers,
      ...(controller ? { signal: controller.signal } : {}),
    });

    if (!response.ok) {
      let errorBody: { message?: string; error_code?: string } = {};
      try {
        errorBody = await response.json();
      } catch {
        // Response may not be JSON
      }
      throw new ApiClientError(
        errorBody.message ?? `Request failed with status ${response.status}`,
        errorBody.error_code ?? 'UNKNOWN_ERROR',
        response.status,
      );
    }

    return response.json() as Promise<T>;
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiClientError('Request timed out', 'TIMEOUT', 408);
    }
    throw error;
  } finally {
    if (timeout) clearTimeout(timeout);
  }
}

export const apiClient = {
  ask(query: string): Promise<AgentAskResponse> {
    return request<AgentAskResponse>('/v1/agents/ask', {
      method: 'POST',
      body: JSON.stringify({ query }),
      timeoutMs: 30_000,
    });
  },

  ingest(file: File): Promise<{ document_id: string; chunks_produced: number }> {
    const formData = new FormData();
    formData.append('file', file);
    return request('/v1/ingest', {
      method: 'POST',
      body: formData,
      timeoutMs: 60_000,
    });
  },

  getDocuments(): Promise<DocumentsResponse> {
    return request<DocumentsResponse>('/v1/documents');
  },

  health(): Promise<{ status: string; services: Record<string, string> }> {
    return request('/health');
  },
};

export { ApiClientError };
