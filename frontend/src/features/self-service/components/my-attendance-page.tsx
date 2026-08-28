'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import * as React from 'react';
import { useForm } from 'react-hook-form';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { FormLayout, FormSection } from '@/components/common/form-layout';
import { LoadingState } from '@/components/common/loading-state';
import { Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Tabs } from '@/components/common/tabs';
import { TextField } from '@/components/common/text-field';
import { TextareaField } from '@/components/common/textarea-field';
import {
  ApprovalStatusBadge,
  AttendanceCalendar,
  AttendanceStatusBadge,
  WorkModeBadge,
  formatMinutes,
} from '@/components/common/workforce-widgets';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Form } from '@/components/ui/form';
import { AttendanceCard } from '@/features/self-service/components/attendance-card';
import {
  useMyAttendance,
  useMyAttendanceSummary,
  useMyCalendar,
  useMyRegularizations,
  useRequestRegularization,
} from '@/features/self-service/hooks';
import { myRegularizationSchema, type MyRegularizationFormValues } from '@/features/self-service/schema';
import type { AttendanceRecord } from '@/features/self-service/types';
import type { Regularization } from '@/features/self-service/api';
import type { CalendarDay } from '@/features/workforce/types';

/**
 * My Attendance.
 *
 * Three tabs rather than three pages, because they are three views of the same
 * month and a person comparing "what the calendar says" with "what the register
 * says" should not be navigating between routes to do it. The active tab lives
 * in the URL, so a colleague can be sent a link to the one that matters.
 *
 * The register is read-only by construction: there is no edit action anywhere on
 * this screen, and the API has no endpoint for one. A wrong day is fixed by
 * asking, which is what the corrections tab is.
 */

function monthLabel(year: number, month: number): string {
  return new Date(year, month - 1, 1).toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
}

