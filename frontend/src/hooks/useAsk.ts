import { useMutation } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import type { AgentAskResponse } from '@/types/api';

export function useAsk() {
  return useMutation<AgentAskResponse, Error, string>({
    mutationFn: (query: string) => apiClient.ask(query),
  });
}
