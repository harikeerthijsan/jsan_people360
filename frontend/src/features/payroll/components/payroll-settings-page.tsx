'use client';

import { useQuery } from '@tanstack/react-query';
import * as React from 'react';

import { Can } from '@/components/common/can';
import { ConfirmDialog } from '@/components/common/modal';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { workforceApi } from '@/features/workforce/api';
import { payrollConfigFormSchema, type PayrollConfigFormValues } from '@/features/payroll/schema';
import {
  usePayrollConfig,
  usePayrollConfigHistory,
  useUpdatePayrollConfig,
} from '@/features/payroll/hooks';
import {
  DAY_BASIS_LABELS,
  PAY_FREQUENCY_LABELS,
  ROUNDING_RULE_LABELS,
  UNPAID_LEAVE_TREATMENT_LABELS,
  WEEKDAY_LABELS,
  WORKING_DAYS_RULE_LABELS,
  type PayrollConfig,
  type PayrollConfigHistoryEntry,
} from '@/features/payroll/types';

/**
 * The payroll rulebook.
 *
 * Everything a future payroll run will read and nothing it computes yet.
 * Saving requires a reason and an effective date, and the server writes one
 * history row per field that actually changed — the table at the bottom is
 * that record, and it has no edit surface anywhere.
 */

type FormState = Omit<PayrollConfigFormValues, 'reason' | 'effective_from'>;

function fromConfig(config: PayrollConfig): FormState {
  return {
    pay_frequency: config.pay_frequency,
    period_start_day: config.period_start_day,
    period_end_day: config.period_end_day,
    pay_day: config.pay_day,
    cutoff_day: config.cutoff_day,
    currency: config.currency,
    working_days_rule: config.working_days_rule,
    weekly_off_days: config.weekly_off_days,
    proration_basis: config.proration_basis,
    unpaid_leave_treatment: config.unpaid_leave_treatment,
    unpaid_leave_basis: config.unpaid_leave_basis,
    overtime_enabled: config.overtime_enabled,
    overtime_basis: config.overtime_basis,
    overtime_multiplier: config.overtime_multiplier,
    overtime_min_hours: config.overtime_min_hours,
    overtime_max_hours: config.overtime_max_hours,
    overtime_approval_required: config.overtime_approval_required,
    standard_daily_hours: config.standard_daily_hours,
    deduct_absence: config.deduct_absence,
    deduct_late_arrival: config.deduct_late_arrival,
    deduct_early_exit: config.deduct_early_exit,
    require_approved_attendance: config.require_approved_attendance,
    rounding_rule: config.rounding_rule,
    rounding_precision: config.rounding_precision,
  };
}

