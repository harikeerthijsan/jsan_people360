import * as React from 'react';

import { cn } from '@/lib/utils';

/**
 * A vertical timeline of dated events.
 *
 * Generic on purpose: the Employee module renders employment history through
 * it, and audit history, onboarding checklists and approval chains all have the
 * same shape. It knows about a rail, a marker and an ordered list -- nothing
 * about employees.
 */

export interface TimelineItem {
  /** Stable key, also used as the React key. */
  id: string;
  /** Short label for the kind of event. Rendered as the heading. */
  title: React.ReactNode;
  /** When it happened, already formatted. */
  timestamp: React.ReactNode;
  /** The body of the entry. */
  description?: React.ReactNode;
  /** Supporting detail rendered below the description in muted text. */
  meta?: React.ReactNode;
  /** Drawn inside the marker. Falls back to a plain dot. */
  icon?: React.ReactNode;
  /**
   * Emphasises the marker. Use for the entries a reader scans for -- a
   * promotion among a run of detail edits.
   */
  highlighted?: boolean;
}

interface TimelineProps {
  items: TimelineItem[];
  className?: string;
}

export function Timeline({ items, className }: TimelineProps): React.JSX.Element {
  return (
    // A real ordered list: the sequence is the content, and a stack of divs
    // would leave a screen reader with no way to convey it.
    <ol className={cn('relative space-y-6', className)}>
      {items.map((item, index) => {
        const isLast = index === items.length - 1;

        return (
          <li key={item.id} className="relative flex gap-4">
            <div className="flex flex-col items-center">
              <span
                className={cn(
                  'flex size-8 shrink-0 items-center justify-center rounded-full border-2',
                  item.highlighted === true
                    ? 'border-primary bg-primary-subtle text-primary'
                    : 'border-border bg-background text-muted-foreground',
                )}
                aria-hidden="true"
              >
                {item.icon ?? <span className="size-2 rounded-full bg-current" />}
              </span>

              {/* The rail stops at the last marker rather than trailing into
                  nothing, which would read as "more below". */}
              {!isLast ? <span className="bg-border mt-1 w-px flex-1" aria-hidden="true" /> : null}
            </div>

            <div className="min-w-0 flex-1 pb-1">
              <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
                <p className="font-medium">{item.title}</p>
                <p className="text-muted-foreground text-xs">{item.timestamp}</p>
              </div>

              {item.description !== undefined ? (
                <p className="text-muted-foreground mt-1 text-sm break-words">{item.description}</p>
              ) : null}

              {item.meta !== undefined ? (
                <div className="text-muted-foreground mt-2 text-xs">{item.meta}</div>
              ) : null}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
