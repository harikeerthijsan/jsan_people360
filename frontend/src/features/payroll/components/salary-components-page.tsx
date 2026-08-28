'use client';

import * as React from 'react';

import { Can } from '@/components/common/can';
import { ConfirmDialog } from '@/components/common/modal';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { componentFormSchema, type ComponentFormValues } from '@/features/payroll/schema';
import {
  useCreateComponent,
  useSalaryComponents,
  useSetComponentStatus,
  useUpdateComponent,
} from '@/features/payroll/hooks';
import {
  CALCULATION_TYPE_LABELS,
  COMPONENT_TYPE_LABELS,
  describeComponentValue,
  type CalculationType,
  type ComponentType,
  type PercentageBasis,
  type SalaryComponent,
} from '@/features/payroll/types';

/**
 * Salary components.
 *
 * The configurable earning and deduction masters — Basic, HRA, PF, Tax — that
 * structures are built from. Editing one changes *future* assignments only:
 * every compensation record snapshots its component values at assignment, so
 * nothing here can rewrite what somebody was already promised.
 */

const EMPTY_FORM: ComponentFormValues = {
  name: '',
  code: '',
  component_type: 'earning',
  calculation_type: 'fixed',
  value: '0',
  percentage_basis: null,
  description: null,
  proration_allowed: true,
  attendance_impact: false,
  leave_impact: false,
  overtime_eligible: false,
  is_taxable: true,
};

const FLAG_LABELS: Record<
  'proration_allowed' | 'attendance_impact' | 'leave_impact' | 'overtime_eligible' | 'is_taxable',
  string
> = {
  proration_allowed: 'Proration allowed',
  attendance_impact: 'Attendance impact',
  leave_impact: 'Leave impact',
  overtime_eligible: 'Overtime eligible',
  is_taxable: 'Taxable',
};

