'use client';

import * as React from 'react';

import { Can, usePermitted } from '@/components/common/can';
import { ConfirmDialog } from '@/components/common/modal';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  assignmentFormSchema,
  revisionFormSchema,
} from '@/features/payroll/schema';
import {
  useAssignCompensation,
  useEmployeeCompensation,
  useEmployeeSalaryHistory,
  useReviseSalary,
  useSalaryStructures,
} from '@/features/payroll/hooks';
import {
  describeComponentValue,
  type SalaryStructure,
} from '@/features/payroll/types';
import {
  ComponentBreakdown,
  CompensationRecordsTable,
  CompensationSummary,
  SalaryHistoryTable,
} from './compensation-view';

/**
 * One employee's salary page: current compensation, every past period, the
 * change history — and, for the permissions that allow it, the assignment and
 * revision forms.
 *
 * A revision never edits the current record. The server ends it the day
 * before the new period starts and opens a new one, which is why the form
 * below asks for a reason: the history's Reason column must never be blank
 * for a change to somebody's pay.
 */

interface ComponentValueRow {
  component_id: string;
  label: string;
  hint: string;
  value: string;
}

interface MoneyForm {
  salary_structure_id: string;
  currency: string;
  annual_ctc: string;
  annual_gross: string;
  monthly_gross: string;
  basic_salary: string;
  effective_from: string;
  reason: string;
}

const EMPTY_MONEY: MoneyForm = {
  salary_structure_id: '',
  currency: 'INR',
  annual_ctc: '',
  annual_gross: '',
  monthly_gross: '',
  basic_salary: '',
  effective_from: '',
  reason: '',
};

