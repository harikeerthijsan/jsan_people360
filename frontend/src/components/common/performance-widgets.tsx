'use client';

import { Award, Lightbulb, Star, Trophy, Users } from 'lucide-react';
import * as React from 'react';

import { Badge } from '@/components/ui/badge';
import { Card, CardContent } from '@/components/ui/card';
import {
  GOAL_PRIORITY_LABELS,
  GOAL_STATUS_LABELS,
  MAX_RATING,
  MIN_RATING,
  RATING_LABELS,
  RECOGNITION_LABELS,
  type GoalPriority,
  type GoalStatus,
  type RecognitionType,
} from '@/features/performance/types';
import { cn } from '@/lib/utils';

/**
 * The performance module's shared pieces.
 *
 * Grouped in one file because they are small and always used together: a goal
 * card contains a progress bar and two badges, a review row contains a rating
 * control. Splitting them across six files would mean six imports on every
 * screen and no clearer boundary.
 */

type BadgeVariant = React.ComponentProps<typeof Badge>['variant'];

const GOAL_STATUS_VARIANT: Record<GoalStatus, BadgeVariant> = {
  not_started: 'secondary',
  in_progress: 'default',
  completed: 'success',
  blocked: 'destructive',
  cancelled: 'outline',
};

const PRIORITY_VARIANT: Record<GoalPriority, BadgeVariant> = {
  low: 'outline',
  medium: 'secondary',
  high: 'warning',
  critical: 'destructive',
};

export function GoalStatusBadge({
  status,
  className,
}: {
  status: GoalStatus;
  className?: string;
}): React.JSX.Element {
  return (
    <Badge variant={GOAL_STATUS_VARIANT[status]} className={className}>
      {GOAL_STATUS_LABELS[status]}
    </Badge>
  );
}

export function PriorityBadge({
  priority,
  className,
}: {
  priority: GoalPriority;
  className?: string;
}): React.JSX.Element {
  return (
    <Badge variant={PRIORITY_VARIANT[priority]} className={className}>
      {GOAL_PRIORITY_LABELS[priority]}
    </Badge>
  );
}

// ---------------------------------------------------------------------------
interface ProgressBarProps {
  value: number;
  /** Shown above the bar; omit for a bare bar inside a dense row. */
  label?: string;
  className?: string;
}

/**
 * A percentage as a bar.
 *
 * Carries the ARIA progressbar role and its value, so the figure is announced
 * rather than being conveyed by width alone.
 */
