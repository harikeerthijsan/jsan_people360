'use client';

import * as React from 'react';

import { AnalyticsBreakdown } from '@/components/common/performance-widgets';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCycles, usePerformanceAnalytics, usePerformanceDashboard } from '@/features/performance/hooks';
import {
  CYCLE_STATUS_LABELS,
  type PerformanceCycle,
  type PerformanceCycleStatus,
} from '@/features/performance/types';

/**
 * The organization-wide Performance screen.
 *
 * The audit found this module in an unusual state: a finished backend, a
 * finished frontend data layer (api, hooks, schema, types, a widget kit) and
 * no screen importing any of it — a "Soon" badge in the sidebar for a module
 * that was one file short of existing. This is that file.
 *
 * A cycle filter narrows every figure at once, because the numbers interlock:
 * a completion percentage from one cycle over a goals count from another is
 * how a dashboard tells a story nobody can act on.
 */

const STATUS_TONE: Record<PerformanceCycleStatus, 'default' | 'secondary' | 'outline'> = {
  draft: 'outline',
  active: 'default',
  closed: 'secondary',
  archived: 'secondary',
};

export function PerformanceOverviewPage(): React.JSX.Element {
  const [cycleId, setCycleId] = React.useState<string | undefined>(undefined);
  const dashboard = usePerformanceDashboard(cycleId);
  const analytics = usePerformanceAnalytics(cycleId);
  const cycles = useCycles({ page: 1, page_size: 50 });

  const cycleRows = cycles.data?.items ?? [];
  const data = dashboard.data;

  const cycleColumns: DataTableColumn<PerformanceCycle>[] = [
    {
      id: 'name',
      header: 'Cycle',
      cell: (row) => (
        <div>
          <p className="font-medium">{row.name}</p>
          <p className="text-muted-foreground text-xs">
            {row.cycle_code} · {row.financial_year}
          </p>
        </div>
      ),
    },
    {
      id: 'window',
      header: 'Period',
      cell: (row) =>
        `${new Date(row.start_date).toLocaleDateString()} — ${new Date(row.end_date).toLocaleDateString()}`,
    },
    {
      id: 'deadlines',
      header: 'Review deadlines',
      cell: (row) => (
        <span className="text-muted-foreground text-xs">
          self {new Date(row.self_review_deadline).toLocaleDateString()} · manager{' '}
          {new Date(row.manager_review_deadline).toLocaleDateString()}
        </span>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => <Badge variant={STATUS_TONE[row.status]}>{CYCLE_STATUS_LABELS[row.status]}</Badge>,
    },
  ];

  if (dashboard.error) {
    return <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} />;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Performance"
        description="Cycles, goals and reviews across the organization."
        actions={
          <select
            aria-label="Cycle"
            className="border-input bg-background h-9 rounded-md border px-3 text-sm"
            value={cycleId ?? ''}
            onChange={(event) => setCycleId(event.target.value || undefined)}
          >
            <option value="">All cycles</option>
            {cycleRows.map((cycle) => (
              <option key={cycle.id} value={cycle.id}>
                {cycle.name}
              </option>
            ))}
          </select>
        }
      />

      {!data ? (
        <LoadingState message="Loading performance figures…" />
      ) : (
        <>
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            <StatCard label="Active cycles" value={data.active_cycles} />
            <StatCard
              label="Goals assigned"
              value={data.goals_assigned}
              hint={`${String(data.goals_completed)} completed`}
            />
            <StatCard label="Goal completion" value={`${String(data.goal_completion_percentage)}%`} />
            <StatCard
              label="Reviews pending"
              value={data.reviews_pending}
              hint={`${String(data.self_reviews_pending)} self · ${String(data.manager_reviews_pending)} manager`}
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <AnalyticsBreakdown title="Goals by status" items={data.by_goal_status} />
            <AnalyticsBreakdown title="Goals by priority" items={data.by_priority} />
          </div>

          <div className="grid gap-6 lg:grid-cols-2">
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Top performers</CardTitle>
              </CardHeader>
              <CardContent>
                {data.top_performers.length === 0 ? (
                  <p className="text-muted-foreground text-sm">No finalised ratings yet.</p>
                ) : (
                  <ul className="space-y-2">
                    {data.top_performers.map((entry) => (
                      <li key={entry.employee.id} className="flex items-center justify-between text-sm">
                        <span>
                          {entry.employee.full_name}{' '}
                          <span className="text-muted-foreground text-xs">
                            {entry.employee.employee_code}
                          </span>
                        </span>
                        <Badge>{entry.rating}/5</Badge>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Needs attention</CardTitle>
              </CardHeader>
              <CardContent>
                {data.low_performance_alerts.length === 0 ? (
                  <p className="text-muted-foreground text-sm">Nobody is flagged.</p>
                ) : (
                  <ul className="space-y-2">
                    {data.low_performance_alerts.map((entry) => (
                      <li key={entry.employee.id} className="flex items-center justify-between text-sm">
                        <span>
                          {entry.employee.full_name}{' '}
                          <span className="text-muted-foreground text-xs">
                            {entry.employee.employee_code}
                          </span>
                        </span>
                        <Badge variant="destructive">{entry.rating}/5</Badge>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>
          </div>

          {analytics.data ? (
            <div className="grid gap-6 lg:grid-cols-2">
              <AnalyticsBreakdown title="Rating distribution" items={analytics.data.rating_distribution} />
              <AnalyticsBreakdown
                title="Business unit performance"
                items={analytics.data.business_unit_performance}
              />
            </div>
          ) : null}

          <div className="space-y-3">
            <h2 className="text-base font-semibold">Cycles</h2>
            <DataTable
              rows={cycleRows}
              columns={cycleColumns}
              getRowId={(row) => row.id}
              isLoading={cycles.isLoading}
              error={cycles.error}
              emptyTitle="No cycles"
              emptyDescription="Create a performance cycle to start assigning goals."
            />
          </div>
        </>
      )}
    </div>
  );
}
