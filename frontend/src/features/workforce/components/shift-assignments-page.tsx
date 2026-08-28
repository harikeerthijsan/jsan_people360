'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import * as React from 'react';
import { useForm } from 'react-hook-form';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { EmptyState } from '@/components/common/empty-state';
import { FormLayout, FormSection } from '@/components/common/form-layout';
import { Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { SelectField } from '@/components/common/select-field';
import { TextField } from '@/components/common/text-field';
import { ShiftSummary } from '@/components/common/workforce-widgets';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Form } from '@/components/ui/form';
import { EmployeePicker } from '@/features/workforce/components/employee-picker';
import { useAssignShift, useShiftHistory, useShifts } from '@/features/workforce/hooks';
import { shiftAssignSchema, type ShiftAssignFormValues } from '@/features/workforce/schema';
import type { EmployeeShift } from '@/features/workforce/types';

/**
 * Who is on which shift, and since when.
 *
 * Assigning never edits the current row: it closes it and opens a new one. An
 * attendance record from March has to be read against the shift that was in
 * force in March, not the one assigned since.
 */
export function ShiftAssignmentsPage(): React.JSX.Element {
  const [employeeId, setEmployeeId] = React.useState('');
  const [isOpen, setIsOpen] = React.useState(false);

  const shifts = useShifts({ status: 'active' });
  const history = useShiftHistory(employeeId || undefined);
  const assign = useAssignShift();

  const form = useForm<ShiftAssignFormValues>({
    resolver: zodResolver(shiftAssignSchema),
    defaultValues: { employee_id: '', shift_id: '', effective_from: '' },
  });

  const open = (): void => {
    form.reset({ employee_id: employeeId, shift_id: '', effective_from: '' });
    setIsOpen(true);
  };

  const submit = form.handleSubmit((values) => {
    assign.mutate(values, {
      onSuccess: () => {
        setIsOpen(false);
        form.reset();
      },
    });
  });

  const columns: DataTableColumn<EmployeeShift>[] = [
    {
      id: 'shift',
      header: 'Shift',
      cell: (row) => (row.shift ? <ShiftSummary shift={row.shift} /> : '—'),
    },
    {
      id: 'from',
      header: 'Effective from',
      cell: (row) => <span className="tabular-nums">{row.effective_from}</span>,
    },
    {
      id: 'to',
      header: 'Until',
      cell: (row) =>
        row.effective_to ? (
          <span className="tabular-nums">{row.effective_to}</span>
        ) : (
          <Badge variant="success">Current</Badge>
        ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Shift assignments"
        description="Assigning closes the current assignment and opens a new one; nothing is overwritten."
        actions={
          <Button disabled={!employeeId} onClick={open}>
            Assign a shift
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Whose history</CardTitle>
        </CardHeader>
        <CardContent>
          <EmployeePicker onChange={setEmployeeId} value={employeeId} />
        </CardContent>
      </Card>

      {!employeeId ? (
        <EmptyState
          title="Choose an employee"
          description="Pick someone above to see which shifts they have been on."
        />
      ) : (
        <DataTable
          columns={columns}
          emptyDescription="This employee has never been assigned a shift."
          emptyTitle="No assignments"
          error={history.error}
          getRowId={(row) => row.id}
          isLoading={history.isPending}
          onRetry={() => void history.refetch()}
          rows={history.data ?? []}
        />
      )}

      <Modal
        onOpenChange={setIsOpen}
        open={isOpen}
        title="Assign a shift"
        description="The new shift must start after the current assignment began."
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
            <Button isLoading={assign.isPending} onClick={() => void submit()}>
              Assign
            </Button>
          </>
        }
      >
        <Form {...form}>
          <FormLayout onSubmit={(event) => void submit(event)}>
            <FormSection columns={1} title="Assignment">
              <SelectField
                control={form.control}
                isLoading={shifts.isPending}
                label="Shift"
                name="shift_id"
                options={(shifts.data?.items ?? []).map((shift) => ({
                  value: shift.id,
                  label: shift.name,
                  hint: `${shift.start_time.slice(0, 5)} – ${shift.end_time.slice(0, 5)}`,
                }))}
                required
              />
              <TextField
                control={form.control}
                description="The previous assignment is closed the day before this."
                label="Effective from"
                name="effective_from"
                required
                type="date"
              />
            </FormSection>
          </FormLayout>
        </Form>
      </Modal>
    </div>
  );
}
