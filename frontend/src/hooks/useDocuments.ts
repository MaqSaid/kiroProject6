import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';
import type { DocumentsResponse } from '@/types/api';

export function useDocuments() {
  return useQuery<DocumentsResponse>({
    queryKey: ['documents'],
    queryFn: () => apiClient.getDocuments(),
  });
}
