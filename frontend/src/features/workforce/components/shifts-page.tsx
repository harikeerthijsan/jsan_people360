'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import * as React from 'react';
import { useForm } from 'react-hook-form';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { FormLayout, FormSection } from '@/components/common/form-layout';
import { Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { NumberField } from '@/components/common/number-field';
import { SelectField } from '@/components/common/select-field';
import { TextField } from '@/components/common/text-field';
import { ShiftSummary } from '@/components/common/workforce-widgets';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Form } from '@/components/ui/form';
import { Label } from '@/components/ui/label';
import { useCreateShift, useShifts, useUpdateShift } from '@/features/workforce/hooks';
import { shiftSchema, type ShiftFormValues } from '@/features/workforce/schema';
import { SHIFT_TYPES, SHIFT_TYPE_LABELS, WEEKDAYS, type Shift } from '@/features/workforce/types';

const BLANK: ShiftFormValues = {
  name: '',
  code: '',
  shift_type: 'general',
  start_time: '09:30',
  end_time: '18:30',
  grace_minutes: 15,
  break_minutes: 60,
  weekly_off: [5, 6],
  status: 'active',
};

/**
 * Shifts.
 *
 * A shift is what an attendance record is measured against -- late, early exit
 * and overtime all come from its window and grace. Editing one changes how
 * future days are read, which is why assignment history is kept separately
 * rather than by editing the shift under an employee.
 */
export function ShiftsPage(): React.JSX.Element {
  const [editing, setEditing] = React.useState<Shift | null>(null);
  const [isOpen, setIsOpen] = React.useState(false);

  const query = useShifts();
  const create = useCreateShift();
  const update = useUpdateShift(editing?.id ?? '');

  const form = useForm<ShiftFormValues>({ resolver: zodResolver(shiftSchema), defaultValues: BLANK });
  const weeklyOff = form.watch('weekly_off');

  const open = (shift: Shift | null): void => {
    setEditing(shift);
    form.reset(
      shift
        ? {
            name: shift.name,
            code: shift.code,
            shift_type: shift.shift_type,
            start_time: shift.start_time.slice(0, 5),
            end_time: shift.end_time.slice(0, 5),
            grace_minutes: shift.grace_minutes,
            break_minutes: shift.break_minutes,
            weekly_off: shift.weekly_off,
            status: shift.status,
          }
        : BLANK,
    );
    setIsOpen(true);
  };

  const toggleDay = (day: number, checked: boolean): void => {
    const next = checked ? [...weeklyOff, day] : weeklyOff.filter((value) => value !== day);
    form.setValue(
      'weekly_off',
      next.sort((a, b) => Number(a) - Number(b)),
      {
        shouldDirty: true,
        shouldValidate: true,
      },
    );
  };

  const submit = form.handleSubmit((values) => {
    const mutation = editing ? update : create;
    mutation.mutate(values, {
      onSuccess: () => {
        setIsOpen(false);
        setEditing(null);
      },
    });
  });

  const columns: DataTableColumn<Shift>[] = [
    { id: 'shift', header: 'Shift', cell: (row) => <ShiftSummary shift={row} /> },
    { id: 'code', header: 'Code', cell: (row) => row.code },
    {
      id: 'break',
      header: 'Break',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{row.break_minutes} min</span>,
    },
    {
      id: 'off',
      header: 'Weekly off',
      cell: (row) =>
        row.weekly_off.length === 0
          ? 'None'
          : row.weekly_off.map((day) => WEEKDAYS[day]?.slice(0, 3) ?? '?').join(', '),
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <Badge variant={row.status === 'active' ? 'success' : 'outline'}>
          {row.status === 'active' ? 'Active' : 'Inactive'}
        </Badge>
      ),
    },
    {
      id: 'action',
      header: '',
      align: 'right',
      cell: (row) => (
        <Button
          onClick={() => {
            open(row);
          }}
          size="sm"
          variant="outline"
        >
          Edit
        </Button>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Shifts"
        description="The working window each attendance record is read against."
        actions={
          <Button
            onClick={() => {
              open(null);
            }}
          >
            Add shift
          </Button>
        }
      />

      <DataTable
        columns={columns}
        emptyDescription="No shifts are configured."
        emptyTitle="Nothing configured"
        error={query.error}
        getRowId={(row) => row.id}
        isLoading={query.isPending}
        onRetry={() => void query.refetch()}
        rows={query.data?.items ?? []}
      />

      <Modal
        onOpenChange={setIsOpen}
        open={isOpen}
        size="lg"
        title={editing ? `Edit ${editing.name}` : 'Add a shift'}
        description="Editing changes how days are read from now on; days already recorded keep their figures."
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
            <Button isLoading={create.isPending || update.isPending} onClick={() => void submit()}>
              Save
            </Button>
          </>
        }
      >
        <Form {...form}>
          <FormLayout onSubmit={(event) => void submit(event)}>
            <FormSection title="Identity">
              <TextField control={form.control} label="Name" name="name" required />
              <TextField control={form.control} label="Code" name="code" required />
              <SelectField
                control={form.control}
                label="Type"
                name="shift_type"
                options={SHIFT_TYPES.map((value) => ({ value, label: SHIFT_TYPE_LABELS[value] }))}
                required
              />
              <SelectField
                control={form.control}
                label="Status"
                name="status"
                options={[
                  { value: 'active', label: 'Active' },
                  { value: 'inactive', label: 'Inactive', hint: 'Cannot be assigned' },
                ]}
                required
              />
            </FormSection>

            <FormSection
              description="A night shift may end before it starts; that is expected."
              title="Timings"
            >
              <TextField control={form.control} label="Starts" name="start_time" required type="time" />
              <TextField control={form.control} label="Ends" name="end_time" required type="time" />
              <NumberField
                control={form.control}
                description="Minutes after the start time before an arrival counts as late."
                label="Grace"
                name="grace_minutes"
              />
              <NumberField
                control={form.control}
                description="Deducted from the day's worked time."
                label="Break"
                name="break_minutes"
              />
            </FormSection>

            <FormSection columns={1} title="Weekly off">
              <div className="flex flex-wrap gap-4">
                {WEEKDAYS.map((label, day) => (
                  <div className="flex items-center gap-2" key={label}>
                    <Checkbox
                      checked={weeklyOff.includes(day)}
                      id={`weekly-off-${String(day)}`}
                      onCheckedChange={(value) => {
                        toggleDay(day, value === true);
                      }}
                    />
                    <Label htmlFor={`weekly-off-${String(day)}`}>{label}</Label>
                  </div>
                ))}
              </div>
              <p className="text-muted-foreground text-sm">
                These days are not charged when leave is applied for across them.
              </p>
            </FormSection>
          </FormLayout>
        </Form>
      </Modal>
    </div>
  );
}