function CompensationForm({
  employeeId,
  mode,
  employeeName,
}: {
  employeeId: string;
  mode: 'assign' | 'revise';
  employeeName: string;
}): React.JSX.Element {
  const structures = useSalaryStructures({ status: 'active', page_size: 100 });
  const assign = useAssignCompensation();
  const revise = useReviseSalary();

  const [form, setForm] = React.useState<MoneyForm>(EMPTY_MONEY);
  const [componentRows, setComponentRows] = React.useState<ComponentValueRow[]>([]);
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [confirming, setConfirming] = React.useState(false);

  const activeStructures = structures.data?.items ?? [];
  const mutation = mode === 'assign' ? assign : revise;

  const pickStructure = (structure: SalaryStructure | undefined): void => {
    setForm((current) => ({
      ...current,
      salary_structure_id: structure?.id ?? '',
      currency: structure?.currency ?? current.currency,
    }));
    setComponentRows(
      (structure?.components ?? []).map((item) => ({
        component_id: item.component.id,
        label: `${item.component.name} (${item.component.code})`,
        hint:
          item.component.calculation_type === 'percentage'
            ? `Percentage, e.g. ${describeComponentValue(item.component)}`
            : 'Fixed amount',
        value: item.default_value ?? item.component.value,
      })),
    );
  };

  const validate = (): boolean => {
    const payload = {
      ...form,
      reason: mode === 'assign' ? form.reason || null : form.reason,
      components: componentRows.map((row) => ({ component_id: row.component_id, value: row.value })),
    };
    const schema = mode === 'assign' ? assignmentFormSchema : revisionFormSchema;
    const parsed = schema.safeParse(payload);
    if (!parsed.success) {
      const fieldErrors: Record<string, string> = {};
      for (const issue of parsed.error.issues) {
        fieldErrors[String(issue.path[0] ?? 'form')] = issue.message;
      }
      setErrors(fieldErrors);
      return false;
    }
    setErrors({});
    return true;
  };

  const submit = (): void => {
    const components = componentRows.map((row) => ({
      component_id: row.component_id,
      value: row.value,
    }));
    if (mode === 'assign') {
      assign.mutate(
        {
          employeeId,
          payload: { ...form, reason: form.reason || null, components },
        },
        { onSuccess: () => setConfirming(false) },
      );
    } else {
      revise.mutate(
        { employeeId, payload: { ...form, components } },
        { onSuccess: () => setConfirming(false) },
      );
    }
  };

  const moneyField = (
    id: keyof MoneyForm,
    label: string,
  ): React.JSX.Element => (
    <div className="space-y-2">
      <Label htmlFor={`salary-${id}`}>{label}</Label>
      <Input
        id={`salary-${id}`}
        inputMode="decimal"
        value={form[id]}
        onChange={(event) => setForm({ ...form, [id]: event.target.value })}
      />
      {errors[id] ? <p className="text-destructive text-xs">{errors[id]}</p> : null}
    </div>
  );

  return (
    <Card>
      <CardHeader>
        <CardTitle>{mode === 'assign' ? 'Assign compensation' : 'Revise salary'}</CardTitle>
      </CardHeader>
      <CardContent>
        <form
          className="grid gap-4 sm:grid-cols-3"
          onSubmit={(event) => {
            event.preventDefault();
            if (validate()) setConfirming(true);
          }}
        >
          <div className="space-y-2">
            <Label htmlFor="salary-structure">Salary structure</Label>
            <select
              id="salary-structure"
              className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
              value={form.salary_structure_id}
              onChange={(event) =>
                pickStructure(activeStructures.find((item) => item.id === event.target.value))
              }
            >
              <option value="">
                {structures.isPending ? 'Loading structures…' : 'Choose a structure'}
              </option>
              {activeStructures.map((structure) => (
                <option key={structure.id} value={structure.id}>
                  {structure.name}
                </option>
              ))}
            </select>
            {errors.salary_structure_id ? (
              <p className="text-destructive text-xs">{errors.salary_structure_id}</p>
            ) : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="salary-currency">Currency</Label>
            <Input
              id="salary-currency"
              value={form.currency}
              onChange={(event) => setForm({ ...form, currency: event.target.value.toUpperCase() })}
            />
            {errors.currency ? <p className="text-destructive text-xs">{errors.currency}</p> : null}
          </div>
          <div className="space-y-2">
            <Label htmlFor="salary-effective_from">Effective from</Label>
            <Input
              id="salary-effective_from"
              type="date"
              value={form.effective_from}
              onChange={(event) => setForm({ ...form, effective_from: event.target.value })}
            />
            {errors.effective_from ? (
              <p className="text-destructive text-xs">{errors.effective_from}</p>
            ) : null}
          </div>
          {moneyField('annual_ctc', 'Annual CTC')}
          {moneyField('annual_gross', 'Annual gross')}
          {moneyField('monthly_gross', 'Monthly gross')}
          {moneyField('basic_salary', 'Basic salary')}

          {componentRows.length > 0 ? (
            <div className="space-y-2 sm:col-span-3">
              <Label>Component values</Label>
              <div className="grid gap-3 sm:grid-cols-2">
                {componentRows.map((row, index) => (
                  <div key={row.component_id} className="space-y-1">
                    <Label htmlFor={`component-${row.component_id}`} className="text-xs font-normal">
                      {row.label}
                      <span className="text-muted-foreground ml-1">· {row.hint}</span>
                    </Label>
                    <Input
                      id={`component-${row.component_id}`}
                      inputMode="decimal"
                      value={row.value}
                      onChange={(event) =>
                        setComponentRows((current) =>
                          current.map((item, itemIndex) =>
                            itemIndex === index ? { ...item, value: event.target.value } : item,
                          ),
                        )
                      }
                    />
                  </div>
                ))}
              </div>
              {errors.components ? (
                <p className="text-destructive text-xs">{errors.components}</p>
              ) : null}
            </div>
          ) : null}

          <div className="space-y-2 sm:col-span-3">
            <Label htmlFor="salary-reason">
              Reason{mode === 'assign' ? ' (optional)' : ''}
            </Label>
            <Textarea
              id="salary-reason"
              rows={2}
              value={form.reason}
              onChange={(event) => setForm({ ...form, reason: event.target.value })}
            />
            {errors.reason ? <p className="text-destructive text-xs">{errors.reason}</p> : null}
          </div>

          <div className="sm:col-span-3">
            <Button type="submit" disabled={!form.salary_structure_id}>
              {mode === 'assign' ? 'Assign compensation' : 'Revise salary'}
            </Button>
          </div>
        </form>
      </CardContent>

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={mode === 'assign' ? `Assign compensation to ${employeeName}?` : `Revise ${employeeName}'s salary?`}
        description={
          mode === 'assign'
            ? `Annual CTC ${form.annual_ctc} ${form.currency}, effective ${form.effective_from}.`
            : `The current record will be ended the day before ${form.effective_from} and a new one opened at ${form.annual_ctc} ${form.currency}. Both stay in the history permanently.`
        }
        confirmLabel={mode === 'assign' ? 'Assign' : 'Revise'}
        isConfirming={mutation.isPending}
        onConfirm={submit}
      />
    </Card>
  );
}

export function EmployeeSalaryPage({ employeeId }: { employeeId: string }): React.JSX.Element {
  const query = useEmployeeCompensation(employeeId);
  const canReadHistory = usePermitted({ anyOf: ['payroll:history_view', 'payroll:team_view'] });
  const history = useEmployeeSalaryHistory(employeeId, canReadHistory);

  if (query.isPending) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} />;

  const data = query.data;
  const title = `${data.employee.full_name} · ${data.employee.employee_code}`;

  return (
    <div className="space-y-6">
      <PageHeader
        title={title}
        description="Compensation record, effective periods and salary history. Nothing here is ever overwritten — a change ends one period and opens another."
      />

      {data.current ? (
        <>
          <CompensationSummary record={data.current} />
          <ComponentBreakdown record={data.current} />
        </>
      ) : null}

      {data.current === null ? (
        <Can permission="payroll:create">
          <CompensationForm
            employeeId={employeeId}
            mode="assign"
            employeeName={data.employee.full_name}
          />
        </Can>
      ) : (
        <Can permission="payroll:update">
          <CompensationForm
            employeeId={employeeId}
            mode="revise"
            employeeName={data.employee.full_name}
          />
        </Can>
      )}

      <Card>
        <CardHeader>
          <CardTitle>Compensation periods</CardTitle>
        </CardHeader>
        <CardContent>
          <CompensationRecordsTable
            records={data.records}
            isLoading={false}
            error={null}
          />
        </CardContent>
      </Card>

      {canReadHistory ? (
        <Card>
          <CardHeader>
            <CardTitle>Salary history</CardTitle>
          </CardHeader>
          <CardContent>
            <SalaryHistoryTable
              entries={history.data ?? []}
              isLoading={history.isLoading}
              error={history.error}
            />
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
