'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import * as React from 'react';
import { useForm, type DefaultValues, type FieldValues, type Resolver } from 'react-hook-form';

import { Modal } from '@/components/common/modal';
import { SelectField, type SelectOption } from '@/components/common/select-field';
import { TextField } from '@/components/common/text-field';
import { TextareaField } from '@/components/common/textarea-field';
import { Form } from '@/components/ui/form';
import { useEmployeeList, useLifecycleAction } from '@/features/employees/hooks/use-employees';
import {
  changeDesignationSchema,
  changeManagerSchema,
  confirmEmployeeSchema,
  promoteEmployeeSchema,
  transferTeamSchema,
} from '@/features/employees/schemas/employee.schemas';
import type { EmployeeRecord } from '@/features/employees/types/employee.types';
import { useMasterOptions } from '@/features/organization/hooks/use-masters';
import type { MasterSlug } from '@/features/organization/types/organization.types';

/**
 * The lifecycle actions that need a form before they can run.
 *
 * Each is its own dialog with its own schema rather than one dialog with a mode
 * switch: a transfer and a promotion ask for different things, and a shared form
 * would make every field optional and every rule conditional -- exactly the
 * shape the API deliberately avoids.
 */
export type LifecycleKind = 'confirm' | 'transfer' | 'designation' | 'manager' | 'promote';

const today = (): string => new Date().toISOString().slice(0, 10);

/** A picker backed by one of the organization masters. */
function MasterSelect({
  control,
  name,
  label,
  master,
  required = false,
  disabled,
}: {
  control: ReturnType<typeof useForm<FieldValues>>['control'];
  name: string;
  label: string;
  master: MasterSlug;
  required?: boolean;
  disabled: boolean;
}): React.JSX.Element {
  const query = useMasterOptions(master);
  const options: SelectOption[] = (query.data?.items ?? []).map((record) => ({
    value: record.id,
    label: record.name,
    hint: record.code,
  }));

  return (
    <SelectField
      control={control}
      name={name}
      label={label}
      options={options}
      isLoading={query.isPending}
      emptyMessage={`No active ${label.toLowerCase()} to choose from`}
      required={required}
      disabled={disabled}
    />
  );
}

interface LifecycleDialogsProps {
  employee: EmployeeRecord;
  openKind: LifecycleKind | null;
  onClose: () => void;
}

export function LifecycleDialogs({
  employee,
  openKind,
  onClose,
}: LifecycleDialogsProps): React.JSX.Element | null {
  if (openKind === null) return null;

  // Keyed on the kind so switching action remounts the form rather than
  // carrying the previous action's values across.
  return <LifecycleDialog key={openKind} employee={employee} kind={openKind} onClose={onClose} />;
}

function LifecycleDialog({
  employee,
  kind,
  onClose,
}: {
  employee: EmployeeRecord;
  kind: LifecycleKind;
  onClose: () => void;
}): React.JSX.Element {
  const config = DIALOGS[kind];
  const mutation = useLifecycleAction(config.action, employee.id);

  const form = useForm<FieldValues>({
    resolver: zodResolver(config.schema) as Resolver<FieldValues>,
    defaultValues: config.defaults(employee) as DefaultValues<FieldValues>,
    mode: 'onSubmit',
  });

  const submit = form.handleSubmit((values) => {
    mutation.mutate(values, { onSuccess: onClose });
  });

  return (
    <Modal
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title={config.title}
      description={config.description}
      size="md"
      footer={null}
    >
      <Form {...form}>
        <form onSubmit={submit} className="space-y-4" noValidate>
          <div className="grid gap-4 sm:grid-cols-2">
            {config.fields({ form, employee, disabled: mutation.isPending })}

            <TextField
              control={form.control}
              name="effective_date"
              label="Effective date"
              type="date"
              description="Back-dating is allowed."
              required
              disabled={mutation.isPending}
            />
            <TextField control={form.control} name="reason" label="Reason" disabled={mutation.isPending} />
            <TextareaField
              control={form.control}
              name="notes"
              label="Notes"
              rows={2}
              className="sm:col-span-2"
              disabled={mutation.isPending}
            />
          </div>

          <div className="flex justify-end gap-2 pt-2">
            <button
              type="button"
              onClick={onClose}
              disabled={mutation.isPending}
              className="border-input hover:bg-accent inline-flex h-9 items-center rounded-md border px-4 text-sm font-medium disabled:opacity-50"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={mutation.isPending}
              aria-busy={mutation.isPending}
              className="bg-primary text-primary-foreground hover:bg-primary-hover inline-flex h-9 items-center rounded-md px-4 text-sm font-medium disabled:opacity-50"
            >
              {mutation.isPending ? 'Saving…' : config.submitLabel}
            </button>
          </div>
        </form>
      </Form>
    </Modal>
  );
}

