'use client';

import { useRouter, useSearchParams } from 'next/navigation';
import * as React from 'react';

import { cn } from '@/lib/utils';

/**
 * Tabs whose selection lives in the URL.
 *
 * Built here rather than pulled in as another Radix primitive, because the
 * behaviour that matters is the URL binding: a colleague can send "look at the
 * bank tab of this employee" as a link, the back button steps between tabs, and
 * a refresh stays where you were. A local-state tab strip does none of that.
 *
 * Keyboard behaviour follows the WAI-ARIA tabs pattern -- arrow keys move
 * between tabs, Home and End jump to the ends -- so the strip is operable
 * without a mouse.
 */

export interface TabDefinition {
  /** Stable key. Appears in the URL, so keep it short and readable. */
  id: string;
  label: string;
  /** Rendered after the label, e.g. a count. */
  badge?: React.ReactNode;
}

interface TabsProps {
  tabs: TabDefinition[];
  /** Query parameter the selection is stored in. */
  paramName?: string;
  /** Used when the URL names no tab, or names one that does not exist. */
  defaultTabId?: string;
  /** Labels the tab strip for assistive technology. */
  label: string;
  children: (activeTabId: string) => React.ReactNode;
  className?: string;
}

export function Tabs({
  tabs,
  paramName = 'tab',
  defaultTabId,
  label,
  children,
  className,
}: TabsProps): React.JSX.Element {
  const router = useRouter();
  const searchParams = useSearchParams();
  const listRef = React.useRef<HTMLDivElement>(null);

  const fallback = defaultTabId ?? tabs[0]?.id ?? '';
  const requested = searchParams.get(paramName);
  // An unknown tab in the URL falls back rather than rendering nothing, so a
  // stale or hand-edited link still lands somewhere useful.
  const activeId = tabs.some((tab) => tab.id === requested) ? (requested as string) : fallback;

  const select = React.useCallback(
    (id: string) => {
      const params = new URLSearchParams(searchParams.toString());
      params.set(paramName, id);
      // `scroll: false` keeps the page where it is; switching tab is not
      // navigating to a new page as far as the reader is concerned.
      router.replace(`?${params.toString()}`, { scroll: false });
    },
    [paramName, router, searchParams],
  );

  const onKeyDown = (event: React.KeyboardEvent<HTMLDivElement>) => {
    const currentIndex = tabs.findIndex((tab) => tab.id === activeId);
    if (currentIndex === -1) return;

    const moves: Record<string, number> = {
      ArrowRight: currentIndex + 1,
      ArrowLeft: currentIndex - 1,
      Home: 0,
      End: tabs.length - 1,
    };
    const nextIndex = moves[event.key];
    if (nextIndex === undefined) return;

    event.preventDefault();
    const wrapped = (nextIndex + tabs.length) % tabs.length;
    const next = tabs[wrapped];
    if (!next) return;

    select(next.id);
    listRef.current?.querySelector<HTMLButtonElement>(`[data-tab-id="${next.id}"]`)?.focus();
  };

  return (
    <div className={cn('space-y-6', className)}>
      <div
        ref={listRef}
        role="tablist"
        aria-label={label}
        onKeyDown={onKeyDown}
        // Scrolls rather than wrapping: eight tabs on a phone would otherwise
        // become three rows and push the content off the screen.
        className="border-border -mx-1 flex gap-1 overflow-x-auto border-b px-1"
      >
        {tabs.map((tab) => {
          const isActive = tab.id === activeId;

          return (
            <button
              key={tab.id}
              type="button"
              role="tab"
              id={`tab-${tab.id}`}
              data-tab-id={tab.id}
              aria-selected={isActive}
              aria-controls={`panel-${tab.id}`}
              // Only the active tab is in the tab order; the arrow keys move
              // between them from there. This is the roving-tabindex pattern.
              tabIndex={isActive ? 0 : -1}
              onClick={() => {
                select(tab.id);
              }}
              className={cn(
                'flex shrink-0 items-center gap-2 border-b-2 px-3 py-2 text-sm font-medium whitespace-nowrap transition-colors',
                'focus-visible:ring-ring rounded-t-sm focus-visible:ring-2 focus-visible:outline-none',
                isActive
                  ? 'border-primary text-primary'
                  : 'text-muted-foreground hover:text-foreground border-transparent',
              )}
            >
              {tab.label}
              {tab.badge !== undefined ? (
                <span className="bg-muted text-muted-foreground rounded-full px-1.5 py-0.5 text-xs">
                  {tab.badge}
                </span>
              ) : null}
            </button>
          );
        })}
      </div>

      <div role="tabpanel" id={`panel-${activeId}`} aria-labelledby={`tab-${activeId}`} tabIndex={0}>
        {children(activeId)}
      </div>
    </div>
  );
}
