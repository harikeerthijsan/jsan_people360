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
import { structureFormSchema, type StructureFormValues } from '@/features/payroll/schema';
import {
  useCreateStructure,
  useSalaryComponents,
  useSalaryStructures,
  useSetStructureStatus,
  useUpdateStructure,
} from '@/features/payroll/hooks';
import {
  PAY_FREQUENCY_LABELS,
  STRUCTURE_STATUS_LABELS,
  type PayFrequency,
  type SalaryStructure,
  type StructureStatus,
} from '@/features/payroll/types';

/**
 * Salary structures.
 *
 * Reusable templates: which components, paid how often, in what currency. A
 * structure is born a draft, must be activated before anybody can be assigned
 * from it, and editing it never touches compensation already assigned — every
 * assignment is a snapshot.
 */

const EMPTY_FORM: StructureFormValues = {
  name: '',
  description: null,
  pay_frequency: 'monthly',
  currency: 'INR',
  effective_from: null,
  effective_to: null,
  component_ids: [],
};

const STATUS_VARIANT: Record<StructureStatus, 'secondary' | 'outline' | 'default'> = {
  draft: 'outline',
  active: 'secondary',
  inactive: 'outline',
};

export function SalaryStructuresPage(): React.JSX.Element {
  const [search, setSearch] = React.useState('');
  const [statusFilter, setStatusFilter] = React.useState<StructureStatus | ''>('');
  const query = useSalaryStructures({
    search: search || undefined,
    status: statusFilter || undefined,
  });
  const components = useSalaryComponents();
  const create = useCreateStructure();
  const update = useUpdateStructure();
  const setStatus = useSetStructureStatus();

  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [form, setForm] = React.useState<StructureFormValues>(EMPTY_FORM);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [deactivating, setDeactivating] = React.useState<SalaryStructure | null>(null);

  const rows = query.data?.items ?? [];
  const editing = editingId !== null;

  const startEdit = (row: SalaryStructure): void => {
    setEditingId(row.id);
    setErrors({});
    setForm({
      name: row.name,
      description: row.description,
      pay_frequency: row.pay_frequency,
      currency: row.currency,
      effective_from: row.effective_from,
      effective_to: row.effective_to,
      component_ids: row.components.map((item) => item.component.id),
    });
  };

  const reset = (): void => {
    setEditingId(null);
    setForm(EMPTY_FORM);
    setErrors({});
  };

  const toggleComponent = (componentId: string): void => {
    setForm((current) => ({
      ...current,
      component_ids: current.component_ids.includes(componentId)
        ? current.component_ids.filter((id) => id !== componentId)
        : [...current.component_ids, componentId],
    }));
  };

  const submit = (event: React.FormEvent): void => {
    event.preventDefault();
    const parsed = structureFormSchema.safeParse(form);
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
    const payload = {
      name: values.name,
      description: values.description,
      pay_frequency: values.pay_frequency,
      currency: values.currency,
      effective_from: values.effective_from,
      effective_to: values.effective_to,
      components: values.component_ids.map((componentId) => ({ component_id: componentId })),
    };
    if (editingId !== null) {
      update.mutate({ structureId: editingId, payload }, { onSuccess: reset });
    } else {
      create.mutate(payload, { onSuccess: reset });
    }
  };

  const columns: DataTableColumn<SalaryStructure>[] = [
    {
      id: 'name',
      header: 'Structure',
      cell: (row) => (
        <div>
          <div className="font-medium">{row.name}</div>
          <div className="text-muted-foreground text-xs">
            {row.components.map((item) => item.component.code).join(' · ') || 'No components'}
          </div>
        </div>
      ),
    },
    {
      id: 'frequency',
      header: 'Frequency',
      cell: (row) => PAY_FREQUENCY_LABELS[row.pay_frequency],
    },
    { id: 'currency', header: 'Currency', cell: (row) => row.currency },
    {
      id: 'effective',
      header: 'Effective',
      cell: (row) =>
        row.effective_from ? `${row.effective_from} → ${row.effective_to ?? 'open'}` : '—',
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <Badge variant={STATUS_VARIANT[row.status]}>{STRUCTURE_STATUS_LABELS[row.status]}</Badge>
      ),
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) => (
        <Can permission="payroll:structure_manage">
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
                onClick={() => setStatus.mutate({ structureId: row.id, status: 'active' })}
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
        title="Salary Structures"
        description="Templates compensation is assigned from. A structure must be active before assignment, and edits never touch salaries already assigned."
      />

      <Can permission="payroll:structure_manage">
        <Card>
          <CardHeader>
            <CardTitle>{editing ? `Edit ${form.name || 'structure'}` : 'New structure'}</CardTitle>
          </CardHeader>
          <CardContent>
            <form className="grid gap-4 sm:grid-cols-3" onSubmit={submit}>
              <div className="space-y-2">
                <Label htmlFor="structure-name">Name</Label>
                <Input
                  id="structure-name"
                  value={form.name}
                  onChange={(event) => setForm({ ...form, name: event.target.value })}
                />
                {errors.name ? <p className="text-destructive text-xs">{errors.name}</p> : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="structure-frequency">Pay frequency</Label>
                <select
                  id="structure-frequency"
                  className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                  value={form.pay_frequency}
                  onChange={(event) =>
                    setForm({ ...form, pay_frequency: event.target.value as PayFrequency })
                  }
                >
                  {(Object.keys(PAY_FREQUENCY_LABELS) as PayFrequency[]).map((frequency) => (
                    <option key={frequency} value={frequency}>
                      {PAY_FREQUENCY_LABELS[frequency]}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="structure-currency">Currency</Label>
                <Input
                  id="structure-currency"
                  value={form.currency}
                  onChange={(event) => setForm({ ...form, currency: event.target.value.toUpperCase() })}
                />
                {errors.currency ? <p className="text-destructive text-xs">{errors.currency}</p> : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="structure-from">Effective from</Label>
                <Input
                  id="structure-from"
                  type="date"
                  value={form.effective_from ?? ''}
                  onChange={(event) => setForm({ ...form, effective_from: event.target.value || null })}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="structure-to">Effective to</Label>
                <Input
                  id="structure-to"
                  type="date"
                  value={form.effective_to ?? ''}
                  onChange={(event) => setForm({ ...form, effective_to: event.target.value || null })}
                />
                {errors.effective_to ? (
                  <p className="text-destructive text-xs">{errors.effective_to}</p>
                ) : null}
              </div>
              <div className="space-y-2 sm:col-span-3">
                <Label htmlFor="structure-description">Description</Label>
                <Textarea
                  id="structure-description"
                  rows={2}
                  value={form.description ?? ''}
                  onChange={(event) => setForm({ ...form, description: event.target.value || null })}
                />
              </div>
              <div className="space-y-2 sm:col-span-3">
                <Label>Components</Label>
                <div className="grid gap-2 sm:grid-cols-3">
                  {(components.data ?? []).map((component) => (
                    <label key={component.id} className="flex items-center gap-2 text-sm">
                      <input
                        type="checkbox"
                        checked={form.component_ids.includes(component.id)}
                        onChange={() => toggleComponent(component.id)}
                      />
                      <span>
                        {component.name}
                        <span className="text-muted-foreground ml-1 font-mono text-xs">
                          {component.code}
                        </span>
                      </span>
                    </label>
                  ))}
                </div>
                {errors.component_ids ? (
                  <p className="text-destructive text-xs">{errors.component_ids}</p>
                ) : null}
              </div>
              <div className="flex gap-2 sm:col-span-3">
                <Button type="submit" isLoading={create.isPending || update.isPending}>
                  {editing ? 'Save changes' : 'Create structure'}
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

      <div className="flex flex-wrap items-end gap-3">
        <Input
          aria-label="Search structures"
          placeholder="Search by name"
          className="max-w-xs"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
        <select
          aria-label="Status filter"
          className="border-input bg-background h-9 rounded-md border px-3 text-sm"
          value={statusFilter}
          onChange={(event) => setStatusFilter(event.target.value as StructureStatus | '')}
        >
          <option value="">All statuses</option>
          {(Object.keys(STRUCTURE_STATUS_LABELS) as StructureStatus[]).map((status) => (
            <option key={status} value={status}>
              {STRUCTURE_STATUS_LABELS[status]}
            </option>
          ))}
        </select>
      </div>

      <DataTable
        rows={rows}
        columns={columns}
        getRowId={(row) => row.id}
        isLoading={query.isLoading}
        error={query.error}
        emptyTitle="No salary structures"
        emptyDescription="Create a structure, add its components, then activate it to start assigning."
      />

      <ConfirmDialog
        open={deactivating !== null}
        onOpenChange={(open) => {
          if (!open) setDeactivating(null);
        }}
        title={`Deactivate ${deactivating?.name ?? 'structure'}?`}
        description="No new compensation can be assigned from it. Salaries already assigned are snapshots and are not affected."
        confirmLabel="Deactivate"
        isConfirming={setStatus.isPending}
        onConfirm={() => {
          if (deactivating === null) return;
          setStatus.mutate(
            { structureId: deactivating.id, status: 'inactive' },
            { onSuccess: () => setDeactivating(null) },
          );
        }}
      />
    </div>
  );
}
