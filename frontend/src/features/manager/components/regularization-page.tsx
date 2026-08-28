'use client';

import { useSearchParams } from 'next/navigation';
import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { Pagination } from '@/components/common/pagination';
import { Tabs } from '@/components/common/tabs';
import { ApprovalStatusBadge } from '@/components/common/workforce-widgets';
import { Button } from '@/components/ui/button';
import { DecisionButtons, TeamMemberCell, formatTime } from '@/features/manager/components/widgets';
import { useDecideRegularization, useTeamRegularizations } from '@/features/manager/hooks';
import type { TeamRegularizationRow } from '@/features/manager/types';

/**
 * Attendance regularization.
 *
 * The queue a manager works through, so it opens on the requests that need a
 * decision. Approving is what actually amends the attendance record -- the
 * request on its own changes nothing, which is why the two are separate steps
 * and why this is the only route by which a manager changes a day.
 *
 * A request belonging to another manager's report is not merely hidden: asking
 * for one by id is refused by the API.
 */

const STATUS_TABS = [
  { id: 'pending', label: 'Pending' },
  { id: 'approved', label: 'Approved' },
  { id: 'rejected', label: 'Rejected' },
] as const;

export function RegularizationPage(): React.JSX.Element {
  const searchParams = useSearchParams();
  const [page, setPage] = React.useState(1);

  const requested = searchParams.get('status') ?? 'pending';
  const status = STATUS_TABS.some((tab) => tab.id === requested) ? requested : 'pending';

  React.useEffect(() => {
    setPage(1);
  }, [status]);

  const requests = useTeamRegularizations({ page, page_size: 20, status });
  const decide = useDecideRegularization();

  const columns: DataTableColumn<TeamRegularizationRow>[] = [
    { id: 'employee', header: 'Employee', cell: (row) => <TeamMemberCell employee={row.employee} /> },
    {
      id: 'date',
      header: 'Date',
      cell: (row) => <span className="tabular-nums">{row.request.attendance_date}</span>,
    },
    {
      id: 'requested',
      header: 'Requested times',
      cell: (row) => (
        <span className="tabular-nums">
          {formatTime(row.request.requested_check_in_at)} – {formatTime(row.request.requested_check_out_at)}
        </span>
      ),
    },
    {
      id: 'reason',
      header: 'Reason',
      cell: (row) => <span className="line-clamp-2">{row.request.reason}</span>,
    },
    {
      id: 'attachment',
      header: 'Attachment',
      cell: (row) =>
        row.request.supporting_document_id ? (
          <Button asChild size="sm" variant="ghost">
            <a href={`/documents/${row.request.supporting_document_id}`} rel="noreferrer" target="_blank">
              View
            </a>
          </Button>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
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
            subject="correction"
          />
        ) : null,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Attendance Corrections"
        description="Requests from your direct reports. Approving is what amends the day."
      />

      <Tabs defaultTabId="pending" label="Corrections by status" paramName="status" tabs={[...STATUS_TABS]}>
        {() => (
          <div className="space-y-6">
            <DataTable
              caption="Attendance corrections"
              columns={columns}
              emptyDescription="Nothing from your team matches this filter."
              emptyTitle="No corrections"
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
