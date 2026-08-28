'use client';

import { useSearchParams } from 'next/navigation';
import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { Pagination } from '@/components/common/pagination';
import { Tabs } from '@/components/common/tabs';
import { TimesheetStatusBadge } from '@/components/common/workforce-widgets';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { DecisionButtons, TeamMemberCell, formatDay } from '@/features/manager/components/widgets';
import { useDecideTimesheet, useTeamTimesheets } from '@/features/manager/hooks';
import type { TeamTimesheetRow } from '@/features/manager/types';

/**
 * Team Timesheets.
 *
 * Approving a week without looking at it is not approval, so the entries are
 * one click away rather than on another screen: the row opens a panel with the
 * project, date, hours, billable flag and task for every line the week
 * contains.
 *
 * "Request correction" is the reject action. A rejected week is the one state
 * an employee may save over, so returning it is what re-opens it for them --
 * there is no separate "send back" that would mean the same thing differently.
 */

const STATUS_TABS = [
  { id: 'submitted', label: 'Awaiting decision' },
  { id: 'approved', label: 'Approved' },
  { id: 'rejected', label: 'Returned' },
  { id: 'draft', label: 'Draft' },
] as const;

export function TeamTimesheetsPage(): React.JSX.Element {
  const searchParams = useSearchParams();
  const [page, setPage] = React.useState(1);
  const [open, setOpen] = React.useState<TeamTimesheetRow | null>(null);

  const requested = searchParams.get('status') ?? 'submitted';
  const status = STATUS_TABS.some((tab) => tab.id === requested) ? requested : 'submitted';

  React.useEffect(() => {
    setPage(1);
  }, [status]);

  const timesheets = useTeamTimesheets({ page, page_size: 20, status });
  const decide = useDecideTimesheet();

  const columns: DataTableColumn<TeamTimesheetRow>[] = [
    { id: 'employee', header: 'Employee', cell: (row) => <TeamMemberCell employee={row.employee} /> },
    { id: 'code', header: 'Timesheet', cell: (row) => row.timesheet.timesheet_code },
    {
      id: 'week',
      header: 'Week beginning',
      cell: (row) => <span className="tabular-nums">{formatDay(row.timesheet.week_start_date)}</span>,
    },
    {
      id: 'hours',
      header: 'Hours',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{row.timesheet.total_hours}</span>,
    },
    {
      id: 'billable',
      header: 'Billable',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{row.timesheet.billable_hours}</span>,
    },
    {
      id: 'entries',
      header: 'Lines',
      align: 'right',
      cell: (row) => (
        <Button
          onClick={() => {
            setOpen(row);
          }}
          size="sm"
          variant="ghost"
        >
          {row.timesheet.entries.length} entries
        </Button>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => <TimesheetStatusBadge status={row.timesheet.status} />,
    },
    {
      id: 'notes',
      header: 'Comment',
      cell: (row) => <span className="text-muted-foreground">{row.timesheet.decision_notes ?? '—'}</span>,
    },
    {
      id: 'action',
      header: '',
      align: 'right',
      cell: (row) =>
        row.timesheet.status === 'submitted' ? (
          <DecisionButtons
            isPending={decide.isPending}
            onDecide={(decision) => {
              decide.mutate({ id: row.timesheet.id, decision });
            }}
            rejectLabel="Return for correction"
            subject="timesheet"
          />
        ) : null,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Team Timesheets"
        description="Weeks submitted by your direct reports. Returning one re-opens it for editing."
      />

      <Tabs defaultTabId="submitted" label="Timesheets by status" paramName="status" tabs={[...STATUS_TABS]}>
        {() => (
          <div className="space-y-6">
            <DataTable
              caption="Team timesheets"
              columns={columns}
              emptyDescription="Nothing from your team matches this filter."
              emptyTitle="No timesheets"
              error={timesheets.error}
              getRowId={(row) => row.timesheet.id}
              isLoading={timesheets.isPending}
              onRetry={() => void timesheets.refetch()}
              rows={timesheets.data?.items ?? []}
            />

            {timesheets.data ? (
              <Pagination itemLabel="timesheets" meta={timesheets.data.meta} onPageChange={setPage} />
            ) : null}
          </div>
        )}
      </Tabs>

      <Modal
        description={
          open
            ? `${open.employee.full_name} · week beginning ${formatDay(open.timesheet.week_start_date)}`
            : undefined
        }
        onOpenChange={(next) => {
          if (!next) setOpen(null);
        }}
        open={open !== null}
        size="xl"
        title={open ? open.timesheet.timesheet_code : 'Timesheet'}
      >
        {open ? (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead scope="col">Date</TableHead>
                  <TableHead scope="col">Project</TableHead>
                  <TableHead scope="col">Task</TableHead>
                  <TableHead className="text-right" scope="col">
                    Hours
                  </TableHead>
                  <TableHead scope="col">Billable</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {open.timesheet.entries.map((entry) => (
                  <TableRow key={entry.id}>
                    <TableCell className="tabular-nums">{entry.work_date}</TableCell>
                    <TableCell className="font-mono text-xs">{entry.project_id.slice(0, 8)}</TableCell>
                    <TableCell>{entry.task}</TableCell>
                    <TableCell className="text-right tabular-nums">{entry.hours}</TableCell>
                    <TableCell>
                      <Badge variant={entry.billable ? 'success' : 'outline'}>
                        {entry.billable ? 'Billable' : 'Non-billable'}
                      </Badge>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        ) : null}
      </Modal>
    </div>
  );
}
