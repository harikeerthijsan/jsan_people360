'use client';

import * as React from 'react';

import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { usePayrollRunRecord } from '@/features/payroll/hooks';
import {
  ADJUSTMENT_STATUS_LABELS,
  COMPONENT_TYPE_LABELS,
  RECORD_STATUS_LABELS,
  formatMoney,
  type PayrollRecordDetail,
} from '@/features/payroll/types';

/**
 * One employee's calculated payroll: the payslip-to-be. Every line carries
 * the basis it was computed on, because "how" is the question a payroll
 * number gets asked.
 */

export function PayslipBreakdown({ record }: { record: PayrollRecordDetail }): React.JSX.Element {
  const earnings = record.line_items.filter((item) => item.item_type === 'earning');
  const deductions = record.line_items.filter((item) => item.item_type === 'deduction');

  const section = (
    title: string,
    items: typeof earnings,
    total: string,
  ): React.JSX.Element => (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {items.length === 0 ? (
          <p className="text-muted-foreground text-sm">None.</p>
        ) : (
          items.map((item) => (
            <div key={item.id} className="flex items-start justify-between gap-4 border-b py-2 text-sm">
              <div>
                <div className="font-medium">{item.name}</div>
                <div className="text-muted-foreground text-xs">{item.calculation_basis}</div>
              </div>
              <div className="text-right">
                <div>{formatMoney(item.amount, record.currency)}</div>
                {item.prorated && item.original_amount ? (
                  <div className="text-muted-foreground text-xs">
                    of {formatMoney(item.original_amount, record.currency)}
                  </div>
                ) : null}
              </div>
            </div>
          ))
        )}
        <div className="flex justify-between pt-3 text-sm font-semibold">
          <span>Total</span>
          <span>{formatMoney(total, record.currency)}</span>
        </div>
      </CardContent>
    </Card>
  );

  // Review-phase adjustments never edit the calculation: when any exist, the
  // page shows all three layers — Original, Adjustment, Final — side by side.
  const hasAdjustments =
    record.adjustments.length > 0 ||
    Number(record.adjustment_earnings) !== 0 ||
    Number(record.adjustment_deductions) !== 0;

  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard
          label={hasAdjustments ? 'Final gross' : 'Gross earnings'}
          value={formatMoney(record.final_gross, record.currency)}
        />
        <StatCard
          label={hasAdjustments ? 'Final deductions' : 'Total deductions'}
          value={formatMoney(record.final_deductions, record.currency)}
        />
        <StatCard
          label={hasAdjustments ? 'Final net pay' : 'Net pay'}
          value={formatMoney(record.final_net, record.currency)}
        />
      </div>

      {hasAdjustments ? (
        <Card>
          <CardHeader>
            <CardTitle>Original · Adjustment · Final</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            <div className="text-muted-foreground grid grid-cols-4 gap-2 border-b pb-2 font-medium">
              <span />
              <span className="text-right">Original calculation</span>
              <span className="text-right">Adjustment</span>
              <span className="text-right">Final</span>
            </div>
            {(
              [
                ['Gross', record.gross_earnings, record.adjustment_earnings, record.final_gross],
                [
                  'Deductions',
                  record.total_deductions,
                  record.adjustment_deductions,
                  record.final_deductions,
                ],
                ['Net pay', record.net_pay, '—', record.final_net],
              ] as const
            ).map(([label, original, adjustment, final]) => (
              <div key={label} className="grid grid-cols-4 gap-2 border-b py-2">
                <span className="text-muted-foreground">{label}</span>
                <span className="text-right">{formatMoney(original, record.currency)}</span>
                <span className="text-right">
                  {adjustment === '—' ? '—' : formatMoney(adjustment, record.currency)}
                </span>
                <span className="text-right font-medium">{formatMoney(final, record.currency)}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      {record.adjustments.length > 0 ? (
        <Card>
          <CardHeader>
            <CardTitle>Adjustments</CardTitle>
          </CardHeader>
          <CardContent>
            {record.adjustments.map((adjustment) => (
              <div
                key={adjustment.id}
                className="flex items-start justify-between gap-4 border-b py-2 text-sm"
              >
                <div>
                  <div className="font-medium">
                    {adjustment.name}
                    <Badge
                      className="ml-2"
                      variant={adjustment.status === 'active' ? 'secondary' : 'outline'}
                    >
                      {ADJUSTMENT_STATUS_LABELS[adjustment.status]}
                    </Badge>
                  </div>
                  <div className="text-muted-foreground text-xs">
                    {COMPONENT_TYPE_LABELS[adjustment.item_type]} · {adjustment.reason}
                  </div>
                  {adjustment.cancel_reason ? (
                    <div className="text-muted-foreground text-xs">
                      Cancelled: {adjustment.cancel_reason}
                    </div>
                  ) : null}
                </div>
                <div className={adjustment.status === 'cancelled' ? 'line-through opacity-60' : ''}>
                  {formatMoney(adjustment.amount, record.currency)}
                </div>
              </div>
            ))}
          </CardContent>
        </Card>
      ) : null}

      <div className="grid gap-4 lg:grid-cols-2">
        {section('Earnings', earnings, record.gross_earnings)}
        {section('Deductions', deductions, record.total_deductions)}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Attendance basis</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            {(
              [
                ['Working days', String(record.working_days)],
                ['Eligible days', String(record.eligible_days)],
                ['Present days', String(record.present_days)],
                ['Paid leave', record.paid_leave_days],
                ['Unpaid leave', record.unpaid_leave_days],
                ['Overtime paid (h)', record.overtime_hours_paid],
              ] as const
            ).map(([label, value]) => (
              <div key={label} className="flex justify-between border-b py-2">
                <span className="text-muted-foreground">{label}</span>
                <span>{value}</span>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Salary record used</CardTitle>
          </CardHeader>
          <CardContent className="text-sm">
            {(
              [
                ['Structure', record.structure_name ?? '—'],
                [
                  'Monthly basic',
                  record.monthly_basic ? formatMoney(record.monthly_basic, record.currency) : '—',
                ],
                [
                  'Monthly gross',
                  record.monthly_gross ? formatMoney(record.monthly_gross, record.currency) : '—',
                ],
                [
                  'Annual CTC',
                  record.annual_ctc ? formatMoney(record.annual_ctc, record.currency) : '—',
                ],
                ['Proration basis', record.proration_basis ?? '—'],
              ] as const
            ).map(([label, value]) => (
              <div key={label} className="flex justify-between border-b py-2">
                <span className="text-muted-foreground">{label}</span>
                <span>{value}</span>
              </div>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export function PayrollRecordPage({
  runId,
  employeeId,
}: {
  runId: string;
  employeeId: string;
}): React.JSX.Element {
  const query = usePayrollRunRecord(runId, employeeId);

  if (query.isPending) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} />;

  const record = query.data;

  return (
    <div className="space-y-6">
      <PageHeader
        title={`${record.employee.full_name} · ${record.period.name}`}
        description="Calculated payroll record. Every amount carries the basis it was computed on."
      />
      <div className="flex items-center gap-2">
        <Badge
          variant={
            record.status === 'requires_review' || record.status === 'adjustment_required'
              ? 'destructive'
              : record.status === 'excluded'
                ? 'outline'
                : 'secondary'
          }
        >
          {RECORD_STATUS_LABELS[record.status]}
        </Badge>
        {record.exception_reason ? (
          <span className="text-muted-foreground text-sm">{record.exception_reason}</span>
        ) : null}
      </div>
      <PayslipBreakdown record={record} />
    </div>
  );
}
