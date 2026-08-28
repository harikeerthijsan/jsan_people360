'use client';

import Link from 'next/link';
import * as React from 'react';

import { Can } from '@/components/common/can';
import { ConfirmDialog } from '@/components/common/modal';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { routes } from '@/config/site';
import { useCreatePayrollRun, usePayrollPeriods, usePayrollRuns } from '@/features/payroll/hooks';
import {
  RUN_STATUS_LABELS,
  formatMoney,
  type PayrollRun,
  type PayrollRunStatus,
} from '@/features/payroll/types';

/**
 * Payroll runs: one per period, each the execution context of the
 * calculation engine. Creating a run produces no numbers — calculation is a
 * separate, separately-permissioned act on the run's own page.
 */

const STATUS_VARIANT: Record<PayrollRunStatus, 'secondary' | 'outline' | 'destructive'> = {
  draft: 'outline',
  calculating: 'outline',
  requires_review: 'destructive',
  calculated: 'secondary',
  in_review: 'secondary',
  review_complete: 'secondary',
  pending_approval: 'secondary',
  returned: 'destructive',
  approved: 'secondary',
  finalized: 'secondary',
};

export function PayrollRunsPage(): React.JSX.Element {
  const runs = usePayrollRuns({});
  const periods = usePayrollPeriods({ page_size: 100 });
  const create = useCreatePayrollRun();

  const [periodId, setPeriodId] = React.useState('');
  const [confirming, setConfirming] = React.useState(false);

  const runPeriodIds = new Set((runs.data?.items ?? []).map((run) => run.period.id));
  const availablePeriods = (periods.data?.items ?? []).filter(
    (period) => !runPeriodIds.has(period.id) && period.status !== 'cancelled',
  );
  const chosenPeriod = availablePeriods.find((period) => period.id === periodId);

  const columns: DataTableColumn<PayrollRun>[] = [
    {
      id: 'run',
      header: 'Run',
      cell: (row) => (
        <div>
          <div className="font-medium">{row.period.name}</div>
          <div className="text-muted-foreground font-mono text-xs">{row.run_code}</div>
        </div>
      ),
    },
    {
      id: 'window',
      header: 'Period',
      cell: (row) => `${row.period.start_date} → ${row.period.end_date}`,
    },
    { id: 'employees', header: 'Employees', cell: (row) => row.employee_count },
    { id: 'gross', header: 'Gross', cell: (row) => formatMoney(row.total_gross, row.currency) },
    { id: 'net', header: 'Net', cell: (row) => formatMoney(row.total_net, row.currency) },
    {
      id: 'review',
      header: 'Review',
      cell: (row) =>
        row.review_count > 0 ? <Badge variant="destructive">{row.review_count}</Badge> : '—',
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <Badge variant={STATUS_VARIANT[row.status]}>{RUN_STATUS_LABELS[row.status]}</Badge>
      ),
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) => (
        <Button asChild size="sm" variant="outline">
          <Link href={routes.payrollRunDetail(row.id)}>Open</Link>
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Payroll Runs"
        description="One run per period. A run is calculated from the prepared payroll inputs; nothing here approves, finalizes or pays anything yet."
      />

      <Can permission="payroll:run_create">
        <Card>
          <CardHeader>
            <CardTitle>New payroll run</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <Label htmlFor="run-period">Payroll period</Label>
              <select
                id="run-period"
                className="border-input bg-background h-9 rounded-md border px-3 text-sm"
                value={periodId}
                onChange={(event) => setPeriodId(event.target.value)}
              >
                <option value="">
                  {periods.isPending ? 'Loading periods…' : 'Choose a period without a run'}
                </option>
                {availablePeriods.map((period) => (
                  <option key={period.id} value={period.id}>
                    {period.name}
                  </option>
                ))}
              </select>
            </div>
            <Button disabled={!periodId} onClick={() => setConfirming(true)}>
              Create run
            </Button>
          </CardContent>
        </Card>
      </Can>

      <DataTable
        rows={runs.data?.items ?? []}
        columns={columns}
        getRowId={(row) => row.id}
        isLoading={runs.isLoading}
        error={runs.error}
        emptyTitle="No payroll runs"
        emptyDescription="Create a run for a period, then calculate it from the run's page."
      />

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`Create the payroll run for ${chosenPeriod?.name ?? 'this period'}?`}
        description="The run is created as a draft with no numbers. Calculation happens from the run's page and needs its own permission."
        confirmLabel="Create run"
        isConfirming={create.isPending}
        onConfirm={() =>
          create.mutate(
            { periodId },
            {
              onSuccess: () => {
                setConfirming(false);
                setPeriodId('');
              },
            },
          )
        }
      />
    </div>
  );
}
