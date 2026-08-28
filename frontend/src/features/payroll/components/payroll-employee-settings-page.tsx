'use client';

import * as React from 'react';

import { Can } from '@/components/common/can';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { EmployeePicker } from '@/features/workforce/components/employee-picker';
import {
  useEmployeePayrollSettings,
  useEmployeeSettingsList,
  useUpsertEmployeeSettings,
} from '@/features/payroll/hooks';
import {
  DAY_BASIS_LABELS,
  ELIGIBILITY_LABELS,
  ELIGIBILITY_REASON_LABELS,
  PAY_FREQUENCY_LABELS,
  type EmployeePayrollSettings,
  type EmployeeSettingsUpsertInput,
  type PayFrequency,
  type PayrollDayBasis,
  type PayrollEligibility,
  type PayrollEligibilityReason,
} from '@/features/payroll/types';

/**
 * Per-employee payroll settings and eligibility.
 *
 * A row exists only where somebody decided something: an employee with no row
 * is "not configured", never "eligible by default". Overrides follow the
 * NULL-means-follow rule — "Follow global" defers to the payroll
 * configuration rather than copying its value here. No salary figure appears
 * on this screen; compensation lives on the salary pages behind its own
 * permissions.
 */

const ELIGIBILITY_VARIANT: Record<PayrollEligibility, 'secondary' | 'outline' | 'destructive'> = {
  eligible: 'secondary',
  not_eligible: 'outline',
  suspended: 'destructive',
};

type TriState = '' | 'true' | 'false';

interface FormState {
  eligibility: PayrollEligibility;
  eligibility_reason: PayrollEligibilityReason | '';
  frequency_override: PayFrequency | '';
  proration_override: PayrollDayBasis | '';
  overtime_eligible: TriState;
  unpaid_leave_deduction: TriState;
  payroll_effective_date: string;
  notes: string;
}

const EMPTY_FORM: FormState = {
  eligibility: 'eligible',
  eligibility_reason: '',
  frequency_override: '',
  proration_override: '',
  overtime_eligible: '',
  unpaid_leave_deduction: '',
  payroll_effective_date: '',
  notes: '',
};

const triStateToPayload = (value: TriState): boolean | null =>
  value === '' ? null : value === 'true';

