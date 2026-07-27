import { type FC, useState, useCallback, useOptimistic } from 'react';
import { QueryInput } from '@/components/QueryInput';
import { ConversationHistory } from '@/components/ConversationHistory';
import { ErrorState } from '@/components/ErrorState';
import { useAsk } from '@/hooks/useAsk';
import type { Message, AgentAskResponse } from '@/types/api';

export const ChatPage: FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [highlightedChunk, setHighlightedChunk] = useState<number | undefined>();
  const askMutation = useAsk();

  const [optimisticMessages, addOptimistic] = useOptimistic(
    messages,
    (current: Message[], newMsg: Message) => [...current, newMsg],
  );

  const handleSubmit = useCallback(
    async (query: string) => {
      const userMsg: Message = {
        id: crypto.randomUUID(),
        role: 'user',
        content: query,
      };

      const pendingMsg: Message = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: '',
        pending: true,
      };

      addOptimistic(userMsg);
      addOptimistic(pendingMsg);

      const response: AgentAskResponse = await askMutation.mutateAsync(query);

      setMessages((prev) => [
        ...prev,
        userMsg,
        {
          id: pendingMsg.id,
          role: 'assistant',
          content: response.answer,
          response,
          pending: false,
        },
      ]);
    },
    [askMutation, addOptimistic],
  );

  const handleCitationClick = useCallback((index: number) => {
    setHighlightedChunk(index);
    const element = document.querySelector(`[data-testid="source-chunk-${index}"]`);
    element?.scrollIntoView({ behavior: 'smooth', block: 'center' });
  }, []);

  return (
    <section aria-label="Chat" className="flex flex-col h-full gap-6">
      <ConversationHistory
        messages={optimisticMessages}
        onCitationClick={handleCitationClick}
        highlightedChunk={highlightedChunk}
      />

      {askMutation.isError && (
        <ErrorState
          message={askMutation.error?.message ?? 'Failed to get answer'}
          onRetry={() => void askMutation.reset()}
        />
      )}

      <div className="sticky bottom-0 bg-gray-50 pt-4 pb-2">
        <QueryInput onSubmit={handleSubmit} />
      </div>
    </section>
  );
};
