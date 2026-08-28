'use client';

import { ChevronLeft, ChevronRight } from 'lucide-react';
import * as React from 'react';

import { EmptyState } from '@/components/common/empty-state';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import { useTeamCalendar } from '@/features/manager/hooks';
import {
  CALENDAR_KIND_LABELS,
  type CalendarEntryKind,
  type TeamCalendarEntry,
} from '@/features/manager/types';

/**
 * Team Calendar.
 *
 * One month of everything dated that concerns the team, as a wall calendar. The
 * server sends the four kinds -- approved leave, the holidays that apply where
 * the team works, attendance exceptions and joining dates -- already merged into
 * one dated stream, so the grid below only has to bucket them by day.
 *
 * The grid is padded to start on the weekday the 1st actually falls on. Without
 * that padding every month reads as though it began on a Monday.
 */

const KIND_TONE: Record<CalendarEntryKind, string> = {
  leave: 'bg-amber-100 text-amber-900 dark:bg-amber-950/60 dark:text-amber-200',
  holiday: 'bg-primary-subtle text-primary',
  exception: 'bg-destructive/10 text-destructive',
  joining: 'bg-emerald-100 text-emerald-900 dark:bg-emerald-950/60 dark:text-emerald-200',
};

const WEEKDAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const;

function monthLabel(year: number, month: number): string {
  return new Date(year, month - 1, 1).toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
}

export function TeamCalendarPage(): React.JSX.Element {
  const today = React.useMemo(() => new Date(), []);
  const [year, setYear] = React.useState(today.getFullYear());
  const [month, setMonth] = React.useState(today.getMonth() + 1);

  const calendar = useTeamCalendar(year, month);

  const step = (delta: number): void => {
    const next = new Date(year, month - 1 + delta, 1);
    setYear(next.getFullYear());
    setMonth(next.getMonth() + 1);
  };

  const byDay = React.useMemo(() => {
    const grouped = new Map<string, TeamCalendarEntry[]>();
    for (const entry of calendar.data?.entries ?? []) {
      const existing = grouped.get(entry.day);
      if (existing) existing.push(entry);
      else grouped.set(entry.day, [entry]);
    }
    return grouped;
  }, [calendar.data]);

  const daysInMonth = new Date(year, month, 0).getDate();
  // `getDay()` counts Sunday as 0; the grid starts on Monday.
  const leadingBlanks = (new Date(year, month - 1, 1).getDay() + 6) % 7;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Team Calendar"
        description="Leave, holidays, attendance exceptions and joining dates for your direct reports."
        actions={
          <div className="flex items-center gap-2">
            <Button
              aria-label="Previous month"
              onClick={() => {
                step(-1);
              }}
              size="sm"
              variant="outline"
            >
              <ChevronLeft className="size-4" aria-hidden="true" />
            </Button>
            <span className="min-w-40 text-center text-sm font-medium">{monthLabel(year, month)}</span>
            <Button
              aria-label="Next month"
              onClick={() => {
                step(1);
              }}
              size="sm"
              variant="outline"
            >
              <ChevronRight className="size-4" aria-hidden="true" />
            </Button>
          </div>
        }
      />

      {calendar.isPending ? (
        <LoadingState message="Loading the team calendar…" />
      ) : calendar.error ? (
        <ErrorState error={calendar.error} onRetry={() => void calendar.refetch()} />
      ) : (
        <div className="space-y-4">
          <div className="text-muted-foreground grid grid-cols-7 gap-1 text-center text-xs font-medium">
            {WEEKDAYS.map((label) => (
              <span key={label}>{label}</span>
            ))}
          </div>

          <div className="grid grid-cols-7 gap-1">
            {Array.from({ length: leadingBlanks }, (_, index) => (
              <div aria-hidden="true" key={`blank-${String(index)}`} />
            ))}

            {Array.from({ length: daysInMonth }, (_, index) => {
              const day = index + 1;
              const iso = `${String(year)}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
              const entries = byDay.get(iso) ?? [];

              return (
                <div className="min-h-24 rounded-md border p-1.5 text-xs" key={iso}>
                  <div className="font-medium tabular-nums">{day}</div>
                  <ul className="mt-1 space-y-0.5">
                    {entries.slice(0, 3).map((entry, position) => (
                      <li
                        className={cn('truncate rounded px-1 py-0.5', KIND_TONE[entry.kind])}
                        key={`${entry.kind}-${String(position)}`}
                        title={[entry.label, entry.detail].filter(Boolean).join(' · ')}
                      >
                        {entry.label}
                      </li>
                    ))}
                    {entries.length > 3 ? (
                      <li className="text-muted-foreground px-1">+{entries.length - 3} more</li>
                    ) : null}
                  </ul>
                </div>
              );
            })}
          </div>

          <div className="text-muted-foreground flex flex-wrap gap-x-4 gap-y-1 text-xs">
            {(Object.keys(KIND_TONE) as CalendarEntryKind[]).map((kind) => (
              <span className="flex items-center gap-1.5" key={kind}>
                <span className={cn('size-3 rounded-sm', KIND_TONE[kind])} />
                {CALENDAR_KIND_LABELS[kind]}
              </span>
            ))}
          </div>

          {calendar.data.entries.length === 0 ? (
            <EmptyState
              description="No leave, holidays or exceptions fall in this month for your team."
              title="Nothing this month"
            />
          ) : (
            <section className="space-y-2">
              <h2 className="text-sm font-semibold">This month, in order</h2>
              <ul className="space-y-1.5">
                {calendar.data.entries.map((entry, position) => (
                  <li
                    className="flex flex-wrap items-center gap-2 text-sm"
                    key={`${entry.day}-${entry.kind}-${String(position)}`}
                  >
                    <span className="text-muted-foreground w-24 shrink-0 tabular-nums">{entry.day}</span>
                    <Badge variant="outline">{CALENDAR_KIND_LABELS[entry.kind]}</Badge>
                    <span className="min-w-0 truncate">{entry.label}</span>
                    {entry.detail ? (
                      <span className="text-muted-foreground truncate">· {entry.detail}</span>
                    ) : null}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
