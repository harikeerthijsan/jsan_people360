'use client';

import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  COMPONENT_TYPE_LABELS,
  PAY_FREQUENCY_LABELS,
  describeComponentValue,
  formatMoney,
  type Compensation,
  type CompensationComponent,
  type SalaryHistoryEntry,
} from '@/features/payroll/types';

/**
 * Read-only building blocks shared by the admin salary page and the
 * employee's own portal page. Same shapes on purpose: there is nothing about
 * a person's own pay they must not see, so the two screens differ in *whose*
 * records the server answers with, never in what is rendered.
 */

export function CompensationSummary({ record }: { record: Compensation }): React.JSX.Element {
  return (
    <div className="space-y-4">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="Annual CTC" value={formatMoney(record.annual_ctc, record.currency)} />
        <StatCard label="Annual gross" value={formatMoney(record.annual_gross, record.currency)} />
        <StatCard label="Monthly gross" value={formatMoney(record.monthly_gross, record.currency)} />
        <StatCard label="Basic salary" value={formatMoney(record.basic_salary, record.currency)} />
      </div>
      <p className="text-muted-foreground text-sm">
        {record.structure.name} · {PAY_FREQUENCY_LABELS[record.structure.pay_frequency]} · effective{' '}
        {record.effective_from} → {record.effective_to ?? 'open'}
      </p>
    </div>
  );
}

export function ComponentBreakdown({ record }: { record: Compensation }): React.JSX.Element {
  const groups: { title: string; rows: CompensationComponent[] }[] = [
    { title: 'Earnings', rows: record.components.filter((row) => row.component_type === 'earning') },
    {
      title: 'Deductions',
      rows: record.components.filter((row) => row.component_type === 'deduction'),
    },
  ];
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      {groups.map((group) => (
        <Card key={group.title}>
          <CardHeader>
            <CardTitle>{group.title}</CardTitle>
          </CardHeader>
          <CardContent>
            {group.rows.length === 0 ? (
              <p className="text-muted-foreground text-sm">None in this structure.</p>
            ) : (
              group.rows.map((row) => (
                <div key={row.id} className="flex justify-between border-b py-2 text-sm">
                  <span>
                    {row.name}
                    <span className="text-muted-foreground ml-1 font-mono text-xs">{row.code}</span>
                  </span>
                  <span>
                    {row.calculation_type === 'percentage'
                      ? describeComponentValue(row)
                      : formatMoney(row.value, record.currency)}
                  </span>
                </div>
              ))
            )}
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

export function CompensationRecordsTable({
  records,
  isLoading,
  error,
}: {
  records: Compensation[];
  isLoading: boolean;
  error: Error | null;
}): React.JSX.Element {
  const columns: DataTableColumn<Compensation>[] = [
    {
      id: 'period',
      header: 'Period',
      cell: (row) => `${row.effective_from} → ${row.effective_to ?? 'open'}`,
    },
    { id: 'structure', header: 'Structure', cell: (row) => row.structure.name },
    { id: 'ctc', header: 'Annual CTC', cell: (row) => formatMoney(row.annual_ctc, row.currency) },
    {
      id: 'monthly',
      header: 'Monthly gross',
      cell: (row) => formatMoney(row.monthly_gross, row.currency),
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <Badge variant={row.status === 'active' ? 'secondary' : 'outline'}>{row.status}</Badge>
      ),
    },
    {
      id: 'components',
      header: 'Components',
      cell: (row) =>
        row.components
          .map((component) => `${component.code} (${COMPONENT_TYPE_LABELS[component.component_type]})`)
          .join(', '),
    },
  ];
  return (
    <DataTable
      rows={records}
      columns={columns}
      getRowId={(row) => row.id}
      isLoading={isLoading}
      error={error}
      emptyTitle="No compensation periods"
      emptyDescription="Nothing has been assigned yet."
    />
  );
}

export function SalaryHistoryTable({
  entries,
  isLoading,
  error,
}: {
  entries: SalaryHistoryEntry[];
  isLoading: boolean;
  error: Error | null;
}): React.JSX.Element {
  const columns: DataTableColumn<SalaryHistoryEntry>[] = [
    { id: 'effective', header: 'Effective from', cell: (row) => row.effective_from },
    {
      id: 'previous',
      header: 'Previous CTC',
      cell: (row) =>
        row.previous_annual_ctc === null ? '—' : formatMoney(row.previous_annual_ctc, row.currency),
    },
    { id: 'new', header: 'New CTC', cell: (row) => formatMoney(row.new_annual_ctc, row.currency) },
    { id: 'reason', header: 'Reason', cell: (row) => row.reason ?? '—' },
    { id: 'by', header: 'Changed by', cell: (row) => row.changed_by_name ?? '—' },
    {
      id: 'when',
      header: 'Recorded',
      cell: (row) => new Date(row.created_at).toLocaleDateString(),
    },
  ];
  return (
    <DataTable
      rows={entries}
      columns={columns}
      getRowId={(row) => row.id}
      isLoading={isLoading}
      error={error}
      emptyTitle="No salary changes"
      emptyDescription="Every assignment and revision will be recorded here, permanently."
    />
  );
}
