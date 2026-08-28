'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { ChevronLeft, ChevronRight, Trash2 } from 'lucide-react';
import * as React from 'react';
import { useFieldArray, useForm, type FieldPath } from 'react-hook-form';

import { EmptyState } from '@/components/common/empty-state';
import { FormLayout } from '@/components/common/form-layout';
import { PageHeader } from '@/components/common/page-header';
import { SelectField } from '@/components/common/select-field';
import { TextField } from '@/components/common/text-field';
import { TimesheetStatusBadge } from '@/components/common/workforce-widgets';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Form } from '@/components/ui/form';
import { Label } from '@/components/ui/label';
import { useProjects } from '@/features/projects/hooks';
import { EmployeePicker } from '@/features/workforce/components/employee-picker';
import { useSaveTimesheet, useSubmitTimesheet, useTimesheets } from '@/features/workforce/hooks';
import { timesheetSchema, type TimesheetFormValues } from '@/features/workforce/schema';
import { MAX_DAILY_HOURS, WEEKDAYS } from '@/features/workforce/types';

/** The Monday of the week a date falls in. */
function mondayOf(date: Date): string {
  const monday = new Date(date);
  monday.setDate(monday.getDate() - ((monday.getDay() + 6) % 7));
  return monday.toISOString().slice(0, 10);
}

function addDays(iso: string, days: number): string {
  const date = new Date(`${iso}T00:00:00`);
  date.setDate(date.getDate() + days);
  return date.toISOString().slice(0, 10);
}

/** A path into the entry rows, typed exactly rather than as a bare string. */
const entryField = (index: number, name: string): FieldPath<TimesheetFormValues> =>
  `entries.${String(index)}.${name}` as FieldPath<TimesheetFormValues>;

/**
 * The weekly timesheet.
 *
 * Saved as a whole week rather than line by line: a timesheet is edited as a
 * grid, and diffing rows client-side would be a second source of truth for what
 * the week contains. Once submitted it is read-only until it is decided --
 * an approver has to be looking at what they were shown.
 */
