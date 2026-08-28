'use client';

import { Download } from 'lucide-react';
import * as React from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useDownloadPayslip } from '@/features/payroll/hooks';
import {
  PAYSLIP_STATUS_LABELS,
  formatMoney,
  type PayslipDetail,
  type PayslipLine,
} from '@/features/payroll/types';

/**
 * The payslip as a document — the same content the PDF renders, laid out
 * for the screen. Shared by the employee's own page and the administrator's
 * view so the two can never show different figures. Read-only by
 * construction: there is no edit surface here, and no API to back one.
 */

export function PayslipDownloadButton({
  payslipId,
  employeeId,
  size = 'default',
}: {
  payslipId: string;
  /** Present on the administrator path; absent means "my own". */
  employeeId?: string;
  size?: 'default' | 'sm';
}): React.JSX.Element {
  const download = useDownloadPayslip();
  return (
    <Button
      size={size}
      variant="outline"
      isLoading={download.isPending}
      onClick={() => download.mutate({ payslipId, employeeId })}
    >
      <Download className="mr-1 size-4" /> Download PDF
    </Button>
  );
}

function LinesCard({
  title,
  lines,
  total,
  currency,
}: {
  title: string;
  lines: PayslipLine[];
  total: string;
  currency: string;
}): React.JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {lines.length === 0 ? (
          <p className="text-muted-foreground text-sm">None.</p>
        ) : (
          lines.map((line, index) => (
            <div
              key={`${line.code ?? line.name}-${String(index)}`}
              className="flex items-start justify-between gap-4 border-b py-2 text-sm"
            >
              <div>
                <div className="font-medium">{line.name}</div>
                {line.calculation_basis ? (
                  <div className="text-muted-foreground text-xs">{line.calculation_basis}</div>
                ) : null}
              </div>
              <div className="whitespace-nowrap">{formatMoney(line.amount, currency)}</div>
            </div>
          ))
        )}
        <div className="flex justify-between pt-3 text-sm font-semibold">
          <span>Total {title.toLowerCase()}</span>
          <span>{formatMoney(total, currency)}</span>
        </div>
      </CardContent>
    </Card>
  );
}

export function PayslipDocument({
  payslip,
  employeeId,
}: {
  payslip: PayslipDetail;
  employeeId?: string;
}): React.JSX.Element {
  const { employer, employee_details: employee, currency } = payslip;
  const rows = (pairs: ReadonlyArray<readonly [string, string]>): React.JSX.Element => (
    <div className="text-sm">
      {pairs.map(([label, value]) => (
        <div key={label} className="flex justify-between gap-4 border-b py-2">
          <span className="text-muted-foreground">{label}</span>
          <span className="text-right">{value}</span>
        </div>
      ))}
    </div>
  );

  return (
    <div className="space-y-6">
      <Card>
        <CardContent className="flex flex-col gap-4 pt-6 sm:flex-row sm:items-start sm:justify-between">
          <div className="flex items-start gap-3">
            {employer.logo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={employer.logo_url} alt="" className="size-12 rounded object-contain" />
            ) : null}
            <div>
              <div className="text-lg font-semibold">{employer.name ?? 'JSAN People360'}</div>
              {employer.address ? (
                <div className="text-muted-foreground text-xs">{employer.address}</div>
              ) : null}
            </div>
          </div>
          <div className="text-left sm:text-right">
            <div className="text-muted-foreground text-xs uppercase tracking-wide">Payslip</div>
            <div className="font-mono text-sm">{payslip.payslip_number}</div>
            <div className="text-muted-foreground text-xs">
              {payslip.payroll_month} · generated {new Date(payslip.generated_at).toLocaleDateString()}
            </div>
            <Badge className="mt-1" variant="secondary">
              {PAYSLIP_STATUS_LABELS[payslip.status]}
            </Badge>
          </div>
        </CardContent>
      </Card>

      <div className="flex justify-end">
        <PayslipDownloadButton payslipId={payslip.id} employeeId={employeeId} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Employee</CardTitle>
          </CardHeader>
          <CardContent>
            {rows([
              ['Name', employee.name],
              ['Employee ID', employee.employee_code],
              ['Department', employee.department ?? '—'],
              ['Designation', employee.designation ?? '—'],
              ['Joining date', employee.joining_date ?? '—'],
              ...(employee.bank_name
                ? ([
                    ['Bank', employee.bank_name],
                    ['Account', employee.account_masked ?? '—'],
                  ] as const)
                : []),
            ])}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Payroll</CardTitle>
          </CardHeader>
          <CardContent>
            {rows([
              ['Payroll month', payslip.payroll_month],
              ['Pay period', `${payslip.period_start} → ${payslip.period_end}`],
              ['Pay date', payslip.pay_date],
              ['Pay frequency', payslip.pay_frequency],
              ['Currency', currency],
              ['Salary structure', payslip.structure_name ?? '—'],
            ])}
          </CardContent>
        </Card>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <LinesCard title="Earnings" lines={payslip.earnings} total={payslip.gross_earnings} currency={currency} />
        <LinesCard
          title="Deductions"
          lines={payslip.deductions}
          total={payslip.total_deductions}
          currency={currency}
        />
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Summary</CardTitle>
        </CardHeader>
        <CardContent>
          {rows([
            ['Gross earnings', formatMoney(payslip.gross_earnings, currency)],
            ['Total deductions', formatMoney(payslip.total_deductions, currency)],
          ])}
          <div className="flex justify-between gap-4 py-3 text-base font-semibold">
            <span>Net pay</span>
            <span>{formatMoney(payslip.net_pay, currency)}</span>
          </div>
          <p className="text-muted-foreground text-sm">{payslip.amount_in_words}</p>
          <p className="text-muted-foreground mt-3 text-xs">
            This is a computer-generated payslip drawn from finalized payroll. Its figures cannot be
            edited; a correction would be a separate, recorded payroll process.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