export function SalaryComponentsPage(): React.JSX.Element {
  const [includeInactive, setIncludeInactive] = React.useState(false);
  const query = useSalaryComponents(includeInactive);
  const create = useCreateComponent();
  const update = useUpdateComponent();
  const setStatus = useSetComponentStatus();

  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [form, setForm] = React.useState<ComponentFormValues>(EMPTY_FORM);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [deactivating, setDeactivating] = React.useState<SalaryComponent | null>(null);

  const rows = query.data ?? [];
  const editing = editingId !== null;

  const startEdit = (row: SalaryComponent): void => {
    setEditingId(row.id);
    setErrors({});
    setForm({
      name: row.name,
      code: row.code,
      component_type: row.component_type,
      calculation_type: row.calculation_type,
      value: row.value,
      percentage_basis: row.percentage_basis,
      description: row.description,
      proration_allowed: row.proration_allowed,
      attendance_impact: row.attendance_impact,
      leave_impact: row.leave_impact,
      overtime_eligible: row.overtime_eligible,
      is_taxable: row.is_taxable,
    });
  };

  const reset = (): void => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setErrors({});
  };

  const submit = (event: React.FormEvent): void => {
    event.preventDefault();
    const parsed = componentFormSchema.safeParse(form);
    if (!parsed.success) {
      const fieldErrors: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        fieldErrors[String(issue.path[0] ?? 'form')] = issue.message;
      }
      setErrors(fieldErrors);
      return;
    }
    setErrors({});
    const values = parsed.data;
    if (editingId !== null) {
      update.mutate(
        {
          componentId: editingId,
          payload: {
            name: values.name,
            calculation_type: values.calculation_type,
            value: values.value,
            percentage_basis: values.calculation_type === 'percentage' ? values.percentage_basis : null,
            description: values.description,
            proration_allowed: values.proration_allowed,
            attendance_impact: values.attendance_impact,
            leave_impact: values.leave_impact,
            overtime_eligible: values.overtime_eligible,
            is_taxable: values.is_taxable,
          },
        },
        { onSuccess: reset },
      );
    } else {
      create.mutate(
        {
          ...values,
          percentage_basis: values.calculation_type === 'percentage' ? values.percentage_basis : null,
        },
        { onSuccess: reset },
      );
    }
  };

  const columns: DataTableColumn<SalaryComponent>[] = [
    {
      id: 'name',
      header: 'Component',
      cell: (row) => (
        <div>
          <div className="font-medium">{row.name}</div>
          <div className="text-muted-foreground font-mono text-xs">{row.code}</div>
        </div>
      ),
    },
    {
      id: 'type',
      header: 'Type',
      cell: (row) => (
        <Badge variant={row.component_type === 'earning' ? 'secondary' : 'outline'}>
          {COMPONENT_TYPE_LABELS[row.component_type]}
        </Badge>
      ),
    },
    {
      id: 'calculation',
      header: 'Default value',
      cell: (row) => (
        <span>
          {describeComponentValue(row)}
          <span className="text-muted-foreground ml-1 text-xs">
            ({CALCULATION_TYPE_LABELS[row.calculation_type]})
          </span>
        </span>
      ),
    },
    {
      id: 'behaviour',
      header: 'Pay behaviour',
      cell: (row) => {
        const flags = [
          row.proration_allowed ? 'Prorates' : null,
          row.attendance_impact ? 'Attendance' : null,
          row.leave_impact ? 'Leave' : null,
          row.overtime_eligible ? 'Overtime' : null,
          row.is_taxable ? 'Taxable' : null,
        ].filter(Boolean);
        return (
          <span className="text-muted-foreground text-xs">
            {flags.length ? flags.join(' · ') : '—'}
          </span>
        );
      },
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
        <Can permission="payroll:component_manage">
          <div className="flex justify-end gap-2">
            <Button size="sm" variant="outline" onClick={() => startEdit(row)}>
              Edit
            </Button>
            {row.status === 'active' ? (
              <Button size="sm" variant="ghost" onClick={() => setDeactivating(row)}>
                Deactivate
              </Button>
            ) : (
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setStatus.mutate({ componentId: row.id, status: 'active' })}
              >
                Activate
              </Button>
            )}
          </div>
        </Can>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Salary Components"
        description="The building blocks structures are made of. Edits apply to future assignments only — existing compensation keeps its snapshot."
      />

      <Can permission="payroll:component_manage">
        <Card>
          <CardHeader>
            <CardTitle>{editing ? `Edit ${form.name || 'component'}` : 'New component'}</CardTitle>
          </CardHeader>
          <CardContent>
            <form className="grid gap-4 sm:grid-cols-3" onSubmit={submit}>
              <div className="space-y-2">
                <Label htmlFor="component-name">Name</Label>
                <Input
                  id="component-name"
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                />
                {errors.name ? <p className="text-destructive text-xs">{errors.name}</p> : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="component-code">Code</Label>
                <Input
                  id="component-code"
                  value={form.code}
                  disabled={editing}
                  onChange={(event) => setForm({ ...form, code: event.target.value.toUpperCase() })}
                />
                {errors.code ? <p className="text-destructive text-xs">{errors.code}</p> : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="component-type">Type</Label>
                <select
                  id="component-type"
                  className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                  value={form.component_type}
                  disabled={editing}
                  onChange={(event) =>
                    setForm({ ...form, component_type: event.target.value as ComponentType })
                  }
                >
                  <option value="earning">Earning</option>
                  <option value="deduction">Deduction</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="component-calculation">Calculation</Label>
                <select
                  id="component-calculation"
                  className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                  value={form.calculation_type}
                  onChange={(event) => {
                    const calculation = event.target.value as CalculationType;
                    setForm({
                      ...form,
                      calculation_type: calculation,
                      percentage_basis:
                        calculation === 'percentage' ? (form.percentage_basis ?? 'basic') : null,
                    });
                  }}
                >
                  <option value="fixed">Fixed amount</option>
                  <option value="percentage">Percentage</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="component-value">
                  {form.calculation_type === 'percentage' ? 'Percentage (0–100)' : 'Default amount'}
                </Label>
                <Input
                  id="component-value"
                  inputMode="decimal"
                  value={form.value}
                  onChange={(event) => setForm({ ...form, value: event.target.value })}
                />
                {errors.value ? <p className="text-destructive text-xs">{errors.value}</p> : null}
              </div>
              {form.calculation_type === 'percentage' ? (
                <div className="space-y-2">
                  <Label htmlFor="component-basis">Percentage of</Label>
                  <select
                    id="component-basis"
                    className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                    value={form.percentage_basis ?? 'basic'}
                    onChange={(event) =>
                      setForm({ ...form, percentage_basis: event.target.value as PercentageBasis })
                    }
                  >
                    <option value="basic">Basic</option>
                    <option value="gross">Gross</option>
                  </select>
                  {errors.percentage_basis ? (
                    <p className="text-destructive text-xs">{errors.percentage_basis}</p>
                  ) : null}
                </div>
              ) : null}
              <div className="space-y-2 sm:col-span-3">
                <Label>Pay behaviour</Label>
                <p className="text-muted-foreground text-xs">
                  Read by later payroll phases; nothing is calculated against these yet, and
                  compensation already assigned keeps its snapshot.
                </p>
                <div className="flex flex-wrap gap-4">
                  {(Object.keys(FLAG_LABELS) as (keyof typeof FLAG_LABELS)[]).map((flag) => (
                    <label key={flag} className="flex items-center gap-1.5 text-sm">
                      <input
                        type="checkbox"
                        checked={form[flag]}
                        onChange={(event) => setForm({ ...form, [flag]: event.target.checked })}
                      />
                      {FLAG_LABELS[flag]}
                    </label>
                  ))}
                </div>
              </div>
              <div className="space-y-2 sm:col-span-3">
                <Label htmlFor="component-description">Description</Label>
                <Textarea
                  id="component-description"
                  rows={2}
                  value={form.description ?? ''}
                  onChange={(event) => setForm({ ...form, description: event.target.value || null })}
                />
              </div>
              <div className="flex gap-2 sm:col-span-3">
                <Button type="submit" isLoading={create.isPending || update.isPending}>
                  {editing ? 'Save changes' : 'Create component'}
                </Button>
                {editing ? (
                  <Button type="button" variant="outline" onClick={reset}>
                    Cancel
                  </Button>
                ) : null}
              </div>
            </form>
          </CardContent>
        </Card>
      </Can>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={includeInactive}
          onChange={(event) => setIncludeInactive(event.target.checked)}
        />
        Show inactive components
      </label>

      <DataTable
        rows={rows}
        columns={columns}
        getRowId={(row) => row.id}
        isLoading={query.isLoading}
        error={query.error}
        emptyTitle="No components yet"
        emptyDescription="Create the earnings and deductions your salary structures will be made of."
      />

      <ConfirmDialog
        open={deactivating !== null}
        onOpenChange={(open) => {
          if (!open) setDeactivating(null);
        }}
        title={`Deactivate ${deactivating?.name ?? 'component'}?`}
        description="It disappears from new structures and assignments. Compensation that already uses it is a snapshot and keeps resolving."
        confirmLabel="Deactivate"
        isConfirming={setStatus.isPending}
        onConfirm={() => {
          if (deactivating === null) return;
          setStatus.mutate(
            { componentId: deactivating.id, status: 'inactive' },
            { onSuccess: () => setDeactivating(null) },
          );
        }}
      />
    </div>
  );
}