export function TimesheetPage(): React.JSX.Element {
  const [employeeId, setEmployeeId] = React.useState('');
  const [weekStart, setWeekStart] = React.useState(() => mondayOf(new Date()));

  const projects = useProjects();
  const save = useSaveTimesheet(employeeId);
  const submit = useSubmitTimesheet();

  const query = useTimesheets(
    employeeId ? { employee_id: employeeId, from_date: weekStart, to_date: weekStart } : {},
  );
  const timesheet = employeeId
    ? query.data?.items.find((row) => row.week_start_date === weekStart)
    : undefined;
  const isLocked = timesheet?.status === 'submitted' || timesheet?.status === 'approved';

  const form = useForm<TimesheetFormValues>({
    resolver: zodResolver(timesheetSchema),
    defaultValues: { week_start_date: weekStart, entries: [] },
  });
  const entries = useFieldArray({ control: form.control, name: 'entries' });

  // Reload whenever the week or the saved timesheet changes, so the grid always
  // shows what is stored rather than what was last typed into a different week.
  React.useEffect(() => {
    form.reset({
      week_start_date: weekStart,
      entries: (timesheet?.entries ?? []).map((entry) => ({
        project_id: entry.project_id,
        work_date: entry.work_date,
        task: entry.task,
        hours: entry.hours,
        billable: entry.billable,
        comments: entry.comments ?? '',
      })),
    });
  }, [form, timesheet, weekStart]);

  const watched = form.watch('entries');
  const totals = React.useMemo(() => {
    const perDay = new Map<string, number>();
    let total = 0;
    let billable = 0;
    for (const entry of watched) {
      const hours = Number(entry.hours) || 0;
      perDay.set(entry.work_date, (perDay.get(entry.work_date) ?? 0) + hours);
      total += hours;
      if (entry.billable) billable += hours;
    }
    return { perDay, total, billable };
  }, [watched]);

  const stepWeek = (delta: number): void => {
    setWeekStart(addDays(weekStart, delta * 7));
  };

  const onSave = form.handleSubmit((values) => {
    save.mutate(values);
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Timesheets"
        description="One week at a time. Hours can only be booked against a project the employee is allocated to."
        actions={
          <div className="flex gap-2">
            <Button
              disabled={!employeeId || isLocked}
              isLoading={save.isPending}
              onClick={() => void onSave()}
              variant="outline"
            >
              Save
            </Button>
            <Button
              disabled={!timesheet || isLocked || watched.length === 0}
              isLoading={submit.isPending}
              onClick={() => {
                if (timesheet) submit.mutate(timesheet.id);
              }}
            >
              Submit
            </Button>
          </div>
        }
      />

      <Card>
        <CardHeader className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <EmployeePicker onChange={setEmployeeId} value={employeeId} />
          <div className="flex items-center gap-2">
            <Button
              aria-label="Previous week"
              onClick={() => {
                stepWeek(-1);
              }}
              size="icon"
              variant="outline"
            >
              <ChevronLeft className="size-4" />
            </Button>
            <span className="min-w-56 text-center font-medium tabular-nums">
              {weekStart} → {addDays(weekStart, 6)}
            </span>
            <Button
              aria-label="Next week"
              onClick={() => {
                stepWeek(1);
              }}
              size="icon"
              variant="outline"
            >
              <ChevronRight className="size-4" />
            </Button>
          </div>
        </CardHeader>
      </Card>

      {!employeeId ? (
        <EmptyState title="Choose an employee" description="Pick someone above to fill in their week." />
      ) : (
        <>
          {timesheet ? (
            <div className="flex flex-wrap items-center gap-3">
              <TimesheetStatusBadge status={timesheet.status} />
              <span className="text-muted-foreground text-sm">{timesheet.timesheet_code}</span>
              {timesheet.status === 'rejected' && timesheet.decision_notes ? (
                <Alert variant="destructive">
                  <AlertTitle>Sent back</AlertTitle>
                  <AlertDescription>{timesheet.decision_notes}</AlertDescription>
                </Alert>
              ) : null}
            </div>
          ) : null}

          {isLocked ? (
            <Alert>
              <AlertTitle>This week is {timesheet?.status}</AlertTitle>
              <AlertDescription>
                A submitted timesheet is not edited. It has to be sent back before it can change, so an
                approval always refers to a state somebody actually saw.
              </AlertDescription>
            </Alert>
          ) : null}

          <Form {...form}>
            <FormLayout onSubmit={(event) => void onSave(event)}>
              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">Entries</CardTitle>
                  <CardDescription>
                    A day cannot hold more than {MAX_DAILY_HOURS} hours, and the same project and task cannot
                    appear twice on one day.
                  </CardDescription>
                </CardHeader>
                <CardContent className="space-y-4">
                  {entries.fields.length === 0 ? (
                    <p className="text-muted-foreground text-sm">Nothing booked for this week yet.</p>
                  ) : (
                    entries.fields.map((field, index) => (
                      <div
                        className="grid items-end gap-3 lg:grid-cols-[2fr_1fr_2fr_0.8fr_auto_auto]"
                        key={field.id}
                      >
                        <SelectField
                          control={form.control}
                          disabled={isLocked}
                          isLoading={projects.isPending}
                          label="Project"
                          name={entryField(index, 'project_id')}
                          options={(projects.data?.items ?? []).map((project) => ({
                            value: project.id,
                            label: project.project_name,
                            hint: project.project_code,
                          }))}
                          required
                        />
                        <SelectField
                          control={form.control}
                          disabled={isLocked}
                          label="Day"
                          name={entryField(index, 'work_date')}
                          options={WEEKDAYS.map((label, offset) => ({
                            value: addDays(weekStart, offset),
                            label,
                            hint: addDays(weekStart, offset),
                          }))}
                          required
                        />
                        <TextField
                          control={form.control}
                          disabled={isLocked}
                          label="Task"
                          name={entryField(index, 'task')}
                          required
                        />
                        <TextField
                          control={form.control}
                          disabled={isLocked}
                          label="Hours"
                          name={entryField(index, 'hours')}
                          required
                        />
                        <div className="flex items-center gap-2 pb-2">
                          <Checkbox
                            checked={watched[index]?.billable ?? true}
                            disabled={isLocked}
                            id={`billable-${String(index)}`}
                            onCheckedChange={(value) => {
                              form.setValue(entryField(index, 'billable'), value === true, {
                                shouldDirty: true,
                              });
                            }}
                          />
                          <Label htmlFor={`billable-${String(index)}`}>Billable</Label>
                        </div>
                        <Button
                          aria-label={`Remove entry ${String(index + 1)}`}
                          disabled={isLocked}
                          onClick={() => {
                            entries.remove(index);
                          }}
                          size="icon"
                          type="button"
                          variant="outline"
                        >
                          <Trash2 className="size-4" />
                        </Button>
                      </div>
                    ))
                  )}

                  <Button
                    disabled={isLocked}
                    onClick={() => {
                      entries.append({
                        project_id: '',
                        work_date: weekStart,
                        task: '',
                        hours: '8.00',
                        billable: true,
                        comments: '',
                      });
                    }}
                    type="button"
                    variant="outline"
                  >
                    Add an entry
                  </Button>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle className="text-sm">This week</CardTitle>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid gap-2 sm:grid-cols-7">
                    {WEEKDAYS.map((label, offset) => {
                      const day = addDays(weekStart, offset);
                      const hours = totals.perDay.get(day) ?? 0;
                      return (
                        <div className="rounded-md border p-2 text-center" key={label}>
                          <p className="text-muted-foreground text-xs">{label.slice(0, 3)}</p>
                          <p
                            className={`font-semibold tabular-nums ${hours > MAX_DAILY_HOURS ? 'text-destructive' : ''}`}
                          >
                            {hours.toFixed(2)}
                          </p>
                        </div>
                      );
                    })}
                  </div>
                  <p className="text-sm">
                    <b className="tabular-nums">{totals.total.toFixed(2)}</b> hours total ·{' '}
                    <b className="tabular-nums">{totals.billable.toFixed(2)}</b> billable
                  </p>
                </CardContent>
              </Card>
            </FormLayout>
          </Form>
        </>
      )}
    </div>
  );
}
