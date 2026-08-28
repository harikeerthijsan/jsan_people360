'use client';

import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { ApprovalStatusBadge } from '@/components/common/workforce-widgets';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { useDecideLeave, useLeaveRequests, useLeaveTypes } from '@/features/workforce/hooks';
import {
  APPROVAL_STATUSES,
  APPROVAL_STATUS_LABELS,
  LEAVE_DAY_PART_LABELS,
  type ApprovalStatus,
  type LeaveRequest,
} from '@/features/workforce/types';

/**
 * The leave approval queue.
 *
 * Defaults to pending because that is the only state anyone can act on, and a
 * queue that opens showing last year's approved leave hides the work.
 */
export function LeaveApprovalsPage(): React.JSX.Element {
  const [status, setStatus] = React.useState<ApprovalStatus | 'all'>('pending');
  const [leaveTypeId, setLeaveTypeId] = React.useState('all');
  const [fromDate, setFromDate] = React.useState('');
  const [deciding, setDeciding] = React.useState<LeaveRequest | null>(null);
  const [notes, setNotes] = React.useState('');

  const leaveTypes = useLeaveTypes();
  const query = useLeaveRequests({
    ...(status === 'all' ? {} : { status }),
    ...(leaveTypeId === 'all' ? {} : { leave_type_id: leaveTypeId }),
    ...(fromDate ? { from_date: fromDate } : {}),
  });
  const decide = useDecideLeave();

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

  const columns: DataTableColumn<LeaveRequest>[] = [
    { id: 'type', header: 'Type', cell: (row) => row.leave_type?.name ?? '—' },
    {
      id: 'dates',
      header: 'Dates',
      cell: (row) => (
        <span className="tabular-nums">
          {row.from_date === row.to_date ? row.from_date : `${row.from_date} → ${row.to_date}`}
        </span>
      ),
    },
    {
      id: 'days',
      header: 'Working days',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{row.days}</span>,
    },
    { id: 'part', header: 'Part', cell: (row) => LEAVE_DAY_PART_LABELS[row.day_part] },
    { id: 'reason', header: 'Reason', cell: (row) => <span className="line-clamp-2">{row.reason}</span> },
    { id: 'status', header: 'Status', cell: (row) => <ApprovalStatusBadge status={row.status} /> },
    {
      id: 'action',
      header: '',
      align: 'right',
      cell: (row) =>
        row.status === 'pending' ? (
          <Button
            onClick={() => {
              setDeciding(row);
            }}
            size="sm"
          >
            Decide
          </Button>
        ) : null,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Leave approvals"
        description="Approving spends the days that were held when the request was made; rejecting releases them."
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Filters</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-3">
          <div className="space-y-1.5">
            <Label htmlFor="leave-status">Status</Label>
            <Select
              onValueChange={(value) => {
                setStatus(value as ApprovalStatus | 'all');
              }}
              value={status}
            >
              <SelectTrigger id="leave-status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {APPROVAL_STATUSES.map((value) => (
                  <SelectItem key={value} value={value}>
                    {APPROVAL_STATUS_LABELS[value]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="leave-type">Leave type</Label>
            <Select disabled={leaveTypes.isPending} onValueChange={setLeaveTypeId} value={leaveTypeId}>
              <SelectTrigger id="leave-type">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All types</SelectItem>
                {(leaveTypes.data ?? []).map((type) => (
                  <SelectItem key={type.id} value={type.id}>
                    {type.name}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="leave-from">Starting on or after</Label>
            <Input
              id="leave-from"
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
        emptyDescription="Nothing is waiting on a decision."
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
        title="Decide this request"
        description={
          deciding
            ? `${deciding.leave_type?.name ?? 'Leave'} · ${deciding.days} working day(s) · ${deciding.from_date} to ${deciding.to_date}`
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
              Reject
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
            <div className="bg-muted/50 rounded-md p-3 text-sm">
              <p className="font-medium">Reason given</p>
              <p className="text-muted-foreground">{deciding.reason}</p>
            </div>
          ) : null}
          <div className="space-y-1.5">
            <Label htmlFor="leave-decision-notes">Notes</Label>
            <Textarea
              id="leave-decision-notes"
              onChange={(event) => {
                setNotes(event.target.value);
              }}
              placeholder="Optional. The employee sees this with the decision."
              rows={3}
              value={notes}
            />
          </div>
        </div>
      </Modal>
    </div>
  );
}
