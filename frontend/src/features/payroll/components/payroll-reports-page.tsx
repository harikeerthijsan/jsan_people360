'use client';

import * as React from 'react';

import { Can } from '@/components/common/can';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { EmployeePicker } from '@/features/workforce/components/employee-picker';
import { useExportPayrollReport, usePayrollPeriods, usePayrollReport } from '@/features/payroll/hooks';
import {
  REPORT_KIND_LABELS,
  RUN_STATUS_LABELS,
  formatMoney,
  type DeductionReportRow,
  type EarningsReportRow,
  type MonthlyReportRow,
  type OvertimeReportRow,
  type PayrollReportFilters,
  type PayrollReportKind,
  type PayrollRunStatus,
  type UnpaidLeaveReportRow,
} from '@/features/payroll/types';

/**
 * The payroll report dashboard: one set of filters, six views, two export
 * formats. Official numbers come from finalized payroll — the status filter
 * defaults to it and says so when it is changed.
 */

const KINDS: PayrollReportKind[] = ['summary', 'monthly', 'earnings', 'deductions', 'overtime', 'unpaid_leave'];

export function PayrollReportsPage(): React.JSX.Element {
  const [kind, setKind] = React.useState<PayrollReportKind>('summary');
  const [periodId, setPeriodId] = React.useState('');
  const [dateFrom, setDateFrom] = React.useState('');
  const [dateTo, setDateTo] = React.useState('');
  const [teamId, setTeamId] = React.useState('');
  const [locationId, setLocationId] = React.useState('');
  const [employeeId, setEmployeeId] = React.useState('');
  const [status, setStatus] = React.useState<PayrollRunStatus>('finalized');
  const periods = usePayrollPeriods({ page_size: 100 });
  const exporter = useExportPayrollReport();

  const filters: PayrollReportFilters = {
    period_id: periodId || undefined,
    date_from: dateFrom || undefined,
    date_to: dateTo || undefined,
    team_id: teamId || undefined,
    location_id: locationId || undefined,
    employee_id: employeeId || undefined,
    status,
  };
  const report = usePayrollReport(kind, filters);
  const summary = report.data?.summary;
  const currency = summary?.currency ?? 'INR';
  const money = (value: string): string => formatMoney(value, currency);

  const monthlyColumns: DataTableColumn<MonthlyReportRow>[] = [
    { id: 'employee', header: 'Employee', cell: (r) => `${r.employee_name} · ${r.employee_code}` },
    { id: 'department', header: 'Department', cell: (r) => r.department ?? '—' },
    { id: 'period', header: 'Payroll period', cell: (r) => r.period_name },
    { id: 'gross', header: 'Gross', cell: (r) => money(r.gross) },
    { id: 'deductions', header: 'Deductions', cell: (r) => money(r.deductions) },
    { id: 'adjustments', header: 'Adjustments', cell: (r) => money(r.adjustments) },
    { id: 'net', header: 'Net pay', cell: (r) => money(r.net_pay) },
    { id: 'status', header: 'Payroll status', cell: (r) => RUN_STATUS_LABELS[r.run_status] },
  ];
  const earningsColumns: DataTableColumn<EarningsReportRow>[] = [
    { id: 'employee', header: 'Employee', cell: (r) => `${r.employee_name} · ${r.employee_code}` },
    { id: 'department', header: 'Department', cell: (r) => r.department ?? '—' },
    { id: 'period', header: 'Period', cell: (r) => r.period_name },
    { id: 'basic', header: 'Basic salary', cell: (r) => money(r.basic_salary) },
    { id: 'allowances', header: 'Allowances', cell: (r) => money(r.allowances) },
    { id: 'bonus', header: 'Bonus', cell: (r) => money(r.bonus) },
    { id: 'overtime', header: 'Overtime', cell: (r) => money(r.overtime) },
    { id: 'other', header: 'Other earnings', cell: (r) => money(r.other_earnings) },
    { id: 'gross', header: 'Total gross', cell: (r) => money(r.total_gross) },
  ];
  const deductionColumns: DataTableColumn<DeductionReportRow>[] = [
    { id: 'component', header: 'Deduction component', cell: (r) => r.component },
    { id: 'amount', header: 'Amount', cell: (r) => money(r.amount) },
    { id: 'employee', header: 'Employee', cell: (r) => `${r.employee_name} · ${r.employee_code}` },
    { id: 'department', header: 'Department', cell: (r) => r.department ?? '—' },
    { id: 'period', header: 'Payroll period', cell: (r) => r.period_name },
  ];
  const overtimeColumns: DataTableColumn<OvertimeReportRow>[] = [
    { id: 'employee', header: 'Employee', cell: (r) => `${r.employee_name} · ${r.employee_code}` },
    { id: 'department', header: 'Department', cell: (r) => r.department ?? '—' },
    { id: 'period', header: 'Payroll period', cell: (r) => r.period_name },
    { id: 'hours', header: 'Approved overtime hours', cell: (r) => r.approved_overtime_hours },
    { id: 'amount', header: 'Overtime amount', cell: (r) => money(r.overtime_amount) },
  ];
  const unpaidColumns: DataTableColumn<UnpaidLeaveReportRow>[] = [
    { id: 'employee', header: 'Employee', cell: (r) => `${r.employee_name} · ${r.employee_code}` },
    { id: 'period', header: 'Payroll period', cell: (r) => r.period_name },
    { id: 'days', header: 'Unpaid leave days', cell: (r) => r.unpaid_leave_days },
    { id: 'basis', header: 'Deduction basis', cell: (r) => r.deduction_basis ?? '—' },
    { id: 'amount', header: 'Deduction amount', cell: (r) => money(r.deduction_amount) },
  ];

  const table = (): React.JSX.Element | null => {
    const data = report.data;
    const common = { isLoading: report.isLoading, error: report.error, emptyTitle: 'No rows', emptyDescription: 'No finalized payroll matches these filters.' };
    switch (kind) {
      case 'monthly':
        return <DataTable rows={data?.monthly ?? []} columns={monthlyColumns} getRowId={(r) => `${r.employee_id}-${r.period_name}`} {...common} />;
      case 'earnings':
        return <DataTable rows={data?.earnings ?? []} columns={earningsColumns} getRowId={(r) => `${r.employee_id}-${r.period_name}`} {...common} />;
      case 'deductions':
        return <DataTable rows={data?.deductions ?? []} columns={deductionColumns} getRowId={(r) => `${r.employee_id}-${r.period_name}-${r.component}-${r.code ?? ""}`} {...common} />;
      case 'overtime':
        return <DataTable rows={data?.overtime ?? []} columns={overtimeColumns} getRowId={(r) => `${r.employee_id}-${r.period_name}`} {...common} />;
      case 'unpaid_leave':
        return <DataTable rows={data?.unpaid_leave ?? []} columns={unpaidColumns} getRowId={(r) => `${r.employee_id}-${r.period_name}`} {...common} />;
      default:
        return null;
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Payroll Reports"
        description="Read from finalized payroll. Employer cost is shown as gross payroll — employer contributions are not modelled by this application."
        actions={
          <Can permission="payroll:report_export">
            <div className="flex gap-2">
              <Button variant="outline" isLoading={exporter.isPending} onClick={() => exporter.mutate({ kind, filters, format: 'csv' })}>
                Export CSV
              </Button>
              <Button variant="outline" isLoading={exporter.isPending} onClick={() => exporter.mutate({ kind, filters, format: 'xlsx' })}>
                Export XLSX
              </Button>
            </div>
          </Can>
        }
      />

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="space-y-1">
          <Label htmlFor="rep-period">Payroll period</Label>
          <select id="rep-period" className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm" value={periodId} onChange={(e) => setPeriodId(e.target.value)}>
            <option value="">All periods</option>
            {(periods.data?.items ?? []).map((p) => (
              <option key={p.id} value={p.id}>{p.name}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="rep-from">Period ends from</Label>
          <Input id="rep-from" type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="rep-to">Period ends to</Label>
          <Input id="rep-to" type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="rep-status">Payroll status</Label>
          <select id="rep-status" className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm" value={status} onChange={(e) => setStatus(e.target.value as PayrollRunStatus)}>
            {(Object.keys(RUN_STATUS_LABELS) as PayrollRunStatus[]).map((s) => (
              <option key={s} value={s}>{RUN_STATUS_LABELS[s]}{s === 'finalized' ? ' (official)' : ''}</option>
            ))}
          </select>
        </div>
        <div className="space-y-1">
          <Label htmlFor="rep-team">Department (team id)</Label>
          <Input id="rep-team" placeholder="Paste a team id" value={teamId} onChange={(e) => setTeamId(e.target.value.trim())} />
        </div>
        <div className="space-y-1">
          <Label htmlFor="rep-location">Location (id)</Label>
          <Input id="rep-location" placeholder="Paste a location id" value={locationId} onChange={(e) => setLocationId(e.target.value.trim())} />
        </div>
        <div className="space-y-1 sm:col-span-2">
          <Label htmlFor="rep-employee">Employee</Label>
          <EmployeePicker id="rep-employee" value={employeeId} onChange={setEmployeeId} />
        </div>
      </div>

      {status !== 'finalized' ? (
        <p className="text-sm text-amber-700 dark:text-amber-400">
          Showing {RUN_STATUS_LABELS[status].toLowerCase()} payroll — not official figures.
        </p>
      ) : null}

      {summary ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard label="Employees" value={summary.employee_count} />
          <StatCard label="Gross payroll" value={money(summary.gross_payroll)} />
          <StatCard label="Total deductions" value={money(summary.total_deductions)} />
          <StatCard label="Net payroll" value={money(summary.net_payroll)} />
          <StatCard label="Total adjustments" value={money(summary.total_adjustments)} />
          <StatCard label="Total overtime" value={`${money(summary.total_overtime)} · ${summary.total_overtime_hours} h`} />
          <StatCard label="Total unpaid leave" value={`${money(summary.total_unpaid_leave)} · ${summary.total_unpaid_leave_days} d`} />
          <StatCard label="Employer cost (gross)" value={money(summary.total_employer_cost)} />
        </div>
      ) : null}

      <div className="flex flex-wrap gap-2">
        {KINDS.map((k) => (
          <Button key={k} size="sm" variant={k === kind ? 'default' : 'outline'} onClick={() => setKind(k)}>
            {REPORT_KIND_LABELS[k]}
          </Button>
        ))}
      </div>

      {table()}
    </div>
  );
}
