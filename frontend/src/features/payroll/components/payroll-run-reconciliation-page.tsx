'use client';

import Link from 'next/link';
import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { routes } from '@/config/site';
import {
  usePayrollRun,
  useRunComparison,
  useRunReconciliation,
} from '@/features/payroll/hooks';
import { formatMoney, type PayrollComparisonRow } from '@/features/payroll/types';

/**
 * Reconciliation: original calculation, adjustments, and final payroll side
 * by side, plus this run against the previous period. Large moves are
 * highlighted for a human to look at — nothing is rejected automatically.
 */

export function PayrollRunReconciliationPage({ runId }: { runId: string }): React.JSX.Element {
  const runQuery = usePayrollRun(runId);
  const reconciliation = useRunReconciliation(runId);
  const comparison = useRunComparison(runId);

  if (runQuery.isPending || reconciliation.isPending) return <LoadingState />;
  if (runQuery.error) return <ErrorState error={runQuery.error} />;
  if (reconciliation.error) return <ErrorState error={reconciliation.error} />;

  const run = runQuery.data;
  const totals = reconciliation.data;
  const diff = (value: string | null): React.ReactNode => {
    if (value === null) return <span className="text-muted-foreground">new</span>;
    const amount = Number(value);
    if (amount === 0) return '—';
    return (
      <span className={amount > 0 ? 'text-emerald-600 dark:text-emerald-400' : 'text-red-600 dark:text-red-400'}>
        {amount > 0 ? '+' : ''}
        {formatMoney(value, run.currency)}
      </span>
    );
  };

  const comparisonColumns: DataTableColumn<PayrollComparisonRow>[] = [
    {
      id: 'employee',
      header: 'Employee',
      cell: (row) => (
        <div className="flex items-center gap-2">
          <div>
            <div className="font-medium">{row.employee.full_name}</div>
            <div className="text-muted-foreground font-mono text-xs">
              {row.employee.employee_code}
            </div>
          </div>
          {row.notable ? <Badge variant="destructive">Notable</Badge> : null}
        </div>
      ),
    },
    {
      id: 'previous',
      header: 'Previous net',
      cell: (row) =>
        row.previous_net === null ? (
          <span className="text-muted-foreground">Not in previous run</span>
        ) : (
          formatMoney(row.previous_net, run.currency)
        ),
    },
    {
      id: 'current',
      header: 'Current net',
      cell: (row) => formatMoney(row.current_net, run.currency),
    },
    { id: 'net-diff', header: 'Net change', cell: (row) => diff(row.net_difference) },
    { id: 'gross-diff', header: 'Gross change', cell: (row) => diff(row.gross_difference) },
    {
      id: 'deduction-diff',
      header: 'Deduction change',
      cell: (row) => diff(row.deduction_difference),
    },
  ];

  const reconRow = (
    label: string,
    original: string,
    adjustment: string,
    final: string,
  ): React.JSX.Element => (
    <div key={label} className="grid grid-cols-4 gap-2 border-b py-2 text-sm">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right">{formatMoney(original, run.currency)}</span>
      <span className="text-right">{formatMoney(adjustment, run.currency)}</span>
      <span className="text-right font-medium">{formatMoney(final, run.currency)}</span>
    </div>
  );

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Reconciliation · ${run.period.name}`}
        description={`${run.run_code}. Original calculation plus adjustments equals final payroll — the three are kept apart so the trail stays readable.`}
        actions={
          <div className="flex gap-2">
            <Button asChild variant="outline">
              <Link href={routes.payrollRunDetail(runId)}>Run summary</Link>
            </Button>
            <Button asChild variant="outline">
              <Link href={routes.payrollRunReview(runId)}>Review</Link>
            </Button>
          </div>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Final net payroll" value={formatMoney(totals.final_net, run.currency)} />
        <StatCard
          label="Net adjustment"
          value={formatMoney(totals.net_adjustment, run.currency)}
        />
        <StatCard
          label="Active adjustments"
          value={`${String(totals.adjustment_count)} (${String(totals.employees_affected)} employees)`}
        />
        <StatCard label="Cancelled adjustments" value={totals.cancelled_adjustment_count} />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Original · Adjustment · Final</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="text-muted-foreground grid grid-cols-4 gap-2 border-b pb-2 text-sm font-medium">
            <span />
            <span className="text-right">Original calculation</span>
            <span className="text-right">Adjustments</span>
            <span className="text-right">Final</span>
          </div>
          {reconRow('Gross', totals.original_gross, totals.adjustment_earnings, totals.final_gross)}
          {reconRow(
            'Deductions',
            totals.original_deductions,
            totals.adjustment_deductions,
            totals.final_deductions,
          )}
          {reconRow('Net', totals.original_net, totals.net_adjustment, totals.final_net)}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Against the previous period</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            rows={comparison.data ?? []}
            columns={comparisonColumns}
            getRowId={(row) => row.employee.id}
            isLoading={comparison.isLoading}
            error={comparison.error}
            emptyTitle="Nothing to compare"
            emptyDescription="Calculate the run to compare it with the previous period."
          />
          <p className="text-muted-foreground mt-3 text-xs">
            &quot;Notable&quot; marks a net movement beyond the review threshold, or an employee new
            to payroll. It is a highlight for a human, never an automatic rejection.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
