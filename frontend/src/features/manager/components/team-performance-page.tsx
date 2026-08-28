'use client';

import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { TeamMemberCell } from '@/features/manager/components/widgets';
import { useTeamPerformance } from '@/features/manager/hooks';
import type { TeamPerformance } from '@/features/manager/types';

/**
 * Team Performance.
 *
 * A read of the Performance Management module, not a second one. Every figure
 * here -- the goal count, the weighted progress, the review statuses, the
 * rating of record -- is what that module reports, and nothing on this screen
 * recomputes any of it.
 *
 * Submitting a manager review is that module's own action, which is why there
 * is no form here: a second way to write a review would be a second set of
 * rules about when it may be written.
 */

/** Review state as one word, in the order the stages actually happen. */
function reviewLabel(row: TeamPerformance): { label: string; tone: 'warning' | 'success' | 'outline' } {
  if (row.manager_review_status === 'submitted') return { label: 'Your review is in', tone: 'success' };
  if (row.review_due) return { label: 'Your review is due', tone: 'warning' };
  if (row.self_review_status === 'submitted') return { label: 'Self review in', tone: 'outline' };
  return { label: 'Not started', tone: 'outline' };
}

export function TeamPerformancePage(): React.JSX.Element {
  const performance = useTeamPerformance();
  const rows = performance.data ?? [];

  const cycleName = rows.find((row) => row.cycle_name)?.cycle_name ?? null;
  const due = rows.filter((row) => row.review_due).length;
  const rated = rows.filter((row) => row.current_rating !== null).length;

  const columns: DataTableColumn<TeamPerformance>[] = [
    { id: 'employee', header: 'Employee', cell: (row) => <TeamMemberCell employee={row.employee} /> },
    {
      id: 'goals',
      header: 'Goals',
      align: 'right',
      cell: (row) => (
        <span className="tabular-nums">
          {row.goals_completed}/{row.goals}
        </span>
      ),
    },
    {
      id: 'progress',
      header: 'Goal progress',
      cell: (row) => (
        <div className="flex items-center gap-2">
          <div className="bg-muted h-2 w-24 rounded-full">
            <div
              className="bg-primary h-full rounded-full"
              style={{ width: `${String(Math.min(row.goal_progress, 100))}%` }}
            />
          </div>
          <span className="text-muted-foreground text-xs tabular-nums">{row.goal_progress}%</span>
        </div>
      ),
    },
    {
      id: 'review',
      header: 'Review status',
      cell: (row) => {
        const state = reviewLabel(row);
        return <Badge variant={state.tone}>{state.label}</Badge>;
      },
    },
    {
      id: 'rating',
      header: 'Current rating',
      align: 'right',
      cell: (row) =>
        row.current_rating === null ? (
          <span className="text-muted-foreground">—</span>
        ) : (
          <span className="font-medium tabular-nums">{row.current_rating}/5</span>
        ),
    },
    {
      id: 'pending',
      header: 'Pending review',
      cell: (row) =>
        row.review_due ? (
          <Badge variant="warning">Yours</Badge>
        ) : row.self_review_status === 'submitted' ? (
          <span className="text-muted-foreground">—</span>
        ) : (
          <Badge variant="outline">Theirs</Badge>
        ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Team Performance"
        description={cycleName ?? 'No active performance cycle. Figures appear once one is opened.'}
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard hint="direct reports" label="Team members" value={rows.length} />
        <StatCard hint="waiting on you" label="Reviews due" value={due} />
        <StatCard hint="rating recorded" label="Rated" value={rated} />
      </div>

      <DataTable
        caption="Team performance"
        columns={columns}
        emptyDescription="Nobody reports to you yet, or no cycle has been opened."
        emptyTitle="No performance data"
        error={performance.error}
        getRowId={(row) => row.employee.id}
        isLoading={performance.isPending}
        onRetry={() => void performance.refetch()}
        rows={rows}
      />
    </div>
  );
}
