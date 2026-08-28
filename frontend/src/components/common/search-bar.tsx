'use client';

import { Search, X } from 'lucide-react';
import * as React from 'react';

import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

interface SearchBarProps {
  /** Committed value, owned by the parent (usually mirrored into the URL). */
  value: string;
  /** Called after the debounce interval, not on every keystroke. */
  onChange: (value: string) => void;
  placeholder?: string;
  /** Milliseconds to wait before reporting a change. */
  debounceMs?: number;
  label?: string;
  className?: string;
  disabled?: boolean;
}

/**
 * Debounced search input.
 *
 * The input is locally controlled so typing stays responsive, and the committed
 * value is reported only after the user pauses. Without the debounce, every
 * keystroke would fire a request and the results would flicker between stale
 * responses arriving out of order.
 */
export function SearchBar({
  value,
  onChange,
  placeholder = 'Search…',
  debounceMs = 300,
  label = 'Search',
  className,
  disabled = false,
}: SearchBarProps): React.JSX.Element {
  const [draft, setDraft] = React.useState(value);
  const onChangeRef = React.useRef(onChange);

  // Keep the latest callback without making it a dependency of the timer.
  React.useEffect(() => {
    onChangeRef.current = onChange;
  }, [onChange]);

  // Re-sync when the parent changes the value externally (a cleared filter,
  // a back-navigation restoring query state).
  React.useEffect(() => {
    setDraft(value);
  }, [value]);

  React.useEffect(() => {
    if (draft === value) return undefined;

    const timer = setTimeout(() => {
      onChangeRef.current(draft);
    }, debounceMs);

    return () => {
      clearTimeout(timer);
    };
  }, [draft, value, debounceMs]);

  const clear = React.useCallback(() => {
    setDraft('');
    onChangeRef.current('');
  }, []);

  return (
    <div className={cn('relative w-full sm:max-w-xs', className)}>
      <Search
        className="text-muted-foreground pointer-events-none absolute top-1/2 left-3 size-4 -translate-y-1/2"
        aria-hidden="true"
      />
      <Input
        type="search"
        value={draft}
        onChange={(event) => {
          setDraft(event.target.value);
        }}
        onKeyDown={(event) => {
          if (event.key === 'Escape') clear();
        }}
        placeholder={placeholder}
        aria-label={label}
        disabled={disabled}
        // `pr-9` leaves room for the clear button; the native search cancel
        // control is hidden so there is only one way to clear.
        className="pr-9 pl-9 [&::-webkit-search-cancel-button]:appearance-none"
      />
      {draft ? (
        <button
          type="button"
          onClick={clear}
          aria-label="Clear search"
          className="text-muted-foreground hover:text-foreground focus-visible:ring-ring absolute top-1/2 right-2 flex size-6 -translate-y-1/2 items-center justify-center rounded-sm transition-colors focus-visible:ring-2 focus-visible:outline-none"
        >
          <X className="size-3.5" aria-hidden="true" />
        </button>
      ) : null}
    </div>
  );
}
