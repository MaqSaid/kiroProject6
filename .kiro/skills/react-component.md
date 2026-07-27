---
inclusion: manual
---

# Skill: React 19 Component Development

## Purpose
Build accessible, performant React 19 components using TypeScript, TailwindCSS, and modern React patterns (useActionState, use(), useOptimistic, useFormStatus) with full WCAG 2.0 AA compliance and Playwright test coverage.

## Process

1. **Define component interface** — Props type with TypeScript strict mode, including accessibility props
2. **Choose data pattern** — useActionState for form submissions, use() + Suspense for async data
3. **Implement component** — Semantic HTML, ARIA attributes, keyboard handling
4. **Style with TailwindCSS** — Utility classes, responsive design, focus indicators
5. **Write Playwright test** — Interaction test covering keyboard nav and screen reader assertions

## Template

### Form Submission with useActionState

```tsx
"use client";

import { useActionState } from "react";
import { useFormStatus } from "react-dom";

interface FormState {
  error: string | null;
  data: Result | null;
}

export function MyForm({ onSubmit }: { onSubmit: (data: FormData) => Promise<Result> }) {
  const [state, formAction, isPending] = useActionState(
    async (_prev: FormState, formData: FormData): Promise<FormState> => {
      try {
        const result = await onSubmit(formData);
        return { error: null, data: result };
      } catch (err) {
        return { error: (err as Error).message, data: null };
      }
    },
    { error: null, data: null }
  );

  return (
    <form action={formAction} aria-label="Form description">
      <fieldset disabled={isPending}>
        <label htmlFor="input-field">Field Label</label>
        <input
          id="input-field"
          name="field"
          type="text"
          required
          aria-describedby={state.error ? "error-msg" : undefined}
          className="w-full rounded-md border border-gray-300 px-3 py-2
                     focus:outline-none focus:ring-2 focus:ring-blue-500
                     disabled:opacity-50"
        />
        {state.error && (
          <p id="error-msg" role="alert" className="mt-1 text-sm text-red-600">
            {state.error}
          </p>
        )}
        <SubmitButton />
      </fieldset>
    </form>
  );
}

function SubmitButton() {
  const { pending } = useFormStatus();
  return (
    <button
      type="submit"
      disabled={pending}
      className="min-h-[44px] min-w-[44px] rounded-md bg-blue-600 px-4 py-2
                 text-white hover:bg-blue-700
                 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2
                 disabled:opacity-50 disabled:cursor-not-allowed"
    >
      {pending ? "Submitting..." : "Submit"}
    </button>
  );
}
```

### Async Data with use() and Suspense

```tsx
import { Suspense, use } from "react";

interface DataViewProps {
  dataPromise: Promise<Data[]>;
}

export function DataView({ dataPromise }: DataViewProps) {
  return (
    <Suspense fallback={<LoadingSkeleton />}>
      <DataContent dataPromise={dataPromise} />
    </Suspense>
  );
}

function DataContent({ dataPromise }: DataViewProps) {
  const data = use(dataPromise);
  return (
    <section aria-label="Data results">
      <ul role="list" className="divide-y divide-gray-200">
        {data.map((item) => (
          <li key={item.id} className="py-3 px-4">
            <span className="text-gray-900">{item.name}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function LoadingSkeleton() {
  return (
    <div role="status" aria-label="Loading content">
      <div className="animate-pulse space-y-3">
        {[1, 2, 3].map((i) => (
          <div key={i} className="h-10 bg-gray-200 rounded" />
        ))}
      </div>
      <span className="sr-only">Loading...</span>
    </div>
  );
}
```

### Optimistic Updates with useOptimistic

