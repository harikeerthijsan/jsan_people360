'use client';

import * as React from 'react';

import { Can } from '@/components/common/can';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { useLeaveTypes } from '@/features/workforce/hooks';
import { leaveRuleFormSchema, type LeaveRuleFormValues } from '@/features/payroll/schema';
import {
  useCreateLeaveRule,
  useLeaveRules,
  useSetLeaveRuleStatus,
  useUpdateLeaveRule,
} from '@/features/payroll/hooks';
import {
  DAY_BASIS_LABELS,
  LEAVE_TREATMENT_LABELS,
  type LeaveRule,
  type LeaveTreatment,
  type PayrollDayBasis,
} from '@/features/payroll/types';

/**
 * Payroll leave rules.
 *
 * How each existing leave type behaves in payroll — paid keeps the salary
 * whole, unpaid deducts against a day basis. The leave types themselves
 * belong to the workforce module and are referenced, never copied; the
 * "Paid leave type" column shows the leave module's own flag so a payroll
 * rule that contradicts it is a visible decision rather than an accident.
 */

const EMPTY_FORM: LeaveRuleFormValues = {
  leave_type_id: '',
  treatment: 'paid',
  deduction_basis: null,
  description: null,
};

export function PayrollRulesPage(): React.JSX.Element {
  const [includeInactive, setIncludeInactive] = React.useState(false);
  const rules = useLeaveRules(includeInactive);
  const leaveTypes = useLeaveTypes();
  const create = useCreateLeaveRule();
  const update = useUpdateLeaveRule();
  const setStatus = useSetLeaveRuleStatus();

  const [form, setForm] = React.useState<LeaveRuleFormValues>(EMPTY_FORM);
  const [errors, setErrors] = React.useState<Record<string, string>>({});

  const ruledTypeIds = new Set((rules.data ?? []).map((rule) => rule.leave_type_id));
  const unruledTypes = (leaveTypes.data ?? []).filter((type) => !ruledTypeIds.has(type.id));

  const pickType = (leaveTypeId: string): void => {
    const leaveType = (leaveTypes.data ?? []).find((type) => type.id === leaveTypeId);
    // Prefill from the leave module's own paid flag; the rule is still
    // payroll's explicit word, not a silent copy.
    const treatment: LeaveTreatment = leaveType && !leaveType.is_paid ? 'unpaid' : 'paid';
    setForm({
      leave_type_id: leaveTypeId,
      treatment,
      deduction_basis: treatment === 'unpaid' ? 'calendar_days' : null,
      description: null,
    });
  };

  const submit = (event: React.FormEvent): void => {
    event.preventDefault();
    const parsed = leaveRuleFormSchema.safeParse(form);
    if (!parsed.success) {
      const fieldErrors: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        fieldErrors[String(issue.path[0] ?? 'form')] = issue.message;
      }
      setErrors(fieldErrors);
      return;
    }
    setErrors({});
    create.mutate(parsed.data, { onSuccess: () => setForm(EMPTY_FORM) });
  };

  const columns: DataTableColumn<LeaveRule>[] = [
    {
      id: 'leave-type',
      header: 'Leave type',
      cell: (row) => (
        <div>
          <div className="font-medium">{row.leave_type_name}</div>
          <div className="text-muted-foreground font-mono text-xs">{row.leave_type_code}</div>
        </div>
      ),
    },
    {
      id: 'leave-flag',
      header: 'Paid leave type',
      cell: (row) => (row.leave_type_is_paid ? 'Yes' : 'No'),
    },
    {
      id: 'treatment',
      header: 'Payroll treatment',
      cell: (row) => (
        <select
          aria-label={`Treatment for ${row.leave_type_name}`}
          className="border-input bg-background h-8 rounded-md border px-2 text-sm"
          value={row.treatment}
          onChange={(event) => {
            const treatment = event.target.value as LeaveTreatment;
            update.mutate({
              ruleId: row.id,
              payload: {
                treatment,
                deduction_basis:
                  treatment === 'unpaid' ? (row.deduction_basis ?? 'calendar_days') : null,
              },
            });
          }}
        >
          {Object.entries(LEAVE_TREATMENT_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      ),
    },
    {
      id: 'basis',
      header: 'Deduction basis',
      cell: (row) =>
        row.treatment === 'unpaid' ? (
          <select
            aria-label={`Deduction basis for ${row.leave_type_name}`}
            className="border-input bg-background h-8 rounded-md border px-2 text-sm"
            value={row.deduction_basis ?? 'calendar_days'}
            onChange={(event) =>
              update.mutate({
                ruleId: row.id,
                payload: { deduction_basis: event.target.value as PayrollDayBasis },
              })
            }
          >
            {Object.entries(DAY_BASIS_LABELS).map(([value, label]) => (
              <option key={value} value={value}>
                {label}
              </option>
            ))}
          </select>
        ) : (
          '—'
        ),
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
        <Can permission="payroll:rule_manage">
          <Button
            size="sm"
            variant="ghost"
            onClick={() =>
              setStatus.mutate({
                ruleId: row.id,
                status: row.status === 'active' ? 'inactive' : 'active',
              })
            }
          >
            {row.status === 'active' ? 'Deactivate' : 'Activate'}
          </Button>
        </Can>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Payroll Rules"
        description="How each leave type behaves in payroll. Configuration only — the deduction itself belongs to a later phase. Component-level pay flags live on the Salary Components screen."
      />

      <Can permission="payroll:rule_manage">
        <Card>
          <CardHeader>
            <CardTitle>Add a rule</CardTitle>
          </CardHeader>
          <CardContent>
            <form className="grid gap-4 sm:grid-cols-4" onSubmit={submit}>
              <div className="space-y-2">
                <Label htmlFor="rule-leave-type">Leave type</Label>
                <select
                  id="rule-leave-type"
                  className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                  value={form.leave_type_id}
                  onChange={(event) => pickType(event.target.value)}
                >
                  <option value="">
                    {leaveTypes.isPending ? 'Loading leave types…' : 'Choose a leave type'}
                  </option>
                  {unruledTypes.map((type) => (
                    <option key={type.id} value={type.id}>
                      {type.name}
                    </option>
                  ))}
                </select>
                {errors.leave_type_id ? (
                  <p className="text-destructive text-xs">{errors.leave_type_id}</p>
                ) : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="rule-treatment">Treatment</Label>
                <select
                  id="rule-treatment"
                  className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                  value={form.treatment}
                  onChange={(event) => {
                    const treatment = event.target.value as LeaveTreatment;
                    setForm({
                      ...form,
                      treatment,
                      deduction_basis:
                        treatment === 'unpaid' ? (form.deduction_basis ?? 'calendar_days') : null,
                    });
                  }}
                >
                  {Object.entries(LEAVE_TREATMENT_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              {form.treatment === 'unpaid' ? (
                <div className="space-y-2">
                  <Label htmlFor="rule-basis">Deduction basis</Label>
                  <select
                    id="rule-basis"
                    className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                    value={form.deduction_basis ?? 'calendar_days'}
                    onChange={(event) =>
                      setForm({ ...form, deduction_basis: event.target.value as PayrollDayBasis })
                    }
                  >
                    {Object.entries(DAY_BASIS_LABELS).map(([value, label]) => (
                      <option key={value} value={value}>
                        {label}
                      </option>
                    ))}
                  </select>
                  {errors.deduction_basis ? (
                    <p className="text-destructive text-xs">{errors.deduction_basis}</p>
                  ) : null}
                </div>
              ) : null}
              <div className="flex items-end">
                <Button type="submit" disabled={!form.leave_type_id} isLoading={create.isPending}>
                  Add rule
                </Button>
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
        Show inactive rules
      </label>

      <DataTable
        rows={rules.data ?? []}
        columns={columns}
        getRowId={(row) => row.id}
        isLoading={rules.isLoading}
        error={rules.error}
        emptyTitle="No payroll leave rules"
        emptyDescription="Add a rule for each leave type so a later payroll phase knows which leaves deduct pay."
      />
    </div>
  );
}
