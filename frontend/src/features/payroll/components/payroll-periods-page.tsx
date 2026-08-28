'use client';

import * as React from 'react';

import { Can } from '@/components/common/can';
import { ConfirmDialog } from '@/components/common/modal';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { periodFormSchema, type PeriodFormValues } from '@/features/payroll/schema';
import {
  useCreatePayrollPeriod,
  usePayrollPeriods,
  useSetPeriodStatus,
  useUpdatePayrollPeriod,
} from '@/features/payroll/hooks';
import {
  PERIOD_STATUS_LABELS,
  PERIOD_TRANSITIONS,
  type PayrollPeriod,
  type PayrollPeriodStatus,
} from '@/features/payroll/types';

/**
 * Payroll periods.
 *
 * Created and managed here; run nowhere — the calculation engine belongs to a
 * later phase. Status moves only along the server's transition table (the
 * buttons below mirror it, and the server refuses anything else), dates are
 * editable only while a period is open, and overlapping periods are refused.
 */

const EMPTY_FORM: PeriodFormValues = {
  name: '',
  start_date: '',
  end_date: '',
  pay_date: '',
  notes: null,
};

const STATUS_VARIANT: Record<PayrollPeriodStatus, 'secondary' | 'outline' | 'destructive'> = {
  open: 'secondary',
  processing: 'outline',
  under_review: 'outline',
  approved: 'secondary',
  finalized: 'secondary',
  cancelled: 'destructive',
};

