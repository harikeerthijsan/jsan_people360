'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import * as React from 'react';
import { useForm } from 'react-hook-form';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { FormLayout, FormSection } from '@/components/common/form-layout';
import { Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { TextField } from '@/components/common/text-field';
import { TextareaField } from '@/components/common/textarea-field';
import { ApprovalStatusBadge } from '@/components/common/workforce-widgets';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Form } from '@/components/ui/form';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { EmployeePicker } from '@/features/workforce/components/employee-picker';
import {
  useDecideRegularization,
  useRegularizations,
  useRequestRegularization,
} from '@/features/workforce/hooks';
import { regularizationSchema, type RegularizationFormValues } from '@/features/workforce/schema';
import {
  APPROVAL_STATUSES,
  APPROVAL_STATUS_LABELS,
  type ApprovalStatus,
  type Regularization,
} from '@/features/workforce/types';

const stamp = (value: string | null): string =>
  value ? new Date(value).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—';

/**
 * Attendance corrections.
 *
 * Approving is what amends the attendance record -- the request itself changes
 * nothing. That is why the queue matters: an unanswered correction leaves the
 * original, wrong day standing in every report.
 */
export function RegularizationsPage(): React.JSX.Element {
  const [employeeId, setEmployeeId] = React.useState('');
  const [status, setStatus] = React.useState<ApprovalStatus | 'all'>('pending');
  const [isRequesting, setIsRequesting] = React.useState(false);
  const [deciding, setDeciding] = React.useState<Regularization | null>(null);
  const [decisionNotes, setDecisionNotes] = React.useState('');

  const query = useRegularizations({
    ...(employeeId ? { employee_id: employeeId } : {}),
    ...(status === 'all' ? {} : { status }),
  });

  const request = useRequestRegularization(employeeId);
  const decide = useDecideRegularization();

  const form = useForm<RegularizationFormValues>({
    resolver: zodResolver(regularizationSchema),
    defaultValues: {
      attendance_date: '',
      requested_check_in_at: '',
      requested_check_out_at: '',
      reason: '',
      supporting_document_id: '',
    },
  });

  const submit = form.handleSubmit((values) => {
    request.mutate(
      {
        ...values,
        // An empty datetime-local field means "leave this one alone", which the
        // API reads as null rather than as an empty string.
        requested_check_in_at: values.requested_check_in_at || null,
        requested_check_out_at: values.requested_check_out_at || null,
      },
      {
        onSuccess: () => {
          setIsRequesting(false);
          form.reset();
        },
      },
    );
  });

  const record = (approved: boolean): void => {
    if (!deciding) return;
    decide.mutate(
      { id: deciding.id, approved, notes: decisionNotes.trim() || null },
      {
        onSuccess: () => {
          setDeciding(null);
          setDecisionNotes('');
        },
      },
    );
  };

  const columns: DataTableColumn<Regularization>[] = [
    {
      id: 'date',
      header: 'Day',
      cell: (row) => <span className="tabular-nums">{row.attendance_date}</span>,
    },
    { id: 'in', header: 'Requested in', cell: (row) => stamp(row.requested_check_in_at) },
    { id: 'out', header: 'Requested out', cell: (row) => stamp(row.requested_check_out_at) },
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
            variant="outline"
          >
            Decide
          </Button>
        ) : (
          <span className="text-muted-foreground text-sm">{stamp(row.decided_at)}</span>
        ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Attendance corrections"
        description="A forgotten tap is corrected here. Approving is what amends the day."
        actions={
          <Button
            disabled={!employeeId}
            onClick={() => {
              setIsRequesting(true);
            }}
          >
            Request a correction
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Filters</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <EmployeePicker onChange={setEmployeeId} value={employeeId} />
          <div className="space-y-1.5">
            <Label htmlFor="regularization-status">Status</Label>
            <Select
              onValueChange={(value) => {
                setStatus(value as ApprovalStatus | 'all');
              }}
              value={status}
            >
              <SelectTrigger id="regularization-status">
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
        </CardContent>
      </Card>

      <DataTable
        columns={columns}
        emptyDescription="Nothing is waiting on a decision."
        emptyTitle="No corrections"
        error={query.error}
        getRowId={(row) => row.id}
        isLoading={query.isPending}
        onRetry={() => void query.refetch()}
        rows={query.data?.items ?? []}
      />

      <Modal
        onOpenChange={setIsRequesting}
        open={isRequesting}
        size="lg"
        title="Request an attendance correction"
        description="Give the time that should have been recorded, and why."
        footer={
          <>
            <Button
              onClick={() => {
                setIsRequesting(false);
              }}
              variant="outline"
            >
              Cancel
            </Button>
            <Button isLoading={request.isPending} onClick={() => void submit()}>
              Send request
            </Button>
          </>
        }
      >
        <Form {...form}>
          <FormLayout onSubmit={(event) => void submit(event)}>
            <FormSection
              description="Fill in whichever tap was missed. Both is fine."
              title="The day being corrected"
            >
              <TextField control={form.control} label="Date" name="attendance_date" required type="date" />
              <div />
              <TextField
                control={form.control}
                label="Check-in should have been"
                name="requested_check_in_at"
                type="datetime-local"
              />
              <TextField
                control={form.control}
                label="Check-out should have been"
                name="requested_check_out_at"
                type="datetime-local"
              />
              <TextareaField
                className="sm:col-span-2"
                control={form.control}
                description="What happened. The approver sees this and nothing else."
                label="Reason"
                name="reason"
                required
                rows={3}
              />
            </FormSection>
          </FormLayout>
        </Form>
      </Modal>

      <Modal
        onOpenChange={(open) => {
          if (!open) {
            setDeciding(null);
            setDecisionNotes('');
          }
        }}
        open={deciding !== null}
        title="Decide this correction"
        description={deciding ? `${deciding.attendance_date} — ${deciding.reason}` : undefined}
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
        <div className="space-y-1.5">
          <Label htmlFor="decision-notes">Notes</Label>
          <Textarea
            id="decision-notes"
            onChange={(event) => {
              setDecisionNotes(event.target.value);
            }}
            placeholder="Optional. Kept with the decision."
            rows={3}
            value={decisionNotes}
          />
        </div>
      </Modal>
    </div>
  );
}
