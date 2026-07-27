import { type FC, useActionState, useRef, useEffect } from 'react';
import { useFormStatus } from 'react-dom';

interface QueryInputProps {
  onSubmit: (query: string) => Promise<void>;
}

interface FormState {
  error: string | null;
  submitted: boolean;
}

function SubmitButton() {
  const { pending } = useFormStatus();

  return (
    <button
      type="submit"
      disabled={pending}
      aria-busy={pending}
      className="inline-flex items-center justify-center min-h-[44px] min-w-[44px] px-4 py-2 text-sm font-medium text-white bg-blue-600 rounded-md hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 motion-safe:transition-colors"
    >
      {pending ? (
        <>
          <svg
            className="animate-spin -ml-1 mr-2 h-4 w-4 text-white motion-reduce:hidden"
            aria-hidden="true"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
            />
          </svg>
          <span>Sending...</span>
        </>
      ) : (
        'Send'
      )}
    </button>
  );
}

export const QueryInput: FC<QueryInputProps> = ({ onSubmit }) => {
  const inputRef = useRef<HTMLInputElement>(null);

  const [state, submitAction, isPending] = useActionState(
    async (_prev: FormState, formData: FormData): Promise<FormState> => {
      const query = formData.get('query') as string;
      // Whitespace-only input rejection: no request sent, input unchanged
      if (!query.trim()) {
        return { error: null, submitted: false };
      }
      try {
        await onSubmit(query);
        return { error: null, submitted: true };
      } catch {
        return { error: 'Failed to send question. Please try again.', submitted: false };
      }
    },
    { error: null, submitted: false },
  );

  useEffect(() => {
    if (!isPending && state.submitted && inputRef.current) {
      inputRef.current.value = '';
      inputRef.current.focus();
    }
  }, [isPending, state.submitted]);

  return (
    <form action={submitAction} className="flex gap-2">
      <div className="flex-1 relative">
        <label htmlFor="query-input" className="sr-only">
          Ask a question
        </label>
        <input
          ref={inputRef}
          id="query-input"
          name="query"
          type="text"
          maxLength={1000}
          placeholder="Ask a question about your documents..."
          disabled={isPending}
          aria-describedby={state.error ? 'query-error' : undefined}
          aria-invalid={state.error ? true : undefined}
          className="w-full min-h-[44px] px-4 py-2 text-sm text-gray-900 bg-white border border-gray-300 rounded-md placeholder:text-gray-400 disabled:opacity-50 focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"
        />
        {state.error && (
          <p id="query-error" className="absolute -bottom-5 left-0 text-xs text-red-600" role="alert">
            {state.error}
          </p>
        )}
      </div>
      <SubmitButton />
    </form>
  );
};
