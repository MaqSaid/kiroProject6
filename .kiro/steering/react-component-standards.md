# React Component Standards

## Component Structure

```tsx
// frontend/src/components/<ComponentName>.tsx
import { type FC } from 'react';

interface <ComponentName>Props {
  // Required props first, optional after
  requiredProp: string;
  optionalProp?: number;
  onAction?: (value: string) => void;
}

export const <ComponentName>: FC<<ComponentName>Props> = ({
  requiredProp,
  optionalProp = defaultValue,
  onAction,
}) => {
  return (
    <div role="region" aria-label="descriptive label">
      {/* Component content */}
    </div>
  );
};
```

## Accessibility Checklist (WCAG 2.1 AA)

Every component MUST:
- [ ] Use semantic HTML (`<button>`, `<nav>`, `<main>`, not `<div onClick>`)
- [ ] Include ARIA labels on interactive elements without visible text
- [ ] Support keyboard navigation (Tab, Enter, Escape, Arrow keys as appropriate)
- [ ] Have visible focus indicators (outline, ring) — never `outline: none` without replacement
- [ ] Meet contrast ratios: 4.5:1 normal text, 3:1 large text (18px+ or 14px bold)
- [ ] Touch targets minimum 44x44px
- [ ] Respect `prefers-reduced-motion` for animations
- [ ] Associate error messages with form controls via `aria-describedby`
- [ ] Announce dynamic content changes via `aria-live` regions

## Tailwind CSS Patterns

```tsx
// Focus indicators
className="focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2"

// Responsive breakpoints (mobile-first)
className="w-full md:w-1/2 lg:w-1/3"

// Minimum touch target
className="min-h-[44px] min-w-[44px] p-3"

// Reduced motion
className="motion-safe:transition-all motion-safe:duration-200"

// Dark mode support
className="bg-white dark:bg-gray-900 text-gray-900 dark:text-gray-100"
```

## Testing Pattern (Vitest + Testing Library)

```tsx
// frontend/src/components/__tests__/<ComponentName>.test.tsx
import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { <ComponentName> } from '../<ComponentName>';

describe('<ComponentName>', () => {
  it('renders with required props', () => {
    render(<<ComponentName> requiredProp="value" />);
    expect(screen.getByRole('region')).toBeInTheDocument();
  });

  it('is keyboard accessible', () => {
    render(<<ComponentName> requiredProp="value" />);
    const button = screen.getByRole('button');
    button.focus();
    expect(button).toHaveFocus();
    fireEvent.keyDown(button, { key: 'Enter' });
    // Assert action triggered
  });

  it('has no accessibility violations', async () => {
    const { container } = render(<<ComponentName> requiredProp="value" />);
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
```

## API Integration (react-query)

```tsx
import { useQuery, useMutation } from '@tanstack/react-query';

// Query hook
export function useAsk(query: string) {
  return useMutation({
    mutationFn: (params: { query: string; top_k?: number }) =>
      fetch('/v1/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(params),
      }).then(res => res.json()),
  });
}
```

## File Organization

```
frontend/src/
├── components/
│   ├── QueryInput.tsx
│   ├── AnswerDisplay.tsx
│   ├── CitationList.tsx
│   ├── ConfidenceScore.tsx
│   ├── SearchResults.tsx
│   ├── ErrorState.tsx
│   └── __tests__/
├── hooks/
│   ├── useAsk.ts
│   └── useDocuments.ts
├── pages/
│   └── Dashboard.tsx
├── types/
│   └── api.ts
└── App.tsx
```

## Error States

Every component that calls an API must handle:
1. Loading state (skeleton or spinner with `aria-busy="true"`)
2. Error state (with `role="alert"` and retry action)
3. Empty state (meaningful message, not blank)
4. Success state (the normal render)