export function ProgressBar({ value, label, className }: ProgressBarProps): React.JSX.Element {
  const clamped = Math.max(0, Math.min(100, Math.round(value)));
  const tone =
    clamped >= 100 ? 'bg-success' : clamped >= 50 ? 'bg-primary' : clamped > 0 ? 'bg-warning' : 'bg-muted';

  return (
    <div className={cn('space-y-1', className)}>
      {label ? (
        <div className="flex items-center justify-between text-xs">
          <span className="text-muted-foreground">{label}</span>
          <span className="font-medium tabular-nums">{clamped}%</span>
        </div>
      ) : null}
      <div
        className="bg-muted h-2 overflow-hidden rounded-full"
        role="progressbar"
        aria-valuenow={clamped}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-label={label ?? 'Completion'}
      >
        <div
          className={cn('h-full rounded-full transition-[width] duration-300', tone)}
          style={{ width: `${String(clamped)}%` }}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
interface RatingProps {
  value: number | null;
  onChange?: (value: number) => void;
  /** Read-only when omitted, which is how a submitted review renders. */
  disabled?: boolean;
  name?: string;
  className?: string;
}

/**
 * The 1-5 scale, as stars.
 *
 * A radio group rather than buttons: the choice is one-of-five, arrow keys move
 * between options, and each star carries the words for its point on the scale
 * so a screen-reader user hears "Meets expectations", not "3".
 */
export function RatingInput({
  value,
  onChange,
  disabled = false,
  name,
  className,
}: RatingProps): React.JSX.Element {
  const points = Array.from({ length: MAX_RATING - MIN_RATING + 1 }, (_, index) => MIN_RATING + index);
  const groupName = React.useId();

  if (disabled || !onChange) {
    return (
      <span className={cn('inline-flex items-center gap-0.5', className)}>
        {points.map((point) => (
          <Star
            key={point}
            aria-hidden="true"
            className={cn(
              'size-4',
              value !== null && point <= value ? 'fill-warning text-warning' : 'text-muted-foreground/40',
            )}
          />
        ))}
        <span className="sr-only">
          {value === null
            ? 'Not rated'
            : `${String(value)} of ${String(MAX_RATING)} — ${RATING_LABELS[value] ?? ''}`}
        </span>
      </span>
    );
  }

  return (
    <div className={cn('inline-flex items-center gap-0.5', className)} role="radiogroup" aria-label="Rating">
      {points.map((point) => (
        <label key={point} className="cursor-pointer">
          <input
            type="radio"
            name={name ?? groupName}
            value={point}
            checked={value === point}
            onChange={() => onChange(point)}
            className="peer sr-only"
          />
          <Star
            aria-hidden="true"
            className={cn(
              'peer-focus-visible:ring-ring size-5 rounded-sm transition-colors peer-focus-visible:ring-2',
              value !== null && point <= value ? 'fill-warning text-warning' : 'text-muted-foreground/40',
            )}
          />
          <span className="sr-only">{`${String(point)} — ${RATING_LABELS[point] ?? ''}`}</span>
        </label>
      ))}
      {value !== null ? (
        <span className="text-muted-foreground ml-2 text-xs">{RATING_LABELS[value]}</span>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
const RECOGNITION_ICON: Record<RecognitionType, typeof Star> = {
  star_performer: Star,
  innovation: Lightbulb,
  team_player: Users,
  customer_appreciation: Award,
  leadership: Trophy,
};

export function RecognitionBadge({
  type,
  className,
}: {
  type: RecognitionType;
  className?: string;
}): React.JSX.Element {
  const Icon = RECOGNITION_ICON[type];
  return (
    <Badge variant="warning" className={cn('gap-1', className)}>
      <Icon className="size-3" aria-hidden="true" />
      {RECOGNITION_LABELS[type]}
    </Badge>
  );
}

// ---------------------------------------------------------------------------
interface SummaryCardProps {
  label: string;
  value: React.ReactNode;
  hint?: string;
  /** Draws attention without inventing a second accent colour. */
  tone?: 'default' | 'warning' | 'critical';
  className?: string;
}

export function PerformanceSummaryCard({
  label,
  value,
  hint,
  tone = 'default',
  className,
}: SummaryCardProps): React.JSX.Element {
  return (
    <Card className={className}>
      <CardContent className="p-4">
        <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">{label}</p>
        <p
          className={cn(
            'mt-1 text-2xl font-semibold tabular-nums',
            tone === 'warning' && 'text-warning',
            tone === 'critical' && 'text-destructive',
          )}
        >
          {value}
        </p>
        {hint ? <p className="text-muted-foreground mt-1 text-xs">{hint}</p> : null}
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
interface BreakdownProps {
  title: string;
  items: { label: string; count: number }[];
  emptyMessage?: string;
  /** Renders the count as a percentage rather than a tally. */
  asPercentage?: boolean;
  className?: string;
}

/**
 * A labelled horizontal bar chart.
 *
 * Bars are scaled against the largest value rather than a fixed maximum, so a
 * breakdown of small numbers is still readable. Every row shows its figure as
 * text too — a bar alone cannot be read precisely.
 */
export function AnalyticsBreakdown({
  title,
  items,
  emptyMessage = 'Nothing to show yet.',
  asPercentage = false,
  className,
}: BreakdownProps): React.JSX.Element {
  const largest = Math.max(1, ...items.map((item) => item.count));

  return (
    <Card className={className}>
      <CardContent className="space-y-3 p-4">
        <p className="text-sm font-medium">{title}</p>
        {items.length === 0 ? (
          <p className="text-muted-foreground text-sm">{emptyMessage}</p>
        ) : (
          <ul className="space-y-2">
            {items.map((item) => (
              <li key={item.label} className="space-y-1">
                <div className="flex items-center justify-between gap-3 text-sm">
                  <span className="truncate">{item.label}</span>
                  <span className="text-muted-foreground shrink-0 tabular-nums">
                    {item.count}
                    {asPercentage ? '%' : ''}
                  </span>
                </div>
                <div className="bg-muted h-1.5 overflow-hidden rounded-full">
                  <div
                    className="bg-primary h-full rounded-full"
                    style={{
                      width: `${String(asPercentage ? Math.min(100, item.count) : (item.count / largest) * 100)}%`,
                    }}
                  />
                </div>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
