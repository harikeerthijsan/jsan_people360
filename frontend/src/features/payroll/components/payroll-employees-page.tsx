'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import * as React from 'react';

import { Can } from '@/components/common/can';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { routes } from '@/config/site';
import { usePayrollRegister } from '@/features/payroll/hooks';
import { formatMoney, type CompensationListRow } from '@/features/payroll/types';
import { EmployeePicker } from '@/features/workforce/components/employee-picker';

/**
 * The payroll register: every employee's current compensation.
 *
 * Organization-wide by definition, which is why the backing endpoint pairs
 * `payroll:view` with `employees:view_all`. Assigning somebody their first
 * compensation starts from the picker below — their salary page is where the
 * assignment form lives, whether or not a record exists yet.
 */

export function PayrollEmployeesPage(): React.JSX.Element {
  const router = useRouter();
  const [search, setSearch] = React.useState('');
  const [pickedEmployee, setPickedEmployee] = React.useState('');
  const query = usePayrollRegister({ search: search || undefined });

  const rows = query.data?.items ?? [];

  const columns: DataTableColumn<CompensationListRow>[] = [
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
    { id: 'structure', header: 'Structure', cell: (row) => row.structure_name },
    {
      id: 'ctc',
      header: 'Annual CTC',
      cell: (row) => formatMoney(row.annual_ctc, row.currency),
    },
    {
      id: 'monthly',
      header: 'Monthly gross',
      cell: (row) => formatMoney(row.monthly_gross, row.currency),
    },
    {
      id: 'effective',
      header: 'Effective',
      cell: (row) => `${row.effective_from} → ${row.effective_to ?? 'open'}`,
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <Badge variant={row.status === 'active' ? 'secondary' : 'outline'}>{row.status}</Badge>
      ),
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) => (
        <Button asChild size="sm" variant="outline">
          <Link href={routes.payrollEmployeeSalary(row.employee.id)}>Open</Link>
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Employee Compensation"
        description="Who is paid under which structure, and since when. Salary details and revisions live on each employee's salary page."
      />

      <Can permission="payroll:create">
        <Card>
          <CardHeader>
            <CardTitle>Assign compensation</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap items-end gap-3">
            <EmployeePicker
              id="payroll-employee-picker"
              value={pickedEmployee}
              onChange={setPickedEmployee}
            />
            <Button
              disabled={!pickedEmployee}
              onClick={() => {
                if (pickedEmployee) router.push(routes.payrollEmployeeSalary(pickedEmployee));
              }}
            >
              Open salary page
            </Button>
          </CardContent>
        </Card>
      </Can>

      <Input
        aria-label="Search the register"
        placeholder="Search by name or employee code"
        className="max-w-sm"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />

      <DataTable
        rows={rows}
        columns={columns}
        getRowId={(row) => row.id}
        isLoading={query.isLoading}
        error={query.error}
        emptyTitle="No compensation assigned yet"
        emptyDescription="Pick an employee above and assign their first salary structure."
      />
    </div>
  );
}