function clock(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function MonthPicker({
  year,
  month,
  onChange,
}: {
  year: number;
  month: number;
  onChange: (year: number, month: number) => void;
}): React.JSX.Element {
  const shift = (by: number): void => {
    const moved = new Date(year, month - 1 + by, 1);
    onChange(moved.getFullYear(), moved.getMonth() + 1);
  };

  return (
    <div className="flex items-center gap-2">
      <Button
        aria-label="Previous month"
        onClick={() => {
          shift(-1);
        }}
        size="sm"
        variant="outline"
      >
        ‹
      </Button>
      <span className="min-w-40 text-center text-sm font-medium">{monthLabel(year, month)}</span>
      <Button
        aria-label="Next month"
        onClick={() => {
          shift(1);
        }}
        size="sm"
        variant="outline"
      >
        ›
      </Button>
    </div>
  );
}

export function MyAttendancePage(): React.JSX.Element {
  const now = React.useMemo(() => new Date(), []);
  const [year, setYear] = React.useState(now.getFullYear());
  const [month, setMonth] = React.useState(now.getMonth() + 1);
  const [isRequesting, setIsRequesting] = React.useState(false);

  const range = React.useMemo(() => {
    const first = new Date(year, month - 1, 1);
    const last = new Date(year, month, 0);
    const iso = (value: Date): string =>
      `${String(value.getFullYear())}-${String(value.getMonth() + 1).padStart(2, '0')}-${String(value.getDate()).padStart(2, '0')}`;
    return { from: iso(first), to: iso(last) };
  }, [year, month]);

  const calendar = useMyCalendar(year, month);
  const summary = useMyAttendanceSummary(range.from, range.to);
  const records = useMyAttendance({ from_date: range.from, to_date: range.to });
  const corrections = useMyRegularizations();
  const request = useRequestRegularization();

  const form = useForm<MyRegularizationFormValues>({
    resolver: zodResolver(myRegularizationSchema),
    defaultValues: {
      attendance_date: '',
      requested_check_in_at: '',
      requested_check_out_at: '',
      reason: '',
      supporting_document_id: '',
    },
  });

  const submit = form.handleSubmit((values) => {
    // `datetime-local` has no timezone; the API stores UTC instants, so the
    // browser's own offset is what turns one into the other.
    const asInstant = (value: string | undefined): string | null =>
      value ? new Date(value).toISOString() : null;

    request.mutate(
      {
        attendance_date: values.attendance_date,
        requested_check_in_at: asInstant(values.requested_check_in_at),
        requested_check_out_at: asInstant(values.requested_check_out_at),
        reason: values.reason,
        supporting_document_id: values.supporting_document_id ?? null,
      },
      {
        onSuccess: () => {
          setIsRequesting(false);
          form.reset();
        },
      },
    );
  });

  const registerColumns: DataTableColumn<AttendanceRecord>[] = [
    {
      id: 'date',
      header: 'Date',
      cell: (row) => <span className="tabular-nums">{row.attendance_date}</span>,
    },
    { id: 'status', header: 'Status', cell: (row) => <AttendanceStatusBadge status={row.status} /> },
    { id: 'mode', header: 'Mode', cell: (row) => <WorkModeBadge mode={row.work_mode} /> },
    {
      id: 'in',
      header: 'In',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{clock(row.check_in_at)}</span>,
    },
    {
      id: 'out',
      header: 'Out',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{clock(row.check_out_at)}</span>,
    },
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
          <span className="text-destructive tabular-nums">{formatMinutes(row.late_minutes)}</span>
        ) : (
          '—'
        ),
    },
    {
      id: 'early',
      header: 'Early exit',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{formatMinutes(row.early_exit_minutes)}</span>,
    },
    {
      id: 'overtime',
      header: 'Overtime',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{formatMinutes(row.overtime_minutes)}</span>,
    },
  ];

  const correctionColumns: DataTableColumn<Regularization>[] = [
    {
      id: 'date',
      header: 'Date',
      cell: (row) => <span className="tabular-nums">{row.attendance_date}</span>,
    },
    {
      id: 'requested',
      header: 'Requested',
      cell: (row) => (
        <span className="tabular-nums">
          {clock(row.requested_check_in_at)} – {clock(row.requested_check_out_at)}
        </span>
      ),
    },
    { id: 'reason', header: 'Reason', cell: (row) => <span className="line-clamp-2">{row.reason}</span> },
    { id: 'status', header: 'Status', cell: (row) => <ApprovalStatusBadge status={row.status} /> },
    {
      id: 'notes',
      header: 'Decision',
      cell: (row) => <span className="text-muted-foreground">{row.decision_notes ?? '—'}</span>,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Attendance"
        description="Your own days. A record is corrected by asking, never by editing it here."
        actions={
          <Button
            onClick={() => {
              setIsRequesting(true);
            }}
          >
            Request a correction
          </Button>
        }
      />

      <AttendanceCard />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard hint={monthLabel(year, month)} label="Present" value={summary.data?.present_days ?? 0} />
        <StatCard
          hint="after the grace period"
          label="Late arrivals"
          value={summary.data?.late_arrivals ?? 0}
        />
        <StatCard hint="before the shift ended" label="Early exits" value={summary.data?.early_exits ?? 0} />
        <StatCard label="Overtime" value={formatMinutes(summary.data?.overtime_minutes ?? 0)} />
      </div>

      <div className="flex items-center justify-end">
        <MonthPicker
          month={month}
          onChange={(nextYear, nextMonth) => {
            setYear(nextYear);
            setMonth(nextMonth);
          }}
          year={year}
        />
      </div>

      <Tabs
        label="Attendance views"
        paramName="view"
        tabs={[
          { id: 'calendar', label: 'Calendar' },
          { id: 'register', label: 'History' },
          {
            id: 'corrections',
            label: 'Corrections',
            badge: corrections.data?.meta.total_items ? corrections.data.meta.total_items : undefined,
          },
        ]}
      >
        {(active) =>
          active === 'calendar' ? (
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">{monthLabel(year, month)}</CardTitle>
                <CardDescription>
                  Present, absent, leave, holidays and weekly offs. Hover a square for the detail.
                </CardDescription>
              </CardHeader>
              <CardContent>
                {calendar.isPending ? (
                  <LoadingState />
                ) : (
                  <AttendanceCalendar days={(calendar.data ?? []) as CalendarDay[]} />
                )}
              </CardContent>
            </Card>
          ) : active === 'register' ? (
            <DataTable
              columns={registerColumns}
              emptyDescription="Nothing is recorded for this month."
              emptyTitle="No attendance"
              error={records.error}
              getRowId={(row) => row.id}
              isLoading={records.isPending}
              onRetry={() => void records.refetch()}
              rows={records.data?.items ?? []}
            />
          ) : (
            <DataTable
              columns={correctionColumns}
              emptyDescription="You have not asked for a correction."
              emptyTitle="No corrections"
              error={corrections.error}
              getRowId={(row) => row.id}
              isLoading={corrections.isPending}
              onRetry={() => void corrections.refetch()}
              rows={corrections.data?.items ?? []}
            />
          )
        }
      </Tabs>

      <Modal
        description="Your manager decides. Approving is what amends the record."
        onOpenChange={setIsRequesting}
        open={isRequesting}
        size="lg"
        title="Request an attendance correction"
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
            <FormSection title="The day">
              <TextField control={form.control} label="Date" name="attendance_date" required type="date" />
              <div />
              <TextField
                control={form.control}
                description="Leave blank if only the check-out was wrong."
                label="Check-in should be"
                name="requested_check_in_at"
                type="datetime-local"
              />
              <TextField
                control={form.control}
                description="Leave blank if only the check-in was wrong."
                label="Check-out should be"
                name="requested_check_out_at"
                type="datetime-local"
              />
              <TextareaField
                className="sm:col-span-2"
                control={form.control}
                label="Reason"
                name="reason"
                required
                rows={3}
              />
            </FormSection>
          </FormLayout>
        </Form>
      </Modal>
    </div>
  );
}
