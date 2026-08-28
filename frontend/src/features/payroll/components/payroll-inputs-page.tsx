'use client';

import Link from 'next/link';
import * as React from 'react';

import { Can } from '@/components/common/can';
import { ConfirmDialog } from '@/components/common/modal';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { EmptyState } from '@/components/common/empty-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { FileSpreadsheet } from 'lucide-react';
import { routes } from '@/config/site';
import {
  useDetectInputChanges,
  useGeneratePayrollInputs,
  usePayrollInputs,
  usePayrollPeriods,
} from '@/features/payroll/hooks';
import {
  ELIGIBILITY_LABELS,
  INPUT_STATUS_LABELS,
  type PayrollInput,
  type PayrollInputStatus,
} from '@/features/payroll/types';

/**
 * The payroll input register: what the source modules said, per employee,
 * for one period.
 *
 * Preparing reads approved attendance, leave and overtime and snapshots the
 * result; detecting changes flags inputs whose sources moved afterwards.
 * Neither touches a source record, and nothing on this screen is money.
 */

const STATUS_VARIANT: Record<PayrollInputStatus, 'secondary' | 'outline' | 'destructive'> = {
  ready: 'secondary',
  requires_review: 'destructive',
  excluded: 'outline',
};

export function PayrollInputsPage(): React.JSX.Element {
  const periods = usePayrollPeriods({ page_size: 100 });
  const [periodId, setPeriodId] = React.useState('');
  const [statusFilter, setStatusFilter] = React.useState<PayrollInputStatus | ''>('');
  const [search, setSearch] = React.useState('');
  const [confirmingPrepare, setConfirmingPrepare] = React.useState(false);

  const inputs = usePayrollInputs(periodId, {
    status: statusFilter || undefined,
    search: search || undefined,
  });
  const generate = useGeneratePayrollInputs();
  const detect = useDetectInputChanges();

  const periodOptions = React.useMemo(() => periods.data?.items ?? [], [periods.data]);
  React.useEffect(() => {
    const first = periodOptions[0];
    if (!periodId && first) setPeriodId(first.id);
  }, [periodId, periodOptions]);

  const rows = inputs.data?.items ?? [];
  const selectedPeriod = periodOptions.find((period) => period.id === periodId);
  const summary = {
    ready: rows.filter((row) => row.status === 'ready').length,
    review: rows.filter((row) => row.status === 'requires_review').length,
    excluded: rows.filter((row) => row.status === 'excluded').length,
  };

  const columns: DataTableColumn<PayrollInput>[] = [
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
    { id: 'working', header: 'Working days', cell: (row) => row.working_days },
    {
      id: 'present',
      header: 'Present',
      cell: (row) =>
        row.half_days > 0
          ? `${String(row.present_days)} (+${String(row.half_days)} half)`
          : row.present_days,
    },
    { id: 'absent', header: 'Absent', cell: (row) => row.absent_days },
    { id: 'paid-leave', header: 'Paid leave', cell: (row) => row.paid_leave_days },
    { id: 'unpaid-leave', header: 'Unpaid leave', cell: (row) => row.unpaid_leave_days },
    {
      id: 'overtime',
      header: 'Overtime (h)',
      cell: (row) =>
        row.pending_overtime_hours !== '0.00'
          ? `${row.approved_overtime_hours} (+${row.pending_overtime_hours} pending)`
          : row.approved_overtime_hours,
    },
    {
      id: 'exceptions',
      header: 'Exceptions',
      cell: (row) =>
        row.exception_count > 0 ? (
          <Badge variant="destructive">{row.exception_count}</Badge>
        ) : (
          '—'
        ),
    },
    {
      id: 'eligibility',
      header: 'Eligibility',
      cell: (row) => ELIGIBILITY_LABELS[row.eligibility],
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <div className="flex items-center gap-1.5">
          <Badge variant={STATUS_VARIANT[row.status]}>{INPUT_STATUS_LABELS[row.status]}</Badge>
          {row.source_changed ? <Badge variant="outline">Source changed</Badge> : null}
        </div>
      ),
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) => (
        <Button asChild size="sm" variant="outline">
          <Link href={routes.payrollInputDetail(row.employee.id, periodId)}>Open</Link>
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Payroll Inputs"
        description="What attendance, leave and overtime said, per employee, for a period — the data a later payroll calculation will consume. Preparing never modifies a source record."
        actions={
          periodId ? (
            <Can permission="payroll:inputs_prepare">
              <div className="flex gap-2">
                <Button
                  variant="outline"
                  isLoading={detect.isPending}
                  onClick={() => detect.mutate(periodId)}
                >
                  Detect changes
                </Button>
                <Button isLoading={generate.isPending} onClick={() => setConfirmingPrepare(true)}>
                  Prepare inputs
                </Button>
              </div>
            </Can>
          ) : null
        }
      />

      {periodOptions.length === 0 && !periods.isPending ? (
        <EmptyState
          icon={FileSpreadsheet}
          title="No payroll periods"
          description="Create a payroll period first — inputs are always prepared for one period."
        />
      ) : (
        <>
          <div className="flex flex-wrap items-end gap-3">
            <div className="space-y-1">
              <Label htmlFor="inputs-period">Payroll period</Label>
              <select
                id="inputs-period"
                className="border-input bg-background h-9 rounded-md border px-3 text-sm"
                value={periodId}
                onChange={(event) => setPeriodId(event.target.value)}
              >
                {periodOptions.map((period) => (
                  <option key={period.id} value={period.id}>
                    {period.name}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-1">
              <Label htmlFor="inputs-status">Status</Label>
              <select
                id="inputs-status"
                className="border-input bg-background h-9 rounded-md border px-3 text-sm"
                value={statusFilter}
                onChange={(event) => setStatusFilter(event.target.value as PayrollInputStatus | '')}
              >
                <option value="">All</option>
                {(Object.keys(INPUT_STATUS_LABELS) as PayrollInputStatus[]).map((status) => (
                  <option key={status} value={status}>
                    {INPUT_STATUS_LABELS[status]}
                  </option>
                ))}
              </select>
            </div>
            <Input
              aria-label="Search employees"
              placeholder="Search by name or code"
              className="max-w-xs"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Ready" value={summary.ready} />
            <StatCard label="Requires review" value={summary.review} />
            <StatCard label="Excluded" value={summary.excluded} />
          </div>

          <DataTable
            rows={rows}
            columns={columns}
            getRowId={(row) => row.id}
            isLoading={inputs.isLoading && Boolean(periodId)}
            error={inputs.error}
            emptyTitle="No inputs prepared"
            emptyDescription="Prepare inputs for this period to read attendance, leave and overtime for every in-scope employee."
          />
        </>
      )}

      <ConfirmDialog
        open={confirmingPrepare}
        onOpenChange={setConfirmingPrepare}
        title={`Prepare inputs for ${selectedPeriod?.name ?? 'this period'}?`}
        description="Approved attendance, leave and overtime are read and snapshotted for every in-scope employee. Re-running refreshes existing inputs in place and resets their review state. No attendance or leave record is modified."
        confirmLabel="Prepare"
        isConfirming={generate.isPending}
        onConfirm={() =>
          generate.mutate(periodId, { onSuccess: () => setConfirmingPrepare(false) })
        }
      />
    </div>
  );
}
