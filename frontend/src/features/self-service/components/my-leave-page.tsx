'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { useSearchParams } from 'next/navigation';
import * as React from 'react';
import { useForm } from 'react-hook-form';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { FormLayout, FormSection } from '@/components/common/form-layout';
import { LoadingState } from '@/components/common/loading-state';
import { Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { SelectField } from '@/components/common/select-field';
import { Tabs } from '@/components/common/tabs';
import { TextField } from '@/components/common/text-field';
import { TextareaField } from '@/components/common/textarea-field';
import { ApprovalStatusBadge } from '@/components/common/workforce-widgets';
import { Button } from '@/components/ui/button';
import { CardDescription } from '@/components/ui/card';
import { Form } from '@/components/ui/form';
import { LeaveBalanceGrid } from '@/features/self-service/components/leave-balance-grid';
import {
  useApplyForLeave,
  useCancelMyLeave,
  useMyLeave,
  useMyLeaveBalance,
  useMyLeaveTypes,
} from '@/features/self-service/hooks';
import { myLeaveApplySchema, type MyLeaveApplyFormValues } from '@/features/self-service/schema';
import type { LeaveRequest } from '@/features/self-service/types';
import { LEAVE_DAY_PART_LABELS } from '@/features/workforce/types';

/**
 * My Leave.
 *
 * The balances sit above everything else because the figure that decides
 * whether an application is worth making is "days available", and putting it
 * behind a tab means applying first and finding out afterwards.
 *
 * There is no employee picker. There is nothing to pick: the balances, the
 * requests and the application are all the caller's, resolved server-side.
 */

const STATUS_TABS = [
  { id: 'all', label: 'All' },
  { id: 'pending', label: 'Pending' },
  { id: 'approved', label: 'Approved' },
  { id: 'rejected', label: 'Rejected' },
  { id: 'cancelled', label: 'Cancelled' },
] as const;

export function MyLeavePage(): React.JSX.Element {
  const searchParams = useSearchParams();
  const [isApplying, setIsApplying] = React.useState(searchParams.get('apply') === '1');

  // Read from the URL rather than mirrored into state. `Tabs` already writes the
  // selection there, and a second copy would need syncing back -- which means
  // setting state while a child renders, and React rightly complains about that.
  const requested = searchParams.get('status') ?? 'all';
  const status = STATUS_TABS.some((tab) => tab.id === requested) ? requested : 'all';

  const balances = useMyLeaveBalance();
  const requests = useMyLeave(status === 'all' ? {} : { status });
  const leaveTypes = useMyLeaveTypes();
  const apply = useApplyForLeave();
  const cancel = useCancelMyLeave();

  const form = useForm<MyLeaveApplyFormValues>({
    resolver: zodResolver(myLeaveApplySchema),
    defaultValues: {
      leave_type_id: '',
      from_date: '',
      to_date: '',
      day_part: 'full_day',
      reason: '',
      supporting_document_id: '',
    },
  });

  const submit = form.handleSubmit((values) => {
    apply.mutate(values, {
      onSuccess: () => {
        setIsApplying(false);
        form.reset();
      },
    });
  });

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
      id: 'decision',
      header: 'Decision',
      cell: (row) => <span className="text-muted-foreground">{row.decision_notes ?? '—'}</span>,
    },
    {
      id: 'action',
      header: '',
      align: 'right',
      cell: (row) =>
        // Only what the server will accept: a rejected or already-cancelled
        // request has nothing to release, and leave already taken is refused.
        row.status === 'pending' || row.status === 'approved' ? (
          <Button
            isLoading={cancel.isPending}
            onClick={() => {
              cancel.mutate(row.id);
            }}
            size="sm"
            variant="outline"
          >
            Cancel
          </Button>
        ) : null,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Leave"
        description="Counted in working days: weekends and holidays inside a range are not charged."
        actions={
          <Button
            onClick={() => {
              setIsApplying(true);
            }}
          >
            Apply for leave
          </Button>
        }
      />

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">Balance</h2>
        {balances.isPending ? <LoadingState /> : <LeaveBalanceGrid balances={balances.data ?? []} />}
      </section>

      <section className="space-y-3">
        <h2 className="text-lg font-semibold">My requests</h2>
        <Tabs defaultTabId="all" label="Leave requests by status" paramName="status" tabs={[...STATUS_TABS]}>
          {() => (
            <DataTable
              columns={columns}
              emptyDescription="No requests match this filter."
              emptyTitle="Nothing here"
              error={requests.error}
              getRowId={(row) => row.id}
              isLoading={requests.isPending}
              onRetry={() => void requests.refetch()}
              rows={requests.data?.items ?? []}
            />
          )}
        </Tabs>
      </section>

      <Modal
        description="Weekends and holidays inside the range are not charged."
        onOpenChange={setIsApplying}
        open={isApplying}
        size="lg"
        title="Apply for leave"
        footer={
          <>
            <Button
              onClick={() => {
                setIsApplying(false);
              }}
              variant="outline"
            >
              Cancel
            </Button>
            <Button isLoading={apply.isPending} onClick={() => void submit()}>
              Apply
            </Button>
          </>
        }
      >
        <Form {...form}>
          <FormLayout onSubmit={(event) => void submit(event)}>
            <FormSection title="The request">
              <SelectField
                control={form.control}
                isLoading={leaveTypes.isPending}
                label="Leave type"
                name="leave_type_id"
                options={(leaveTypes.data ?? []).map((type) => ({
                  value: type.id,
                  label: type.name,
                  hint: `${type.annual_allocation} days a year${type.is_paid ? '' : ' · unpaid'}`,
                }))}
                required
              />
              <SelectField
                control={form.control}
                description="A half day applies to a single date."
                label="Day part"
                name="day_part"
                options={Object.entries(LEAVE_DAY_PART_LABELS).map(([value, label]) => ({ value, label }))}
                required
              />
              <TextField control={form.control} label="From" name="from_date" required type="date" />
              <TextField control={form.control} label="To" name="to_date" required type="date" />
              <TextareaField
                className="sm:col-span-2"
                control={form.control}
                label="Reason"
                name="reason"
                required
                rows={3}
              />
            </FormSection>
            <CardDescription>
              Your balance is held as soon as this is sent, and released if the request is turned down.
            </CardDescription>
          </FormLayout>
        </Form>
      </Modal>
    </div>
  );
}
