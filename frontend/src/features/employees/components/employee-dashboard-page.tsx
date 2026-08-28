'use client';

import { CalendarPlus, Clock, LogOut, Users } from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';

import { ErrorState } from '@/components/common/error-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCardSkeleton } from '@/components/common/loading-state';
import { StatCard } from '@/components/common/stat-card';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useEmployeeDashboard } from '@/features/employees/hooks/use-employees';
import type { CountByLabel } from '@/features/employees/types/employee.types';
import { cn } from '@/lib/utils';

/**
 * A horizontal bar breakdown.
 *
 * Bars rather than a pie or a chart library: the question these answer is
 * "which is biggest, and by how much", which a length answers directly and a
 * chart dependency would not answer any better.
 */
function Breakdown({
  title,
  items,
  emptyMessage,
}: {
  title: string;
  items: CountByLabel[];
  emptyMessage: string;
}): React.JSX.Element {
  const largest = items.reduce((max, item) => Math.max(max, item.count), 0);

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm">{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-muted-foreground text-sm">{emptyMessage}</p>
        ) : (
          <dl className="space-y-3">
            {items.map((item) => (
              <div key={item.label} className="space-y-1">
                <div className="flex items-baseline justify-between gap-3 text-sm">
                  <dt className="truncate">{item.label}</dt>
                  <dd className="text-muted-foreground tabular-nums">{item.count}</dd>
                </div>
                <div className="bg-muted h-1.5 overflow-hidden rounded-full" aria-hidden="true">
                  <div
                    className="bg-primary h-full rounded-full"
                    style={{ width: `${String(largest === 0 ? 0 : (item.count / largest) * 100)}%` }}
                  />
                </div>
              </div>
            ))}
          </dl>
        )}
      </CardContent>
    </Card>
  );
}

export function EmployeeDashboardPage(): React.JSX.Element {
  const stats = useEmployeeDashboard();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Employee dashboard"
        description="Headcount and composition across the organization."
        actions={
          <Button asChild variant="outline">
            <Link href="/employees">View directory</Link>
          </Button>
        }
      />

      {stats.error ? (
        <ErrorState
          error={stats.error}
          onRetry={() => {
            void stats.refetch();
          }}
        />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {stats.isPending ? (
              Array.from({ length: 4 }, (_, index) => <StatCardSkeleton key={index} />)
            ) : (
              <>
                <StatCard
                  label="Employed"
                  value={stats.data.employed}
                  hint={`${String(stats.data.total_employees)} records in total`}
                  icon={Users}
                />
                <StatCard
                  label="On probation"
                  value={stats.data.on_probation}
                  hint="Awaiting confirmation"
                  icon={Clock}
                />
                <StatCard
                  label="On notice"
                  value={stats.data.on_notice}
                  hint="Serving notice period"
                  icon={LogOut}
                />
                <StatCard
                  label="Joining this month"
                  value={stats.data.joining_this_month}
                  hint="By joining date"
                  icon={CalendarPlus}
                />
              </>
            )}
          </div>

          <div className={cn('grid gap-6', 'lg:grid-cols-3')}>
            {stats.isPending ? null : (
              <>
                <Breakdown
                  title="By status"
                  items={stats.data.by_status}
                  emptyMessage="No employees recorded yet."
                />
                <Breakdown
                  title="By business unit"
                  items={stats.data.by_business_unit}
                  emptyMessage="No employees have a business unit yet."
                />
                <Breakdown
                  title="By work mode"
                  items={stats.data.by_work_mode}
                  emptyMessage="No work mode recorded yet."
                />
              </>
            )}
          </div>

          {!stats.isPending && stats.data.archived > 0 ? (
            <p className="text-muted-foreground text-sm">
              {stats.data.archived} archived {stats.data.archived === 1 ? 'record is' : 'records are'}{' '}
              excluded from these figures.{' '}
              <Link href="/employees?view=archived" className="text-primary hover:underline">
                View the archive
              </Link>
            </p>
          ) : null}
        </>
      )}
    </div>
  );
}