interface FieldsProps {
  form: ReturnType<typeof useForm<FieldValues>>;
  employee: EmployeeRecord;
  disabled: boolean;
}

interface DialogConfig {
  title: string;
  description: string;
  submitLabel: string;
  action: 'confirm' | 'transfer' | 'changeDesignation' | 'changeManager' | 'promote';
  schema: Parameters<typeof zodResolver>[0];
  defaults: (employee: EmployeeRecord) => FieldValues;
  fields: (props: FieldsProps) => React.ReactNode;
}

const baseDefaults = (): FieldValues => ({ effective_date: today(), reason: '', notes: '' });

const DIALOGS: Record<LifecycleKind, DialogConfig> = {
  confirm: {
    title: 'Confirm this employee?',
    description: 'Ends probation and records the confirmation date.',
    submitLabel: 'Confirm employee',
    action: 'confirm',
    schema: confirmEmployeeSchema,
    defaults: baseDefaults,
    fields: () => null,
  },

  transfer: {
    title: 'Transfer to another team',
    description: 'Choose a business unit as well when the move crosses units.',
    submitLabel: 'Transfer',
    action: 'transfer',
    schema: transferTeamSchema,
    defaults: () => ({ ...baseDefaults(), team_id: '', business_unit_id: '' }),
    fields: ({ form, disabled }) => (
      <>
        <MasterSelect
          control={form.control}
          name="team_id"
          label="New team"
          master="teams"
          required
          disabled={disabled}
        />
        <MasterSelect
          control={form.control}
          name="business_unit_id"
          label="Business unit"
          master="business-units"
          disabled={disabled}
        />
      </>
    ),
  },

  designation: {
    title: 'Change designation',
    description: 'Records a designation change, and optionally a new grade.',
    submitLabel: 'Change designation',
    action: 'changeDesignation',
    schema: changeDesignationSchema,
    defaults: () => ({ ...baseDefaults(), designation_id: '', grade_id: '' }),
    fields: ({ form, disabled }) => (
      <>
        <MasterSelect
          control={form.control}
          name="designation_id"
          label="New designation"
          master="designations"
          required
          disabled={disabled}
        />
        <MasterSelect
          control={form.control}
          name="grade_id"
          label="New grade"
          master="grades"
          disabled={disabled}
        />
      </>
    ),
  },

  manager: {
    title: 'Change reporting manager',
    description:
      'Leave empty to clear the reporting line. A manager who reports to this employee is refused.',
    submitLabel: 'Change manager',
    action: 'changeManager',
    schema: changeManagerSchema,
    defaults: (employee) => ({
      ...baseDefaults(),
      reporting_manager_id: employee.reporting_manager_id ?? '',
    }),
    fields: ({ form, employee, disabled }) => (
      <ManagerSelect form={form} employee={employee} disabled={disabled} />
    ),
  },

  promote: {
    title: 'Promote this employee',
    description: 'Change at least one of designation, grade, salary grade or CTC.',
    submitLabel: 'Record promotion',
    action: 'promote',
    schema: promoteEmployeeSchema,
    defaults: () => ({
      ...baseDefaults(),
      designation_id: '',
      grade_id: '',
      salary_grade_id: '',
      ctc: '',
    }),
    fields: ({ form, disabled }) => (
      <>
        <MasterSelect
          control={form.control}
          name="designation_id"
          label="New designation"
          master="designations"
          disabled={disabled}
        />
        <MasterSelect
          control={form.control}
          name="grade_id"
          label="New grade"
          master="grades"
          disabled={disabled}
        />
        <MasterSelect
          control={form.control}
          name="salary_grade_id"
          label="New salary grade"
          master="grades"
          disabled={disabled}
        />
        <TextField control={form.control} name="ctc" label="New CTC" disabled={disabled} />
      </>
    ),
  },
};

/** The manager picker, excluding the employee themselves. */
function ManagerSelect({ form, employee, disabled }: FieldsProps): React.JSX.Element {
  const query = useEmployeeList({
    page: 1,
    page_size: 100,
    archived: false,
    sort_by: 'first_name',
    sort_order: 'asc',
  });

  const options: SelectOption[] = (query.data?.items ?? [])
    .filter((candidate) => candidate.id !== employee.id)
    .map((candidate) => ({
      value: candidate.id,
      label: candidate.full_name,
      hint: candidate.employee_code,
    }));

  return (
    <SelectField
      control={form.control}
      name="reporting_manager_id"
      label="Reporting manager"
      options={options}
      isLoading={query.isPending}
      emptyMessage="No other employees to report to"
      className="sm:col-span-2"
      disabled={disabled}
    />
  );
}
