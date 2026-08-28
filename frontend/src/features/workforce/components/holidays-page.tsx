'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { Trash2 } from 'lucide-react';
import * as React from 'react';
import { useFieldArray, useForm, type FieldPath } from 'react-hook-form';

import { EmptyState } from '@/components/common/empty-state';
import { ErrorState } from '@/components/common/error-state';
import { FormLayout, FormSection } from '@/components/common/form-layout';
import { LoadingState } from '@/components/common/loading-state';
import { Modal } from '@/components/common/modal';
import { NumberField } from '@/components/common/number-field';
import { PageHeader } from '@/components/common/page-header';
import { SelectField } from '@/components/common/select-field';
import { TextField } from '@/components/common/text-field';
import { TextareaField } from '@/components/common/textarea-field';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Form } from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { useCreateHolidayCalendar, useHolidayCalendars } from '@/features/workforce/hooks';
import { holidayCalendarSchema, type HolidayCalendarFormValues } from '@/features/workforce/schema';
import { HOLIDAY_TYPES, HOLIDAY_TYPE_LABELS } from '@/features/workforce/types';

/**
 * Holiday calendars.
 *
 * A holiday is not simply informational: a day on the calendar is not charged
 * when leave is applied for across it, and it is not counted as an absence. A
 * missing holiday quietly costs someone a leave day.
 */
/** A path into the holiday rows, typed exactly rather than as a bare string. */
const holidayField = (index: number, name: string): FieldPath<HolidayCalendarFormValues> =>
  `holidays.${String(index)}.${name}` as FieldPath<HolidayCalendarFormValues>;

export function HolidaysPage(): React.JSX.Element {
  const [year, setYear] = React.useState(() => new Date().getFullYear());
  const [isOpen, setIsOpen] = React.useState(false);

  const query = useHolidayCalendars({ year });
  const create = useCreateHolidayCalendar();

  const form = useForm<HolidayCalendarFormValues>({
    resolver: zodResolver(holidayCalendarSchema),
    defaultValues: {
      name: '',
      year,
      location_id: '',
      description: '',
      holidays: [{ name: '', holiday_date: '', holiday_type: 'public' }],
    },
  });

  const holidays = useFieldArray({ control: form.control, name: 'holidays' });

  const submit = form.handleSubmit((values) => {
    create.mutate(values, {
      onSuccess: () => {
        setIsOpen(false);
        form.reset();
      },
    });
  });

  return (
    <div className="space-y-6">
      <PageHeader
        title="Holiday calendars"
        description="Days on a calendar are free: they are not charged as leave and are not marked absent."
        actions={
          <Button
            onClick={() => {
              form.reset({
                name: '',
                year,
                location_id: '',
                description: '',
                holidays: [{ name: '', holiday_date: '', holiday_type: 'public' }],
              });
              setIsOpen(true);
            }}
          >
            Create calendar
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Year</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="w-full max-w-40 space-y-1.5">
            <Label htmlFor="holiday-year">Showing</Label>
            <Input
              id="holiday-year"
              max={2100}
              min={2000}
              onChange={(event) => {
                setYear(Number(event.target.value));
              }}
              type="number"
              value={year}
            />
          </div>
        </CardContent>
      </Card>

      {query.isPending ? (
        <LoadingState />
      ) : query.error ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : (query.data ?? []).length === 0 ? (
        <EmptyState
          title="No calendar for this year"
          description="Create one so holidays stop being charged as leave."
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {(query.data ?? []).map((calendar) => (
            <Card key={calendar.id}>
              <CardHeader>
                <CardTitle>{calendar.name}</CardTitle>
                <CardDescription>
                  {calendar.description ??
                    `${String(calendar.holidays.length)} holidays in ${String(calendar.year)}`}
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {[...calendar.holidays]
                  .sort((a, b) => a.holiday_date.localeCompare(b.holiday_date))
                  .map((holiday) => (
                    <div
                      className="flex items-center justify-between border-b py-1.5 last:border-0"
                      key={holiday.id}
                    >
                      <div>
                        <p className="font-medium">{holiday.name}</p>
                        <p className="text-muted-foreground text-sm tabular-nums">{holiday.holiday_date}</p>
                      </div>
                      <Badge variant="outline">{HOLIDAY_TYPE_LABELS[holiday.holiday_type]}</Badge>
                    </div>
                  ))}
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      <Modal
        onOpenChange={setIsOpen}
        open={isOpen}
        size="xl"
        title="Create a holiday calendar"
        description="Every date must fall inside the year, and no date twice."
        footer={
          <>
            <Button
              onClick={() => {
                setIsOpen(false);
              }}
              variant="outline"
            >
              Cancel
            </Button>
            <Button isLoading={create.isPending} onClick={() => void submit()}>
              Create
            </Button>
          </>
        }
      >
        <Form {...form}>
          <FormLayout onSubmit={(event) => void submit(event)}>
            <FormSection title="Calendar">
              <TextField control={form.control} label="Name" name="name" placeholder="India 2026" required />
              <NumberField control={form.control} label="Year" name="year" required />
              <TextareaField
                className="sm:col-span-2"
                control={form.control}
                label="Description"
                name="description"
                rows={2}
              />
            </FormSection>

            <FormSection columns={1} title="Holidays">
              <div className="space-y-3">
                {holidays.fields.map((field, index) => (
                  <div className="grid items-end gap-3 sm:grid-cols-[2fr_1fr_1fr_auto]" key={field.id}>
                    <TextField
                      control={form.control}
                      label="Name"
                      name={holidayField(index, 'name')}
                      required
                    />
                    <TextField
                      control={form.control}
                      label="Date"
                      name={holidayField(index, 'holiday_date')}
                      required
                      type="date"
                    />
                    <SelectField
                      control={form.control}
                      label="Type"
                      name={holidayField(index, 'holiday_type')}
                      options={HOLIDAY_TYPES.map((value) => ({
                        value,
                        label: HOLIDAY_TYPE_LABELS[value],
                      }))}
                      required
                    />
                    <Button
                      aria-label={`Remove holiday ${String(index + 1)}`}
                      disabled={holidays.fields.length === 1}
                      onClick={() => {
                        holidays.remove(index);
                      }}
                      size="icon"
                      type="button"
                      variant="outline"
                    >
                      <Trash2 className="size-4" />
                    </Button>
                  </div>
                ))}

                <Button
                  onClick={() => {
                    holidays.append({ name: '', holiday_date: '', holiday_type: 'public' });
                  }}
                  type="button"
                  variant="outline"
                >
                  Add a holiday
                </Button>
              </div>
            </FormSection>
          </FormLayout>
        </Form>
      </Modal>
    </div>
  );
}
