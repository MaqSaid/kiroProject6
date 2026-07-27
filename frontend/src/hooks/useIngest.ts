import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api-client';

export function useIngest() {
  const queryClient = useQueryClient();

  return useMutation<{ document_id: string; chunks_produced: number }, Error, File>({
    mutationFn: (file: File) => apiClient.ingest(file),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ['documents'] });
    },
  });
}
