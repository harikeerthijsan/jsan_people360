import { ArrowDownRight, ArrowUpRight, type LucideIcon } from 'lucide-react';
import * as React from 'react';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface StatCardProps {
  label: string;
  value: string | number;
  /** Short qualifier under the value, e.g. "vs. last month". */
  hint?: string;
  icon?: LucideIcon;
  /** Signed percentage change; the arrow and colour are derived from the sign. */
  trend?: number;
  /** Colour of the icon bubble; blue unless the figure has a natural colour. */
  tone?: StatTone;
  className?: string;
}

export type StatTone = 'blue' | 'green' | 'orange' | 'red' | 'purple';

const TONES: Record<StatTone, { bubble: string; icon: string }> = {
  blue: { bubble: 'bg-primary-subtle', icon: 'text-primary' },
  green: { bubble: 'bg-success-subtle', icon: 'text-success' },
  orange: { bubble: 'bg-warning-subtle', icon: 'text-warning-foreground' },
  red: { bubble: 'bg-destructive-subtle', icon: 'text-destructive' },
  purple: { bubble: 'bg-chart-5/15', icon: 'text-chart-5' },
};

/** A single KPI tile for dashboard summary rows. */
export function StatCard({
  label,
  value,
  hint,
  icon: Icon,
  trend,
  tone = 'blue',
  className,
}: StatCardProps): React.JSX.Element {
  const palette = TONES[tone];
  const hasTrend = typeof trend === 'number' && Number.isFinite(trend);
  const isPositive = hasTrend && trend > 0;
  const TrendIcon = isPositive ? ArrowUpRight : ArrowDownRight;

  return (
    <Card
      className={cn(
        'transition-[box-shadow,transform] duration-200 hover:-translate-y-0.5 hover:shadow-md',
        className,
      )}
    >
      <CardHeader className="flex flex-row items-center justify-between gap-2 pb-2">
        <CardTitle className="text-muted-foreground text-sm font-medium">{label}</CardTitle>
        {Icon ? (
          <span className={cn('flex size-9 items-center justify-center rounded-full', palette.bubble)}>
            <Icon className={cn('size-4', palette.icon)} aria-hidden="true" />
          </span>
        ) : null}
      </CardHeader>

      <CardContent className="space-y-1">
        <p className="text-foreground text-2xl font-semibold tracking-tight">{value}</p>

        <div className="flex items-center gap-1.5 text-xs">
          {hasTrend ? (
            <span
              className={cn(
                'inline-flex items-center gap-0.5 font-medium',
                isPositive ? 'text-success' : 'text-destructive',
              )}
            >
              <TrendIcon className="size-3" aria-hidden="true" />
              {Math.abs(trend).toFixed(1)}%
            </span>
          ) : null}
          {hint ? <span className="text-muted-foreground">{hint}</span> : null}
        </div>
      </CardContent>
    </Card>
  );
}
