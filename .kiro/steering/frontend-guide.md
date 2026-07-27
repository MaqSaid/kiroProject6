---
inclusion: fileMatch
fileMatchPattern: frontend/**
---

# Frontend Guide — React 19 + TailwindCSS + WCAG 2.0 AA

## React 19 Component Patterns

### Form Submission with useActionState

```tsx
import { useActionState } from 'react';

interface ChatFormProps {
  onSubmit: (query: string) => Promise<Response>;
}

function ChatInput({ onSubmit }: ChatFormProps) {
  const [state, submitAction, isPending] = useActionState(
    async (_prev: State, formData: FormData) => {
      const query = formData.get('query') as string;
      if (!query.trim()) return { error: null, data: null };
      const response = await onSubmit(query);
      return { error: null, data: response };
    },
    { error: null, data: null }
  );

  return (
    <form action={submitAction}>
      <input name="query" disabled={isPending} aria-label="Ask a question" />
      <SubmitButton />
    </form>
  );
}
```

### Loading State with useFormStatus

```tsx
import { useFormStatus } from 'react-dom';

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button type="submit" disabled={pending} aria-busy={pending}>
      {pending ? 'Sending...' : 'Send'}
    </button>
  );
}
```

### Optimistic Updates with useOptimistic

```tsx
import { useOptimistic } from 'react';

function ConversationHistory({ messages }: { messages: Message[] }) {
  const [optimisticMessages, addOptimistic] = useOptimistic(
    messages,
    (current, newMsg: Message) => [...current, newMsg]
  );

  return (
    <div role="log" aria-live="polite" aria-label="Conversation history">
      {optimisticMessages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
    </div>
  );
}
```

### Data Fetching with use() and Suspense

```tsx
import { use, Suspense } from 'react';

function DocumentList({ documentsPromise }: { documentsPromise: Promise<Document[]> }) {
  const documents = use(documentsPromise);
  return (
    <ul aria-label="Ingested documents">
      {documents.map((doc) => (
        <li key={doc.id}>{doc.filename}</li>
      ))}
    </ul>
  );
}

// Parent wraps with Suspense
function DocumentView() {
  const docsPromise = fetchDocuments();
  return (
    <Suspense fallback={<DocumentListSkeleton />}>
      <DocumentList documentsPromise={docsPromise} />
    </Suspense>
  );
}
```

### Ref as Prop (No forwardRef)

```tsx
// React 19: ref is just a prop
function ChatInput({ ref, ...props }: { ref?: React.Ref<HTMLInputElement> }) {
  return <input ref={ref} {...props} />;
}
```

## WCAG 2.0 AA Requirements Checklist

### Semantic HTML
- Use `<main>`, `<nav>`, `<article>`, `<section>`, `<aside>` for page structure
- Use `<h1>`-`<h6>` in proper hierarchy (no skipping levels)
- Use `<button>` for actions, `<a>` for navigation
- Use `<ul>`/`<ol>` for lists, `<table>` for tabular data

### ARIA Attributes
- `aria-live="polite"` on chat conversation area for dynamic updates
- `aria-busy="true"` on loading regions
- `aria-describedby` to associate error messages with form controls
- `aria-label` on icon-only buttons and non-labeled inputs
- `aria-expanded` on collapsible panels (source panel)
- `role="log"` on conversation history
- `role="alert"` on error notifications

### Keyboard Navigation
- All interactive elements must be focusable (natural tab order)
- Visible focus indicators using `ring-2 ring-offset-2` Tailwind utilities
- No keyboard traps — Escape closes modals/panels
- Enter/Space activates buttons
- Arrow keys navigate within lists or panels

### Focus Management
- Move focus to new answer messages after response arrives
- Return focus to input after submission completes
- Manage focus on view transitions (Chat ↔ Documents)
- Use `inert` attribute on background content when modals open

### Contrast and Sizing
- Normal text: minimum 4.5:1 contrast ratio
- Large text (18px+ or 14px+ bold): minimum 3:1 contrast ratio
- Touch targets: minimum 44x44px
- Respect `prefers-reduced-motion`: disable transitions/animations

## TailwindCSS Conventions

### Design Tokens for Confidence Colors

```js
// tailwind.config.ts
export default {
  theme: {
    extend: {
      colors: {
        confidence: {
          high: '#16a34a',     // green-600 — score >= 0.7
          medium: '#d97706',   // amber-600 — score >= 0.4
          low: '#dc2626',      // red-600 — score < 0.4
        },
      },
    },
  },
};
```

### Utility Patterns
- Use `sr-only` for screen-reader-only text
- Use `focus-visible:ring-2` for keyboard focus indicators
- Use `motion-safe:transition-all` to respect reduced motion preference
- Use responsive prefixes: `sm:`, `md:`, `lg:` for breakpoints
- Group related styles with `@apply` only in `@layer components`

### Component Class Organization
```
Layout → spacing → sizing → typography → colors → borders → effects → states
```

Example: `flex flex-col gap-4 w-full max-w-2xl text-sm text-gray-900 border rounded-lg shadow-sm hover:shadow-md`

## API Client Pattern

```tsx
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8080';
const API_KEY = import.meta.env.VITE_API_KEY;

async function apiClient<T>(path: string, options: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      'X-API-Key': API_KEY,
      ...options.headers,
    },
  });
  if (!response.ok) {
    const error = await response.json();
    throw new ApiError(error.message, error.error_code, response.status);
  }
  return response.json();
}
```

## Playwright Testing Patterns

```tsx
import { test, expect } from '@playwright/test';

test('submitting a question shows an answer', async ({ page }) => {
  await page.goto('/');
  const input = page.getByRole('textbox', { name: /ask a question/i });
  await input.fill('What are the speed limits under Section 45?');
  await page.getByRole('button', { name: /send/i }).click();

  // Wait for response (30s max as per spec)
  const answer = page.getByRole('article').first();
  await expect(answer).toBeVisible({ timeout: 30_000 });
  await expect(answer).not.toBeEmpty();
});

test('citation markers are clickable', async ({ page }) => {
  // ... submit query and wait for answer
  const citation = page.getByRole('link', { name: /\[1\]/ });
  await citation.click();
  const sourceChunk = page.getByTestId('source-chunk-1');
  await expect(sourceChunk).toBeInViewport();
});
```