export function PayrollPeriodsPage(): React.JSX.Element {
  const [statusFilter, setStatusFilter] = React.useState<PayrollPeriodStatus | ''>('');
  const query = usePayrollPeriods({ status: statusFilter || undefined });
  const create = useCreatePayrollPeriod();
  const update = useUpdatePayrollPeriod();
  const setStatus = useSetPeriodStatus();

  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [form, setForm] = React.useState<PeriodFormValues>(EMPTY_FORM);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [pendingMove, setPendingMove] = React.useState<{
    period: PayrollPeriod;
    to: PayrollPeriodStatus;
  } | null>(null);

  const rows = query.data?.items ?? [];
  const editing = editingId !== null;

  const startEdit = (row: PayrollPeriod): void => {
    setEditingId(row.id);
    setErrors({});
    setForm({
      name: row.name,
      start_date: row.start_date,
      end_date: row.end_date,
      pay_date: row.pay_date,
      notes: row.notes,
    });
  };

  const reset = (): void => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setErrors({});
  };

  const submit = (event: React.FormEvent): void => {
    event.preventDefault();
    const parsed = periodFormSchema.safeParse(form);
    if (!parsed.success) {
      const fieldErrors: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        fieldErrors[String(issue.path[0] ?? 'form')] = issue.message;
      }
      setErrors(fieldErrors);
      return;
    }
    setErrors({});
    if (editingId !== null) {
      update.mutate({ periodId: editingId, payload: parsed.data }, { onSuccess: reset });
    } else {
      create.mutate(parsed.data, { onSuccess: reset });
    }
  };

  const dateField = (key: 'start_date' | 'end_date' | 'pay_date', label: string): React.JSX.Element => (
    <div className="space-y-2">
      <Label htmlFor={`period-${key}`}>{label}</Label>
      <Input
        id={`period-${key}`}
        type="date"
        value={form[key]}
        onChange={(event) => setForm({ ...form, [key]: event.target.value })}
      />
      {errors[key] ? <p className="text-destructive text-xs">{errors[key]}</p> : null}
    </div>
  );

  const columns: DataTableColumn<PayrollPeriod>[] = [
    { id: 'name', header: 'Period', cell: (row) => <span className="font-medium">{row.name}</span> },
    { id: 'window', header: 'Dates', cell: (row) => `${row.start_date} → ${row.end_date}` },
    { id: 'pay', header: 'Pay date', cell: (row) => row.pay_date },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <Badge variant={STATUS_VARIANT[row.status]}>{PERIOD_STATUS_LABELS[row.status]}</Badge>
      ),
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) => (
        <Can permission="payroll:period_manage">
          <div className="flex justify-end gap-2">
            {row.status === 'open' ? (
              <Button size="sm" variant="outline" onClick={() => startEdit(row)}>
                Edit
              </Button>
            ) : null}
            {PERIOD_TRANSITIONS[row.status].map((target) => (
              <Button
                key={target}
                size="sm"
                variant={target === 'cancelled' ? 'ghost' : 'outline'}
                onClick={() => setPendingMove({ period: row, to: target })}
              >
                {PERIOD_STATUS_LABELS[target]}
              </Button>
            ))}
          </div>
        </Can>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Payroll Periods"
        description="The spans a future payroll run will cover. This phase creates and manages them; nothing is calculated yet."
      />

      <Can permission="payroll:period_manage">
        <Card>
          <CardHeader>
            <CardTitle>{editing ? `Edit ${form.name || 'period'}` : 'New period'}</CardTitle>
          </CardHeader>
          <CardContent>
            <form className="grid gap-4 sm:grid-cols-4" onSubmit={submit}>
              <div className="space-y-2">
                <Label htmlFor="period-name">Name</Label>
                <Input
                  id="period-name"
                  placeholder="August 2026"
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                />
                {errors.name ? <p className="text-destructive text-xs">{errors.name}</p> : null}
              </div>
              {dateField('start_date', 'Start date')}
              {dateField('end_date', 'End date')}
              {dateField('pay_date', 'Pay date')}
              <div className="flex gap-2 sm:col-span-4">
                <Button type="submit" isLoading={create.isPending || update.isPending}>
                  {editing ? 'Save changes' : 'Create period'}
                </Button>
                {editing ? (
                  <Button type="button" variant="outline" onClick={reset}>
                    Cancel
                  </Button>
                ) : null}
              </div>
            </form>
          </CardContent>
        </Card>
      </Can>

      <div className="flex items-end gap-3">
        <select
          aria-label="Status filter"
          className="border-input bg-background h-9 rounded-md border px-3 text-sm"
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value as PayrollPeriodStatus | '')}
        >
          <option value="">All statuses</option>
          {(Object.keys(PERIOD_STATUS_LABELS) as PayrollPeriodStatus[]).map((status) => (
            <option key={status} value={status}>
              {PERIOD_STATUS_LABELS[status]}
            </option>
          ))}
        </select>
      </div>

      <DataTable
        rows={rows}
        columns={columns}
        getRowId={(row) => row.id}
        isLoading={query.isLoading}
        error={query.error}
        emptyTitle="No payroll periods"
        emptyDescription="Create the first period — for example August 2026 — and the later payroll phases will run against it."
      />

      <ConfirmDialog
        open={pendingMove !== null}
        onOpenChange={(open) => {
          if (!open) setPendingMove(null);
        }}
        title={
          pendingMove
            ? `Move ${pendingMove.period.name} to ${PERIOD_STATUS_LABELS[pendingMove.to]}?`
            : 'Move period?'
        }
        description={
          pendingMove?.to === 'cancelled'
            ? 'A cancelled period is terminal and its dates become available to a new period.'
            : pendingMove?.to === 'finalized'
              ? 'Finalized is terminal: the period can never be reopened or edited.'
              : 'The server enforces the workflow; steps can fall back one stage until finalized.'
        }
        confirmLabel={pendingMove ? PERIOD_STATUS_LABELS[pendingMove.to] : 'Confirm'}
        destructive={pendingMove?.to === 'cancelled' || pendingMove?.to === 'finalized'}
        isConfirming={setStatus.isPending}
        onConfirm={() => {
          if (pendingMove === null) return;
          setStatus.mutate(
            { periodId: pendingMove.period.id, status: pendingMove.to },
            { onSuccess: () => setPendingMove(null) },
          );
        }}
      />
    </div>
  );
}
