'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import * as React from 'react';
import { useForm } from 'react-hook-form';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { EmptyState } from '@/components/common/empty-state';
import { FormLayout, FormSection } from '@/components/common/form-layout';
import { LoadingState } from '@/components/common/loading-state';
import { Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { SelectField } from '@/components/common/select-field';
import { TextField } from '@/components/common/text-field';
import { TextareaField } from '@/components/common/textarea-field';
import { ApprovalStatusBadge, LeaveBalanceCard } from '@/components/common/workforce-widgets';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Form } from '@/components/ui/form';
import { EmployeePicker } from '@/features/workforce/components/employee-picker';
import {
  useApplyForLeave,
  useCancelLeave,
  useLeaveBalances,
  useLeaveRequests,
  useLeaveTypes,
} from '@/features/workforce/hooks';
import { leaveApplySchema, type LeaveApplyFormValues } from '@/features/workforce/schema';
import { LEAVE_DAY_PART_LABELS, type LeaveRequest } from '@/features/workforce/types';

/**
 * Applying for leave, and what is left.
 *
 * The balances sit above the form because the number that decides whether an
 * application is worth making is "days remaining", and putting it behind a tab
 * would mean applying first and finding out afterwards.
 */
export function LeavePage(): React.JSX.Element {
  const [employeeId, setEmployeeId] = React.useState('');
  const [isApplying, setIsApplying] = React.useState(false);

  const balances = useLeaveBalances(employeeId || undefined);
  const requests = useLeaveRequests(employeeId ? { employee_id: employeeId } : {});
  const leaveTypes = useLeaveTypes();
  const apply = useApplyForLeave(employeeId);
  const cancel = useCancelLeave();

  const form = useForm<LeaveApplyFormValues>({
    resolver: zodResolver(leaveApplySchema),
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
      id: 'action',
      header: '',
      align: 'right',
      cell: (row) =>
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
        title="Leave"
        description="Counted in working days: a Friday-to-Monday absence costs two days, not four."
        actions={
          <Button
            disabled={!employeeId}
            onClick={() => {
              setIsApplying(true);
            }}
          >
            Apply for leave
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Whose leave</CardTitle>
        </CardHeader>
        <CardContent>
          <EmployeePicker onChange={setEmployeeId} value={employeeId} />
        </CardContent>
      </Card>

      {!employeeId ? (
        <EmptyState
          title="Choose an employee"
          description="Pick someone above to see their balances and requests."
        />
      ) : (
        <>
          <section className="space-y-3">
            <div>
              <h2 className="text-lg font-semibold">Balances</h2>
              <p className="text-muted-foreground text-sm">
                Days held by a pending request are shown separately: they come back if the request is turned
                down.
              </p>
            </div>
            {balances.isPending ? (
              <LoadingState />
            ) : (
              <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
                {(balances.data ?? []).map((balance) => (
                  <LeaveBalanceCard balance={balance} key={balance.id} />
                ))}
              </div>
            )}
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-semibold">Requests</h2>
            <DataTable
              columns={columns}
              emptyDescription="No leave has been applied for."
              emptyTitle="Nothing yet"
              error={requests.error}
              getRowId={(row) => row.id}
              isLoading={requests.isPending}
              onRetry={() => void requests.refetch()}
              rows={requests.data?.items ?? []}
            />
          </section>
        </>
      )}

      <Modal
        onOpenChange={setIsApplying}
        open={isApplying}
        size="lg"
        title="Apply for leave"
        description="Weekends and holidays inside the range are not charged."
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
                options={Object.entries(LEAVE_DAY_PART_LABELS).map(([value, label]) => ({
                  value,
                  label,
                }))}
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
              The balance is held as soon as this is sent, so two overlapping requests cannot both be approved
              against the same entitlement.
            </CardDescription>
          </FormLayout>
        </Form>
      </Modal>
    </div>
  );
}
