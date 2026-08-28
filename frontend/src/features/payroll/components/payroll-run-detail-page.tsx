'use client';

import Link from 'next/link';
import * as React from 'react';

import { Can } from '@/components/common/can';
import { ConfirmDialog } from '@/components/common/modal';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { routes } from '@/config/site';
import {
  useCalculateRun,
  usePayrollRun,
  usePayrollRunRecords,
  useRecalculateRun,
  useSubmitForApproval,
} from '@/features/payroll/hooks';
import {
  RECORD_STATUS_LABELS,
  RUN_STATUS_LABELS,
  formatMoney,
  type PayrollRecord,
  type PayrollRecordStatus,
} from '@/features/payroll/types';

/**
 * One payroll run: the organization-wide summary, the per-employee records,
 * and the calculate/recalculate actions. Every figure on this page is a real
 * calculated database value — nothing is derived in the browser.
 */

const RECORD_VARIANT: Record<PayrollRecordStatus, 'secondary' | 'outline' | 'destructive'> = {
  calculated: 'secondary',
  requires_review: 'destructive',
  excluded: 'outline',
  reviewed: 'secondary',
  adjustment_required: 'destructive',
  ready_for_approval: 'secondary',
};

export function PayrollRunDetailPage({ runId }: { runId: string }): React.JSX.Element {
  const runQuery = usePayrollRun(runId);
  const [statusFilter, setStatusFilter] = React.useState<PayrollRecordStatus | ''>('');
  const [search, setSearch] = React.useState('');
  const records = usePayrollRunRecords(runId, {
    status: statusFilter || undefined,
    search: search || undefined,
  });
  const calculate = useCalculateRun();
  const recalculate = useRecalculateRun();
  const submit = useSubmitForApproval();
  const [confirming, setConfirming] = React.useState<'calculate' | 'recalculate' | null>(null);

  if (runQuery.isPending) return <LoadingState />;
  if (runQuery.error) return <ErrorState error={runQuery.error} />;

  const run = runQuery.data;
  const hasNumbers = run.calculated_at !== null;
  const recalculable = [
    'draft',
    'requires_review',
    'calculated',
    'in_review',
    'review_complete',
    'returned',
  ].includes(run.status);

  const columns: DataTableColumn<PayrollRecord>[] = [
    {
      id: 'employee',
      header: 'Employee',
      cell: (row) => (
        <div>
          <div className="font-medium">{row.employee.full_name}</div>
          <div className="text-muted-foreground font-mono text-xs">{row.employee.employee_code}</div>
        </div>
      ),
    },
    { id: 'gross', header: 'Gross', cell: (row) => formatMoney(row.final_gross, row.currency) },
    {
      id: 'deductions',
      header: 'Deductions',
      cell: (row) => formatMoney(row.final_deductions, row.currency),
    },
    {
      id: 'net',
      header: 'Net pay',
      cell: (row) => (
        <div>
          <div>{formatMoney(row.final_net, row.currency)}</div>
          {row.final_net !== row.net_pay ? (
            <div className="text-muted-foreground text-xs">
              orig {formatMoney(row.net_pay, row.currency)}
            </div>
          ) : null}
        </div>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <div className="space-y-1">
          <Badge variant={RECORD_VARIANT[row.status]}>{RECORD_STATUS_LABELS[row.status]}</Badge>
          {row.exception_reason ? (
            <div className="text-muted-foreground max-w-md text-xs">{row.exception_reason}</div>
          ) : null}
        </div>
      ),
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) => (
        <Button asChild size="sm" variant="outline">
          <Link href={routes.payrollRunEmployee(runId, row.employee.id)}>Open</Link>
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={`${run.period.name} · ${run.run_code}`}
        description={`Pay date ${run.period.pay_date}. ${
          run.calculated_at
            ? `Calculated ${new Date(run.calculated_at).toLocaleString()} by ${run.calculated_by_name ?? 'unknown'}.`
            : 'Not calculated yet.'
        }`}
        actions={
          <div className="flex gap-2">
            {hasNumbers ? (
              <Can permission="payroll:review_view">
                <Button asChild variant="outline">
                  <Link href={routes.payrollRunReview(runId)}>Review</Link>
                </Button>
                <Button asChild variant="outline">
                  <Link href={routes.payrollRunReconciliation(runId)}>Reconciliation</Link>
                </Button>
              </Can>
            ) : null}
            {hasNumbers ? (
              <Can permission="payroll:approval_view">
                <Button asChild variant="outline">
                  <Link href={routes.payrollRunApproval(runId)}>Approval</Link>
                </Button>
              </Can>
            ) : null}
            {run.status === 'review_complete' ? (
              <Can permission="payroll:review_complete">
                <Button
                  isLoading={submit.isPending}
                  onClick={() => submit.mutate(runId)}
                >
                  Submit for approval
                </Button>
              </Can>
            ) : null}
            {recalculable && hasNumbers ? (
              <Can permission="payroll:recalculate">
                <Button
                  variant="outline"
                  isLoading={recalculate.isPending}
                  onClick={() => setConfirming('recalculate')}
                >
                  Recalculate
                </Button>
              </Can>
            ) : null}
            {recalculable && !hasNumbers ? (
              <Can permission="payroll:calculate">
                <Button isLoading={calculate.isPending} onClick={() => setConfirming('calculate')}>
                  Calculate payroll
                </Button>
              </Can>
            ) : null}
          </div>
        }
      />

      <div className="flex items-center gap-2">
        <Badge
          variant={
            run.status === 'requires_review' || run.status === 'returned'
              ? 'destructive'
              : 'secondary'
          }
        >
          {RUN_STATUS_LABELS[run.status]}
        </Badge>
        {run.open_critical_count > 0 ? (
          <Badge variant="destructive">{run.open_critical_count} critical exceptions</Badge>
        ) : run.open_exception_count > 0 ? (
          <Badge variant="outline">{run.open_exception_count} open exceptions</Badge>
        ) : null}
        {run.status === 'returned' && run.return_reason ? (
          <span className="text-muted-foreground text-sm">Returned: {run.return_reason}</span>
        ) : null}
        {run.status === 'finalized' ? (
          <span className="text-muted-foreground text-sm">
            Finalized by {run.finalized_by_name ?? 'unknown'} — read-only.
          </span>
        ) : null}
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Employees" value={run.employee_count} />
        <StatCard label="Gross payroll" value={formatMoney(run.total_gross, run.currency)} />
        <StatCard
          label="Total deductions"
          value={formatMoney(run.total_deductions, run.currency)}
        />
        <StatCard label="Net payroll" value={formatMoney(run.total_net, run.currency)} />
        <StatCard label="Calculated" value={run.calculated_count} />
        <StatCard label="Requires review" value={run.review_count} />
        <StatCard label="Excluded" value={run.excluded_count} />
      </div>

      <div className="flex flex-wrap items-end gap-3">
        <select
          aria-label="Record status filter"
          className="border-input bg-background h-9 rounded-md border px-3 text-sm"
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value as PayrollRecordStatus | '')}
        >
          <option value="">All statuses</option>
          {(Object.keys(RECORD_STATUS_LABELS) as PayrollRecordStatus[]).map((status) => (
            <option key={status} value={status}>
              {RECORD_STATUS_LABELS[status]}
            </option>
          ))}
        </select>
        <Input
          aria-label="Search employees"
          placeholder="Search by name or code"
          className="max-w-xs"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </div>

      <DataTable
        rows={records.data?.items ?? []}
        columns={columns}
        getRowId={(row) => row.id}
        isLoading={records.isLoading}
        error={records.error}
        emptyTitle="No records yet"
        emptyDescription="Calculate the run to produce one record per employee, each a full line-item breakdown."
      />

      <ConfirmDialog
        open={confirming !== null}
        onOpenChange={(open) => {
          if (!open) setConfirming(null);
        }}
        title={
          confirming === 'recalculate'
            ? `Recalculate ${run.period.name}?`
            : `Calculate ${run.period.name}?`
        }
        description={
          confirming === 'recalculate'
            ? 'Existing records are replaced whole — never duplicated. Inputs flagged for review stay refused until resolved.'
            : 'The engine consumes the prepared payroll inputs and produces one record per employee. Nothing is approved or paid.'
        }
        confirmLabel={confirming === 'recalculate' ? 'Recalculate' : 'Calculate'}
        isConfirming={calculate.isPending || recalculate.isPending}
        onConfirm={() => {
          const mutation = confirming === 'recalculate' ? recalculate : calculate;
          mutation.mutate(runId, { onSuccess: () => setConfirming(null) });
        }}
      />
    </div>
  );
}