function SettingsEditor({ employeeId }: { employeeId: string }): React.JSX.Element {
  const query = useEmployeePayrollSettings(employeeId);
  const upsert = useUpsertEmployeeSettings();
  const [form, setForm] = React.useState<FormState>(EMPTY_FORM);
  const [loadedFor, setLoadedFor] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!query.data || loadedFor === employeeId) return;
    const settings = query.data.settings;
    setForm(
      settings === null
        ? EMPTY_FORM
        : {
            eligibility: settings.eligibility,
            eligibility_reason: settings.eligibility_reason ?? '',
            frequency_override: settings.frequency_override ?? '',
            proration_override: settings.proration_override ?? '',
            overtime_eligible:
              settings.overtime_eligible === null ? '' : String(settings.overtime_eligible) as TriState,
            unpaid_leave_deduction:
              settings.unpaid_leave_deduction === null
                ? ''
                : (String(settings.unpaid_leave_deduction) as TriState),
            payroll_effective_date: settings.payroll_effective_date ?? '',
            notes: settings.notes ?? '',
          },
    );
    setLoadedFor(employeeId);
  }, [query.data, employeeId, loadedFor]);

  if (query.isPending) return <p className="text-muted-foreground text-sm">Loading settings…</p>;
  if (query.error) return <p className="text-destructive text-sm">{query.error.message}</p>;

  const data = query.data;
  const selectClass = 'border-input bg-background h-9 w-full rounded-md border px-3 text-sm';

  const submit = (event: React.FormEvent): void => {
    event.preventDefault();
    const payload: EmployeeSettingsUpsertInput = {
      eligibility: form.eligibility,
      eligibility_reason: form.eligibility_reason || null,
      frequency_override: form.frequency_override || null,
      proration_override: form.proration_override || null,
      overtime_eligible: triStateToPayload(form.overtime_eligible),
      unpaid_leave_deduction: triStateToPayload(form.unpaid_leave_deduction),
      payroll_effective_date: form.payroll_effective_date || null,
      notes: form.notes || null,
    };
    upsert.mutate({ employeeId, payload });
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <span className="font-medium">
          {data.employee.full_name}
          <span className="text-muted-foreground ml-1 font-mono text-xs">
            {data.employee.employee_code}
          </span>
        </span>
        <Badge variant={data.has_active_compensation ? 'secondary' : 'outline'}>
          {data.has_active_compensation ? 'Compensation assigned' : 'No compensation yet'}
        </Badge>
        {data.settings === null ? <Badge variant="outline">Not configured</Badge> : null}
      </div>

      <form className="grid gap-4 sm:grid-cols-3" onSubmit={submit}>
        <div className="space-y-2">
          <Label htmlFor="settings-eligibility">Payroll eligibility</Label>
          <select
            id="settings-eligibility"
            className={selectClass}
            value={form.eligibility}
            onChange={(event) =>
              setForm({ ...form, eligibility: event.target.value as PayrollEligibility })
            }
          >
            {Object.entries(ELIGIBILITY_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="settings-reason">Reason</Label>
          <select
            id="settings-reason"
            className={selectClass}
            value={form.eligibility_reason}
            onChange={(event) =>
              setForm({
                ...form,
                eligibility_reason: event.target.value as FormState['eligibility_reason'],
              })
            }
          >
            <option value="">—</option>
            {Object.entries(ELIGIBILITY_REASON_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="settings-effective">Payroll effective date</Label>
          <Input
            id="settings-effective"
            type="date"
            value={form.payroll_effective_date}
            onChange={(event) => setForm({ ...form, payroll_effective_date: event.target.value })}
          />
        </div>
        <div className="space-y-2">
          <Label htmlFor="settings-frequency">Frequency override</Label>
          <select
            id="settings-frequency"
            className={selectClass}
            value={form.frequency_override}
            onChange={(event) =>
              setForm({ ...form, frequency_override: event.target.value as FormState['frequency_override'] })
            }
          >
            <option value="">Follow global</option>
            {Object.entries(PAY_FREQUENCY_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="settings-proration">Proration override</Label>
          <select
            id="settings-proration"
            className={selectClass}
            value={form.proration_override}
            onChange={(event) =>
              setForm({ ...form, proration_override: event.target.value as FormState['proration_override'] })
            }
          >
            <option value="">Follow global</option>
            {Object.entries(DAY_BASIS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="settings-overtime">Overtime eligible</Label>
          <select
            id="settings-overtime"
            className={selectClass}
            value={form.overtime_eligible}
            onChange={(event) =>
              setForm({ ...form, overtime_eligible: event.target.value as TriState })
            }
          >
            <option value="">Follow global</option>
            <option value="true">Yes</option>
            <option value="false">No</option>
          </select>
        </div>
        <div className="space-y-2">
          <Label htmlFor="settings-unpaid">Unpaid leave deduction</Label>
          <select
            id="settings-unpaid"
            className={selectClass}
            value={form.unpaid_leave_deduction}
            onChange={(event) =>
              setForm({ ...form, unpaid_leave_deduction: event.target.value as TriState })
            }
          >
            <option value="">Follow global</option>
            <option value="true">Deduct</option>
            <option value="false">Do not deduct</option>
          </select>
        </div>
        <div className="space-y-2 sm:col-span-2">
          <Label htmlFor="settings-notes">Notes</Label>
          <Textarea
            id="settings-notes"
            rows={2}
            value={form.notes}
            onChange={(event) => setForm({ ...form, notes: event.target.value })}
          />
        </div>
        <Can permission="payroll:employee_settings_update">
          <div className="flex items-end sm:col-span-3">
            <Button type="submit" isLoading={upsert.isPending}>
              Save settings
            </Button>
          </div>
        </Can>
      </form>
    </div>
  );
}

export function PayrollEmployeeSettingsPage(): React.JSX.Element {
  const [search, setSearch] = React.useState('');
  const [pickedEmployee, setPickedEmployee] = React.useState('');
  const list = useEmployeeSettingsList({ search: search || undefined });

  const columns: DataTableColumn<EmployeePayrollSettings>[] = [
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
    {
      id: 'eligibility',
      header: 'Eligibility',
      cell: (row) => (
        <Badge variant={ELIGIBILITY_VARIANT[row.eligibility]}>
          {ELIGIBILITY_LABELS[row.eligibility]}
        </Badge>
      ),
    },
    {
      id: 'reason',
      header: 'Reason',
      cell: (row) =>
        row.eligibility_reason ? ELIGIBILITY_REASON_LABELS[row.eligibility_reason] : '—',
    },
    {
      id: 'overrides',
      header: 'Overrides',
      cell: (row) => {
        const overrides = [
          row.frequency_override ? `Frequency: ${PAY_FREQUENCY_LABELS[row.frequency_override]}` : null,
          row.proration_override ? `Proration: ${DAY_BASIS_LABELS[row.proration_override]}` : null,
          row.overtime_eligible !== null ? `Overtime: ${row.overtime_eligible ? 'yes' : 'no'}` : null,
          row.unpaid_leave_deduction !== null
            ? `Unpaid leave: ${row.unpaid_leave_deduction ? 'deduct' : 'ignore'}`
            : null,
        ].filter(Boolean);
        return overrides.length ? overrides.join(' · ') : 'Follows global configuration';
      },
    },
    {
      id: 'effective',
      header: 'Effective',
      cell: (row) => row.payroll_effective_date ?? '—',
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) => (
        <Button size="sm" variant="outline" onClick={() => setPickedEmployee(row.employee.id)}>
          Open
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Employee Payroll Settings"
        description="Eligibility and per-employee overrides. An employee with no row is not configured — eligibility is never assumed. Salary itself lives on the compensation pages."
      />

      <Card>
        <CardHeader>
          <CardTitle>Configure an employee</CardTitle>
        </CardHeader>
        <CardContent className="space-y-6">
          <EmployeePicker
            id="payroll-settings-picker"
            value={pickedEmployee}
            onChange={setPickedEmployee}
          />
          {pickedEmployee ? <SettingsEditor employeeId={pickedEmployee} /> : null}
        </CardContent>
      </Card>

      <Input
        aria-label="Search configured employees"
        placeholder="Search by name or employee code"
        className="max-w-sm"
        value={search}
        onChange={(event) => setSearch(event.target.value)}
      />

      <DataTable
        rows={list.data?.items ?? []}
        columns={columns}
        getRowId={(row) => row.id}
        isLoading={list.isLoading}
        error={list.error}
        emptyTitle="No employees configured"
        emptyDescription="Pick an employee above to set their payroll eligibility and overrides."
      />
    </div>
  );
}
