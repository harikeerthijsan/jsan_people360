'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import * as React from 'react';
import { useForm } from 'react-hook-form';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { FormLayout } from '@/components/common/form-layout';
import { Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { SelectField } from '@/components/common/select-field';
import { TextareaField } from '@/components/common/textarea-field';
import { AttendanceStatusBadge, WorkModeBadge, formatMinutes } from '@/components/common/workforce-widgets';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Form } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { EmployeePicker } from '@/features/workforce/components/employee-picker';
import { useAttendance, useCheckIn, useCheckOut } from '@/features/workforce/hooks';
import { checkInSchema, type CheckInFormValues } from '@/features/workforce/schema';
import {
  ATTENDANCE_STATUSES,
  ATTENDANCE_STATUS_LABELS,
  WORK_MODES,
  WORK_MODE_LABELS,
  type AttendanceRecord,
  type AttendanceStatus,
} from '@/features/workforce/types';

const today = (): string => new Date().toISOString().slice(0, 10);
const monthAgo = (): string => {
  const date = new Date();
  date.setDate(date.getDate() - 30);
  return date.toISOString().slice(0, 10);
};

const clock = (value: string | null): string =>
  value ? new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : '—';

/**
 * The attendance register.
 *
 * Check-in and check-out are on the same screen as the register rather than on
 * a separate "mark attendance" page: the person marking a day almost always
 * wants to see whether it is already marked, and splitting them produces the
 * duplicate-entry attempt the API then has to refuse.
 */
export function AttendanceRegister(): React.JSX.Element {
  const [employeeId, setEmployeeId] = React.useState('');
  const [status, setStatus] = React.useState<AttendanceStatus | 'all'>('all');
  const [fromDate, setFromDate] = React.useState(monthAgo);
  const [toDate, setToDate] = React.useState(today);
  const [isCheckingIn, setIsCheckingIn] = React.useState(false);

  const query = useAttendance({
    ...(employeeId ? { employee_id: employeeId } : {}),
    ...(status === 'all' ? {} : { status }),
    from_date: fromDate,
    to_date: toDate,
  });

  const checkIn = useCheckIn(employeeId);
  const checkOut = useCheckOut(employeeId);

  const form = useForm<CheckInFormValues>({
    resolver: zodResolver(checkInSchema),
    defaultValues: { work_mode: 'office', notes: '' },
  });

  const columns: DataTableColumn<AttendanceRecord>[] = [
    {
      id: 'date',
      header: 'Date',
      cell: (row) => <span className="tabular-nums">{row.attendance_date}</span>,
    },
    { id: 'in', header: 'In', align: 'right', cell: (row) => clock(row.check_in_at) },
    { id: 'out', header: 'Out', align: 'right', cell: (row) => clock(row.check_out_at) },
    {
      id: 'worked',
      header: 'Worked',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{formatMinutes(row.worked_minutes)}</span>,
    },
    {
      id: 'late',
      header: 'Late',
      align: 'right',
      cell: (row) =>
        row.late_minutes > 0 ? (
          <span className="text-amber-600 tabular-nums">{formatMinutes(row.late_minutes)}</span>
        ) : (
          '—'
        ),
    },
    {
      id: 'overtime',
      header: 'Overtime',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{formatMinutes(row.overtime_minutes)}</span>,
    },
    { id: 'mode', header: 'Mode', cell: (row) => <WorkModeBadge mode={row.work_mode} /> },
    { id: 'status', header: 'Status', cell: (row) => <AttendanceStatusBadge status={row.status} /> },
  ];

  const submitCheckIn = form.handleSubmit((values) => {
    checkIn.mutate(values, {
      onSuccess: () => {
        setIsCheckingIn(false);
        form.reset();
      },
    });
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Attendance register"
        description="Every day is one record. Marking a day twice is refused, not merged."
        actions={
          <div className="flex gap-2">
            <Button
              disabled={!employeeId}
              onClick={() => {
                setIsCheckingIn(true);
              }}
            >
              Check in
            </Button>
            <Button
              disabled={!employeeId}
              isLoading={checkOut.isPending}
              onClick={() => {
                checkOut.mutate({});
              }}
              variant="outline"
            >
              Check out
            </Button>
          </div>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Filters</CardTitle>
          <CardDescription>Leave the employee unset to see everyone.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <EmployeePicker onChange={setEmployeeId} value={employeeId} />

          <div className="space-y-1.5">
            <Label htmlFor="attendance-status">Status</Label>
            <Select
              onValueChange={(value) => {
                setStatus(value as AttendanceStatus | 'all');
              }}
              value={status}
            >
              <SelectTrigger id="attendance-status">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all">All statuses</SelectItem>
                {ATTENDANCE_STATUSES.map((value) => (
                  <SelectItem key={value} value={value}>
                    {ATTENDANCE_STATUS_LABELS[value]}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="attendance-from">From</Label>
            <Input
              id="attendance-from"
              onChange={(event) => {
                setFromDate(event.target.value);
              }}
              type="date"
              value={fromDate}
            />
          </div>

          <div className="space-y-1.5">
            <Label htmlFor="attendance-to">To</Label>
            <Input
              id="attendance-to"
              onChange={(event) => {
                setToDate(event.target.value);
              }}
              type="date"
              value={toDate}
            />
          </div>
        </CardContent>
      </Card>

      <DataTable
        columns={columns}
        emptyDescription="No attendance was recorded in this period."
        emptyTitle="Nothing to show"
        error={query.error}
        getRowId={(row) => row.id}
        isLoading={query.isPending}
        onRetry={() => void query.refetch()}
        rows={query.data?.items ?? []}
      />

      <Modal
        onOpenChange={setIsCheckingIn}
        open={isCheckingIn}
        title="Check in"
        description="Records the arrival time against the shift in force today."
        footer={
          <>
            <Button
              onClick={() => {
                setIsCheckingIn(false);
              }}
              variant="outline"
            >
              Cancel
            </Button>
            <Button isLoading={checkIn.isPending} onClick={() => void submitCheckIn()}>
              Check in
            </Button>
          </>
        }
      >
        <Form {...form}>
          <FormLayout onSubmit={(event) => void submitCheckIn(event)}>
            <SelectField
              control={form.control}
              label="Work mode"
              name="work_mode"
              options={WORK_MODES.map((value) => ({ value, label: WORK_MODE_LABELS[value] }))}
              required
            />
            <TextareaField
              control={form.control}
              description="Optional. Anything the day's record should carry."
              label="Notes"
              name="notes"
              rows={3}
            />
          </FormLayout>
        </Form>
      </Modal>
    </div>
  );
}
