'use client';

import { useSearchParams } from 'next/navigation';
import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { Pagination } from '@/components/common/pagination';
import { StatCard } from '@/components/common/stat-card';
import { Tabs } from '@/components/common/tabs';
import { ApprovalStatusBadge } from '@/components/common/workforce-widgets';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { DecisionButtons, TeamMemberCell, formatDay } from '@/features/manager/components/widgets';
import { useDecideLeave, useTeamLeave } from '@/features/manager/hooks';
import { LEAVE_DAY_PART_LABELS } from '@/features/workforce/types';
import type { TeamLeaveRow } from '@/features/manager/types';

/**
 * Team Leave.
 *
 * The pending tab is the working screen; the others are the record. The small
 * calendar above them is a month of who is away, which is the question a
 * manager actually has when they open this -- "can I approve this without
 * leaving the week uncovered" is answered by seeing the overlap, not by reading
 * a list of dates.
 */

const STATUS_TABS = [
  { id: 'pending', label: 'Pending' },
  { id: 'approved', label: 'Approved' },
  { id: 'rejected', label: 'Rejected' },
  { id: 'all', label: 'All' },
] as const;

function iso(value: Date): string {
  return value.toISOString().slice(0, 10);
}

/** Approved leave for the next 30 days: the overlap a decision has to consider. */
function UpcomingLeave(): React.JSX.Element {
  const today = new Date();
  const horizon = new Date(today);
  horizon.setDate(today.getDate() + 30);

  const upcoming = useTeamLeave({
    page_size: 50,
    status: 'approved',
    from_date: iso(today),
    to_date: iso(horizon),
  });

  const rows = upcoming.data?.items ?? [];

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-sm font-medium">Who is away in the next 30 days</CardTitle>
        <CardDescription>Approved leave for your direct reports.</CardDescription>
      </CardHeader>
      <CardContent>
        {rows.length === 0 ? (
          <p className="text-muted-foreground text-sm">Nobody on your team is booked off.</p>
        ) : (
          <ul className="grid gap-2 sm:grid-cols-2">
            {rows.map((row) => (
              <li className="flex items-center justify-between gap-3" key={row.request.id}>
                <TeamMemberCell employee={row.employee} />
                <span className="text-muted-foreground shrink-0 text-xs tabular-nums">
                  {formatDay(row.request.from_date)}
                  {row.request.from_date === row.request.to_date
                    ? ''
                    : ` → ${formatDay(row.request.to_date)}`}
                </span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}

export function TeamLeavePage(): React.JSX.Element {
  const searchParams = useSearchParams();
  const [page, setPage] = React.useState(1);

  const requested = searchParams.get('status') ?? 'pending';
  const status = STATUS_TABS.some((tab) => tab.id === requested) ? requested : 'pending';

  React.useEffect(() => {
    setPage(1);
  }, [status]);

  const requests = useTeamLeave({
    page,
    page_size: 20,
    ...(status === 'all' ? {} : { status }),
  });
  const decide = useDecideLeave();

  const columns: DataTableColumn<TeamLeaveRow>[] = [
    { id: 'employee', header: 'Employee', cell: (row) => <TeamMemberCell employee={row.employee} /> },
    { id: 'type', header: 'Type', cell: (row) => row.request.leave_type?.name ?? '—' },
    {
      id: 'dates',
      header: 'Dates',
      cell: (row) => (
        <span className="tabular-nums">
          {row.request.from_date === row.request.to_date
            ? row.request.from_date
            : `${row.request.from_date} → ${row.request.to_date}`}
        </span>
      ),
    },
    {
      id: 'days',
      header: 'Working days',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{row.request.days}</span>,
    },
    { id: 'part', header: 'Part', cell: (row) => LEAVE_DAY_PART_LABELS[row.request.day_part] },
    {
      id: 'reason',
      header: 'Reason',
      cell: (row) => <span className="line-clamp-2">{row.request.reason}</span>,
    },
    { id: 'status', header: 'Status', cell: (row) => <ApprovalStatusBadge status={row.request.status} /> },
    {
      id: 'notes',
      header: 'Comment',
      cell: (row) => <span className="text-muted-foreground">{row.request.decision_notes ?? '—'}</span>,
    },
    {
      id: 'action',
      header: '',
      align: 'right',
      cell: (row) =>
        row.request.status === 'pending' ? (
          <DecisionButtons
            isPending={decide.isPending}
            onDecide={(decision) => {
              decide.mutate({ id: row.request.id, decision });
            }}
            subject="leave request"
          />
        ) : null,
    },
  ];

  const pendingCount = status === 'pending' ? (requests.data?.meta.total_items ?? 0) : undefined;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Team Leave"
        description="Your direct reports' requests. Your own leave goes to your manager, not here."
      />

      {pendingCount !== undefined ? (
        <div className="grid gap-4 sm:grid-cols-3">
          <StatCard hint="awaiting your decision" label="Pending requests" value={pendingCount} />
        </div>
      ) : null}

      <UpcomingLeave />

      <Tabs defaultTabId="pending" label="Leave by status" paramName="status" tabs={[...STATUS_TABS]}>
        {() => (
          <div className="space-y-6">
            <DataTable
              caption="Team leave requests"
              columns={columns}
              emptyDescription="Nothing from your team matches this filter."
              emptyTitle="No leave requests"
              error={requests.error}
              getRowId={(row) => row.request.id}
              isLoading={requests.isPending}
              onRetry={() => void requests.refetch()}
              rows={requests.data?.items ?? []}
            />

            {requests.data ? (
              <Pagination itemLabel="requests" meta={requests.data.meta} onPageChange={setPage} />
            ) : null}
          </div>
        )}
      </Tabs>
    </div>
  );
}
