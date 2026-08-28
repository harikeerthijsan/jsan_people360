'use client';

import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { TimesheetStatusBadge } from '@/components/common/workforce-widgets';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useDecideTimesheet, useTimesheetDashboard, useTimesheets } from '@/features/workforce/hooks';
import {
  TIMESHEET_STATUSES,
  TIMESHEET_STATUS_LABELS,
  type Timesheet,
  type TimesheetStatus,
} from '@/features/workforce/types';

/**
 * The timesheet approval queue.
 *
 * A rejected week goes back to the employee as `rejected` and stays that way
 * until they save it again -- so the reason for sending it back is still on
 * screen while they correct it.
 */
export function TimesheetApprovalsPage(): React.JSX.Element {
  const [status, setStatus] = React.useState<TimesheetStatus | 'all'>('submitted');
  const [fromDate, setFromDate] = React.useState('');
  const [deciding, setDeciding] = React.useState<Timesheet | null>(null);
  const [notes, setNotes] = React.useState('');

  const summary = useTimesheetDashboard();
  const query = useTimesheets({
    ...(status === 'all' ? {} : { status }),
    ...(fromDate ? { from_date: fromDate } : {}),
  });
  const decide = useDecideTimesheet();

  const record = (approved: boolean): void => {
    if (!deciding) return;
    decide.mutate(
      { id: deciding.id, approved, notes: notes.trim() || null },
      {
        onSuccess: () => {
          setDeciding(null);
          setNotes('');
        },
      },
    );
  };

  const columns: DataTableColumn<Timesheet>[] = [
    { id: 'code', header: 'Timesheet', cell: (row) => row.timesheet_code },
    {
      id: 'week',
      header: 'Week beginning',
      cell: (row) => <span className="tabular-nums">{row.week_start_date}</span>,
    },
    {
      id: 'hours',
      header: 'Hours',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{row.total_hours}</span>,
    },
    {
      id: 'billable',
      header: 'Billable',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{row.billable_hours}</span>,
    },
    {
      id: 'entries',
      header: 'Entries',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{row.entries.length}</span>,
    },
    { id: 'status', header: 'Status', cell: (row) => <TimesheetStatusBadge status={row.status} /> },
    {
      id: 'action',
      header: '',
      align: 'right',
      cell: (row) =>
        row.status === 'submitted' ? (
          <Button
            onClick={() => {
              setDeciding(row);
            }}
            size="sm"
          >
            Review
          </Button>
        ) : null,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Timesheet approvals"
        description="Only a submitted week can be decided; sending one back reopens it for correction."
      />

      {summary.data ? (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Awaiting review" value={summary.data.submitted} />
          <StatCard label="Approved" value={summary.data.approved} />
          <StatCard label="Sent back" value={summary.data.rejected} />
          <StatCard
            label="Not filled in"
            value={summary.data.missing}
            hint="employees with no timesheet this week"
          />
        </div>
      ) : null}

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Filters</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="timesheet-status">Status</Label>
            <Select
              onValueChange={(value) => {
                setStatus(value as TimesheetStatus | 'all');
              }}
              value={status}
            >
              <SelectTrigger id="timesheet-status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {TIMESHEET_STATUSES.map((value) => (
                  <SelectItem key={value} value={value}>
                    {TIMESHEET_STATUS_LABELS[value]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="timesheet-from">Week beginning on or after</Label>
            <Input
              id="timesheet-from"
              onChange={(event) => {
                setFromDate(event.target.value);
              }}
              type="date"
              value={fromDate}
            />
          </div>
        </CardContent>
      </Card>

      <DataTable
        columns={columns}
        emptyDescription="No timesheets are waiting on a decision."
        emptyTitle="Queue is clear"
        error={query.error}
        getRowId={(row) => row.id}
        isLoading={query.isPending}
        onRetry={() => void query.refetch()}
        rows={query.data?.items ?? []}
      />

      <Modal
        onOpenChange={(open) => {
          if (!open) {
            setDeciding(null);
            setNotes('');
          }
        }}
        open={deciding !== null}
        size="lg"
        title="Review this timesheet"
        description={
          deciding
            ? `${deciding.timesheet_code} · week of ${deciding.week_start_date} · ${deciding.total_hours} hours`
            : undefined
        }
        footer={
          <>
            <Button
              isLoading={decide.isPending}
              onClick={() => {
                record(false);
              }}
              variant="destructive"
            >
              Send back
            </Button>
            <Button
              isLoading={decide.isPending}
              onClick={() => {
                record(true);
              }}
            >
              Approve
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          {deciding ? (
            <div className="max-h-64 space-y-1 overflow-y-auto">
              {deciding.entries.map((entry) => (
                <div className="flex justify-between border-b py-1.5 text-sm last:border-0" key={entry.id}>
                  <div>
                    <p className="font-medium">{entry.task}</p>
                    <p className="text-muted-foreground tabular-nums">{entry.work_date}</p>
                  </div>
                  <span className="tabular-nums">
                    {entry.hours}h{entry.billable ? '' : ' · non-billable'}
                  </span>
                </div>
              ))}
            </div>
          ) : null}

          <div className="space-y-1.5">
            <Label htmlFor="timesheet-notes">Notes</Label>
            <Textarea
              id="timesheet-notes"
              onChange={(event) => {
                setNotes(event.target.value);
              }}
              placeholder="Say what needs correcting if you are sending it back."
              rows={3}
              value={notes}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}