export function PayrollSettingsPage(): React.JSX.Element {
  const query = usePayrollConfig();
  const history = usePayrollConfigHistory();
  const update = useUpdatePayrollConfig();
  const calendars = useQuery({
    queryKey: ['workforce', 'holiday-calendars', 'payroll-settings'],
    queryFn: () => workforceApi.holidayCalendars({}),
    staleTime: 5 * 60_000,
  });

  const [form, setForm] = React.useState<FormState | null>(null);
  const [holidayCalendarId, setHolidayCalendarId] = React.useState<string>('');
  const [reason, setReason] = React.useState('');
  const [effectiveFrom, setEffectiveFrom] = React.useState('');
  const [errors, setErrors] = React.useState<Record<string, string>>({});
  const [confirming, setConfirming] = React.useState(false);

  React.useEffect(() => {
    if (query.data && form === null) {
      setForm(fromConfig(query.data));
      setHolidayCalendarId(query.data.holiday_calendar_id ?? '');
    }
  }, [query.data, form]);

  if (query.isPending || form === null) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} />;

  const set = <K extends keyof FormState>(key: K, value: FormState[K]): void => {
    setForm((current) => (current === null ? current : { ...current, [key]: value }));
  };

  const validate = (): boolean => {
    const parsed = payrollConfigFormSchema.safeParse({
      ...form,
      reason,
      effective_from: effectiveFrom,
    });
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
    update.mutate(
      {
        ...form,
        holiday_calendar_id: holidayCalendarId || undefined,
        clear_holiday_calendar: holidayCalendarId === '' && query.data?.holiday_calendar_id !== null,
        clear_overtime_max_hours: form.overtime_max_hours === null,
        overtime_max_hours: form.overtime_max_hours ?? undefined,
        rounding_precision: form.rounding_rule === 'custom' ? form.rounding_precision : undefined,
        reason,
        effective_from: effectiveFrom,
      },
      {
        onSuccess: () => {
          setConfirming(false);
          setReason('');
        },
      },
    );
  };

  const numberField = (
    key: 'period_start_day' | 'period_end_day' | 'pay_day' | 'cutoff_day',
    label: string,
    max: number,
  ): React.JSX.Element => (
    <div className="space-y-2">
      <Label htmlFor={`config-${key}`}>{label}</Label>
      <Input
        id={`config-${key}`}
        type="number"
        min={1}
        max={max}
        value={form[key]}
        onChange={(event) => set(key, Number(event.target.value))}
      />
      {errors[key] ? <p className="text-destructive text-xs">{errors[key]}</p> : null}
    </div>
  );

  const checkbox = (
    key:
      | 'overtime_enabled'
      | 'overtime_approval_required'
      | 'deduct_absence'
      | 'deduct_late_arrival'
      | 'deduct_early_exit'
      | 'require_approved_attendance',
    label: string,
  ): React.JSX.Element => (
    <label className="flex items-center gap-2 text-sm">
      <input type="checkbox" checked={form[key]} onChange={(event) => set(key, event.target.checked)} />
      {label}
    </label>
  );

  const selectClass = 'border-input bg-background h-9 w-full rounded-md border px-3 text-sm';

  const historyColumns: DataTableColumn<PayrollConfigHistoryEntry>[] = [
    { id: 'field', header: 'Setting', cell: (row) => <span className="font-mono text-xs">{row.field}</span> },
    { id: 'previous', header: 'Previous', cell: (row) => row.previous_value ?? '—' },
    { id: 'new', header: 'New', cell: (row) => row.new_value ?? '—' },
    { id: 'effective', header: 'Effective', cell: (row) => row.effective_from },
    { id: 'reason', header: 'Reason', cell: (row) => row.reason },
    { id: 'by', header: 'Changed by', cell: (row) => row.changed_by_name ?? '—' },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Payroll Settings"
        description="The rulebook a future payroll run will read. Nothing here recalculates existing salaries, and every change is recorded with its reason."
      />

      <form
        className="space-y-6"
        onSubmit={(event) => {
          event.preventDefault();
          if (validate()) setConfirming(true);
        }}
      >
        <Card>
          <CardHeader>
            <CardTitle>Schedule</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="config-frequency">Payroll frequency</Label>
              <select
                id="config-frequency"
                className={selectClass}
                value={form.pay_frequency}
                onChange={(event) => set('pay_frequency', event.target.value as FormState['pay_frequency'])}
              >
                {Object.entries(PAY_FREQUENCY_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="config-currency">Currency</Label>
              <Input
                id="config-currency"
                value={form.currency}
                onChange={(event) => set('currency', event.target.value.toUpperCase())}
              />
              {errors.currency ? <p className="text-destructive text-xs">{errors.currency}</p> : null}
            </div>
            {numberField('period_start_day', 'Period start day', 28)}
            {numberField('period_end_day', 'Period end day', 31)}
            {numberField('pay_day', 'Pay day', 31)}
            {numberField('cutoff_day', 'Cutoff day', 28)}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Working days & holidays</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="config-working-days">Working days rule</Label>
                <select
                  id="config-working-days"
                  className={selectClass}
                  value={form.working_days_rule}
                  onChange={(event) =>
                    set('working_days_rule', event.target.value as FormState['working_days_rule'])
                  }
                >
                  {Object.entries(WORKING_DAYS_RULE_LABELS).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="config-holiday-calendar">Holiday calendar</Label>
                <select
                  id="config-holiday-calendar"
                  className={selectClass}
                  value={holidayCalendarId}
                  onChange={(event) => setHolidayCalendarId(event.target.value)}
                >
                  <option value="">None — no public holidays configured</option>
                  {(calendars.data ?? []).map((calendar) => (
                    <option key={calendar.id} value={calendar.id}>
                      {calendar.name}
                    </option>
                  ))}
                </select>
                <p className="text-muted-foreground text-xs">
                  Reuses the existing workforce holiday calendars — payroll has no holiday list of
                  its own.
                </p>
              </div>
            </div>
            <div className="space-y-2">
              <Label>Weekly off days</Label>
              <div className="flex flex-wrap gap-3">
                {WEEKDAY_LABELS.map((label, day) => (
                  <label key={label} className="flex items-center gap-1.5 text-sm">
                    <input
                      type="checkbox"
                      checked={form.weekly_off_days.includes(day)}
                      onChange={() =>
                        set(
                          'weekly_off_days',
                          form.weekly_off_days.includes(day)
                            ? form.weekly_off_days.filter((item) => item !== day)
                            : [...form.weekly_off_days, day].sort((a, b) => a - b),
                        )
                      }
                    />
                    {label}
                  </label>
                ))}
              </div>
              {errors.weekly_off_days ? (
                <p className="text-destructive text-xs">{errors.weekly_off_days}</p>
              ) : null}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Proration & unpaid leave</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-3">
            <div className="space-y-2">
              <Label htmlFor="config-proration">Proration basis</Label>
              <select
                id="config-proration"
                className={selectClass}
                value={form.proration_basis}
                onChange={(event) =>
                  set('proration_basis', event.target.value as FormState['proration_basis'])
                }
              >
                {Object.entries(DAY_BASIS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="config-unpaid-treatment">Unpaid leave</Label>
              <select
                id="config-unpaid-treatment"
                className={selectClass}
                value={form.unpaid_leave_treatment}
                onChange={(event) =>
                  set('unpaid_leave_treatment', event.target.value as FormState['unpaid_leave_treatment'])
                }
              >
                {Object.entries(UNPAID_LEAVE_TREATMENT_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            <div className="space-y-2">
              <Label htmlFor="config-unpaid-basis">Unpaid leave basis</Label>
              <select
                id="config-unpaid-basis"
                className={selectClass}
                value={form.unpaid_leave_basis}
                onChange={(event) =>
                  set('unpaid_leave_basis', event.target.value as FormState['unpaid_leave_basis'])
                }
              >
                {Object.entries(DAY_BASIS_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Overtime</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="flex flex-wrap gap-6">
              {checkbox('overtime_enabled', 'Overtime enabled')}
              {checkbox('overtime_approval_required', 'Approval required')}
            </div>
            <div className="grid gap-4 sm:grid-cols-4">
              <div className="space-y-2">
                <Label htmlFor="config-ot-basis">Calculation basis</Label>
                <select
                  id="config-ot-basis"
                  className={selectClass}
                  value={form.overtime_basis}
                  onChange={(event) =>
                    set('overtime_basis', event.target.value as FormState['overtime_basis'])
                  }
                >
                  <option value="basic">Basic</option>
                  <option value="gross">Gross</option>
                </select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="config-ot-multiplier">Hourly multiplier</Label>
                <Input
                  id="config-ot-multiplier"
                  inputMode="decimal"
                  value={form.overtime_multiplier}
                  onChange={(event) => set('overtime_multiplier', event.target.value)}
                />
                {errors.overtime_multiplier ? (
                  <p className="text-destructive text-xs">{errors.overtime_multiplier}</p>
                ) : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="config-ot-min">Minimum hours</Label>
                <Input
                  id="config-ot-min"
                  inputMode="decimal"
                  value={form.overtime_min_hours}
                  onChange={(event) => set('overtime_min_hours', event.target.value)}
                />
                {errors.overtime_min_hours ? (
                  <p className="text-destructive text-xs">{errors.overtime_min_hours}</p>
                ) : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="config-ot-max">Maximum hours (blank = no cap)</Label>
                <Input
                  id="config-ot-max"
                  inputMode="decimal"
                  value={form.overtime_max_hours ?? ''}
                  onChange={(event) => set('overtime_max_hours', event.target.value || null)}
                />
                {errors.overtime_max_hours ? (
                  <p className="text-destructive text-xs">{errors.overtime_max_hours}</p>
                ) : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="config-daily-hours">Standard daily hours</Label>
                <Input
                  id="config-daily-hours"
                  inputMode="decimal"
                  value={form.standard_daily_hours}
                  onChange={(event) => set('standard_daily_hours', event.target.value)}
                />
                <p className="text-muted-foreground text-xs">
                  Turns a monthly amount into an hourly overtime rate.
                </p>
                {errors.standard_daily_hours ? (
                  <p className="text-destructive text-xs">{errors.standard_daily_hours}</p>
                ) : null}
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Attendance</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-6">
            {checkbox('deduct_absence', 'Deduct for absence')}
            {checkbox('deduct_late_arrival', 'Deduct for late arrival')}
            {checkbox('deduct_early_exit', 'Deduct for early exit')}
            {checkbox('require_approved_attendance', 'Require approved attendance')}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Rounding</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <Label htmlFor="config-rounding">Rounding rule</Label>
              <select
                id="config-rounding"
                className={selectClass}
                value={form.rounding_rule}
                onChange={(event) => {
                  const rule = event.target.value as FormState['rounding_rule'];
                  setForm((current) =>
                    current === null
                      ? current
                      : {
                          ...current,
                          rounding_rule: rule,
                          rounding_precision: rule === 'custom' ? current.rounding_precision : null,
                        },
                  );
                }}
              >
                {Object.entries(ROUNDING_RULE_LABELS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </select>
            </div>
            {form.rounding_rule === 'custom' ? (
              <div className="space-y-2">
                <Label htmlFor="config-precision">Precision</Label>
                <Input
                  id="config-precision"
                  inputMode="decimal"
                  placeholder="e.g. 0.01, 1, 10"
                  value={form.rounding_precision ?? ''}
                  onChange={(event) => set('rounding_precision', event.target.value || null)}
                />
                {errors.rounding_precision ? (
                  <p className="text-destructive text-xs">{errors.rounding_precision}</p>
                ) : null}
              </div>
            ) : null}
          </CardContent>
        </Card>

        <Can permission="payroll:config_manage">
          <Card>
            <CardHeader>
              <CardTitle>Save changes</CardTitle>
            </CardHeader>
            <CardContent className="grid gap-4 sm:grid-cols-3">
              <div className="space-y-2 sm:col-span-2">
                <Label htmlFor="config-reason">Reason</Label>
                <Textarea
                  id="config-reason"
                  rows={2}
                  placeholder="Why is the configuration changing?"
                  value={reason}
                  onChange={(event) => setReason(event.target.value)}
                />
                {errors.reason ? <p className="text-destructive text-xs">{errors.reason}</p> : null}
              </div>
              <div className="space-y-2">
                <Label htmlFor="config-effective">Effective from</Label>
                <Input
                  id="config-effective"
                  type="date"
                  value={effectiveFrom}
                  onChange={(event) => setEffectiveFrom(event.target.value)}
                />
                {errors.effective_from ? (
                  <p className="text-destructive text-xs">{errors.effective_from}</p>
                ) : null}
              </div>
              <div className="sm:col-span-3">
                <Button type="submit">Save configuration</Button>
              </div>
            </CardContent>
          </Card>
        </Can>
      </form>

      <Card>
        <CardHeader>
          <CardTitle>Configuration history</CardTitle>
        </CardHeader>
        <CardContent>
          <DataTable
            rows={history.data ?? []}
            columns={historyColumns}
            getRowId={(row) => row.id}
            isLoading={history.isLoading}
            error={history.error}
            emptyTitle="No changes yet"
            emptyDescription="Every configuration change will be recorded here — previous value, new value, reason and author."
          />
        </CardContent>
      </Card>

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title="Update the payroll configuration?"
        description={`The change takes effect from ${effectiveFrom || 'the chosen date'} and every changed field is recorded in the history with your reason.`}
        confirmLabel="Save configuration"
        isConfirming={update.isPending}
        onConfirm={submit}
      />
    </div>
  );
}