```tsx
import { useOptimistic, useActionState } from "react";

interface Message {
  id: string;
  text: string;
  status: "pending" | "sent" | "error";
}

export function MessageList({ messages }: { messages: Message[] }) {
  const [optimisticMessages, addOptimistic] = useOptimistic(
    messages,
    (state: Message[], newMsg: Message) => [...state, newMsg]
  );

  const [, sendAction] = useActionState(
    async (_prev: null, formData: FormData) => {
      const text = formData.get("text") as string;
      addOptimistic({ id: crypto.randomUUID(), text, status: "pending" });
      await sendMessage(text);
      return null;
    },
    null
  );

  return (
    <div role="log" aria-live="polite" aria-label="Messages">
      {optimisticMessages.map((msg) => (
        <article key={msg.id} className={msg.status === "pending" ? "opacity-60" : ""}
          aria-busy={msg.status === "pending"}>
          {msg.text}
        </article>
      ))}
      <form action={sendAction}>
        <input name="text" aria-label="Message text" />
        <button type="submit">Send</button>
      </form>
    </div>
  );
}
```

## WCAG 2.0 AA Checklist

- [ ] **Semantic HTML** — Use `<main>`, `<nav>`, `<article>`, `<section>`, `<aside>`, `<header>`, `<footer>`
- [ ] **ARIA live regions** — `aria-live="polite"` for async updates, `role="alert"` for errors
- [ ] **Keyboard navigation** — All interactive elements reachable via Tab, activatable via Enter/Space
- [ ] **Focus indicators** — Visible `focus:ring-2 focus:ring-blue-500` on all interactive elements
- [ ] **No keyboard traps** — Escape closes modals, focus returns to trigger
- [ ] **Color contrast** — 4.5:1 for normal text, 3:1 for large text (18px+ or 14px+ bold)
- [ ] **Touch targets** — Minimum 44x44px (`min-h-[44px] min-w-[44px]`)
- [ ] **Error association** — `aria-describedby` linking inputs to error messages
- [ ] **Reduced motion** — `motion-safe:` prefix for animations, respect `prefers-reduced-motion`
- [ ] **Screen reader text** — `sr-only` class for visually hidden but accessible content
- [ ] **Form labels** — Every input has an associated `<label>` or `aria-label`

## TailwindCSS Conventions

```
/* Spacing: consistent scale */
p-2 p-3 p-4       /* padding */
gap-2 gap-3 gap-4 /* flex/grid gaps */
space-y-2 space-y-3 /* vertical stacking */

/* Colors: semantic tokens */
text-gray-900   /* primary text */
text-gray-600   /* secondary text */
text-red-600    /* error text */
bg-blue-600     /* primary action */
bg-gray-100     /* surface background */

/* Focus states: always include */
focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2

/* Responsive: mobile-first */
w-full md:w-1/2 lg:w-1/3

/* Animation: respect motion preference */
motion-safe:animate-pulse
motion-safe:transition-colors motion-safe:duration-200
```

## Playwright Test Template

```typescript
import { test, expect } from "@playwright/test";

test.describe("ComponentName", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/path");
  });

  test("renders with correct ARIA landmarks", async ({ page }) => {
    await expect(page.getByRole("main")).toBeVisible();
    await expect(page.getByRole("form", { name: "Form description" })).toBeVisible();
  });

  test("submits form with keyboard", async ({ page }) => {
    const input = page.getByLabel("Field Label");
    await input.fill("test value");
    await input.press("Enter");
    await expect(page.getByRole("alert")).not.toBeVisible();
  });

  test("displays error with aria-describedby", async ({ page }) => {
    const button = page.getByRole("button", { name: "Submit" });
    await button.click();
    const error = page.getByRole("alert");
    await expect(error).toBeVisible();
  });

  test("respects prefers-reduced-motion", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    // Verify no animations are running
  });
});
```

## Checklist

Before completing a React component:
- [ ] TypeScript strict mode, no `any` types
- [ ] Semantic HTML elements used
- [ ] All interactive elements have visible focus indicators
- [ ] ARIA attributes where native semantics insufficient
- [ ] Keyboard navigation works (Tab, Enter, Space, Escape)
- [ ] Touch targets >= 44x44px
- [ ] Color contrast meets 4.5:1 / 3:1 thresholds
- [ ] Error states associated via aria-describedby
- [ ] Loading states have aria-live or role="status"
- [ ] Playwright test covers keyboard and accessibility
- [ ] TailwindCSS utilities (no inline styles)
- [ ] Responsive layout (mobile-first)
- [ ] Reduced motion respected
