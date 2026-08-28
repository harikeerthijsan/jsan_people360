'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import * as React from 'react';
import { useForm, type Control, type DefaultValues, type FieldValues, type Resolver } from 'react-hook-form';

import { FormActions, FormLayout, FormSection } from '@/components/common/form-layout';
import { SelectField, type SelectOption } from '@/components/common/select-field';
import { TextField } from '@/components/common/text-field';
import { TextareaField } from '@/components/common/textarea-field';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Form } from '@/components/ui/form';
import { useEmployeeList } from '@/features/employees/hooks/use-employees';
import { createEmployeeSchema, editEmployeeSchema } from '@/features/employees/schemas/employee.schemas';
import {
  BLOOD_GROUPS,
  EMPLOYMENT_STATUSES,
  EMPLOYMENT_STATUS_LABELS,
  MARITAL_STATUS_LABELS,
  WORK_MODE_LABELS,
  type EmployeeRecord,
} from '@/features/employees/types/employee.types';
import { useMasterOptions } from '@/features/organization/hooks/use-masters';
import type { MasterSlug } from '@/features/organization/types/organization.types';
import { GENDER_LABELS } from '@/types/user';
import type { AppError } from '@/lib/errors';

const toOptions = (labels: Record<string, string>): SelectOption[] =>
  Object.entries(labels).map(([value, label]) => ({ value, label }));

const GENDER_OPTIONS = toOptions(GENDER_LABELS);
const MARITAL_STATUS_OPTIONS = toOptions(MARITAL_STATUS_LABELS);
const WORK_MODE_OPTIONS = toOptions(WORK_MODE_LABELS);
const BLOOD_GROUP_OPTIONS: SelectOption[] = BLOOD_GROUPS.map((group) => ({
  value: group,
  label: group,
}));
const STATUS_OPTIONS: SelectOption[] = EMPLOYMENT_STATUSES.map((status) => ({
  value: status,
  label: EMPLOYMENT_STATUS_LABELS[status],
}));

/** The organizational references, in hierarchy order. */
const ORG_FIELDS: { name: string; label: string; master: MasterSlug }[] = [
  { name: 'business_unit_id', label: 'Business unit', master: 'business-units' },
  { name: 'team_id', label: 'Team', master: 'teams' },
  { name: 'designation_id', label: 'Designation', master: 'designations' },
  { name: 'grade_id', label: 'Grade', master: 'grades' },
  { name: 'work_location_id', label: 'Work location', master: 'locations' },
  { name: 'employment_type_id', label: 'Employment type', master: 'employment-types' },
];

/** Renders one reference picker, loading its options from the master. */
function OrganizationField({
  control,
  name,
  label,
  master,
  disabled,
}: {
  control: Control<FieldValues>;
  name: string;
  label: string;
  master: MasterSlug;
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
      disabled={disabled}
    />
  );
}

/**
 * The reporting-manager picker.
 *
 * Drawn from the employee directory rather than a master, and it excludes the
 * person being edited: the API refuses a self-reference, and offering it here
 * would only produce an error the user could have been spared.
 */
function ManagerField({
  control,
  disabled,
  excludeId,
}: {
  control: Control<FieldValues>;
  disabled: boolean;
  excludeId?: string;
}): React.JSX.Element {
  const query = useEmployeeList({
    page: 1,
    page_size: 100,
    archived: false,
    sort_by: 'first_name',
    sort_order: 'asc',
  });

  const options: SelectOption[] = (query.data?.items ?? [])
    .filter((candidate) => candidate.id !== excludeId)
    .map((candidate) => ({
      value: candidate.id,
      label: candidate.full_name,
      hint: candidate.employee_code,
    }));

  return (
    <SelectField
      control={control}
      name="reporting_manager_id"
      label="Reporting manager"
      options={options}
      isLoading={query.isPending}
      emptyMessage="No other employees to report to yet"
      disabled={disabled}
    />
  );
}

interface EmployeeFormProps {
  /** Omit to create; supply to edit. */
  employee?: EmployeeRecord;
  isSubmitting: boolean;
  error: AppError | null;
  onSubmit: (values: FieldValues) => void;
  cancelHref: string;
}

/**
 * The multi-section employee form, shared by create and edit.
 *
 * Bank details and government identifiers are deliberately absent: they are
 * edited from their own tabs on the profile, where the unmasked values are
 * fetched through the audited reveal endpoint rather than sitting in a form
 * that is open for every other reason too.
 */
export function EmployeeForm({
  employee,
  isSubmitting,
  error,
  onSubmit,
  cancelHref,
}: EmployeeFormProps): React.JSX.Element {
  const isEdit = employee !== undefined;

  const defaults: FieldValues = React.useMemo(
    () => ({
      first_name: employee?.first_name ?? '',
      last_name: employee?.last_name ?? '',
      gender: employee?.gender ?? undefined,
      date_of_birth: employee?.date_of_birth ?? '',
      blood_group: employee?.blood_group ?? undefined,
      marital_status: employee?.marital_status ?? undefined,
      nationality: employee?.nationality ?? '',
      photo_url: employee?.photo_url ?? '',

      personal_email: employee?.personal_email ?? '',
      mobile_number: employee?.mobile_number ?? '',
      alternate_number: employee?.alternate_number ?? '',
      emergency_contact_name: employee?.emergency_contact_name ?? '',
      emergency_contact_number: employee?.emergency_contact_number ?? '',
      emergency_contact_relationship: employee?.emergency_contact_relationship ?? '',

      official_email: employee?.official_email ?? '',
      official_mobile: employee?.official_mobile ?? '',
      extension_number: employee?.extension_number ?? '',
      work_mode: employee?.work_mode ?? undefined,

      joining_date: employee?.joining_date ?? '',
      employment_status: employee?.employment_status ?? 'probation',
      employment_type_id: employee?.employment_type_id ?? '',
      business_unit_id: employee?.business_unit_id ?? '',
      team_id: employee?.team_id ?? '',
      designation_id: employee?.designation_id ?? '',
      grade_id: employee?.grade_id ?? '',
      work_location_id: employee?.work_location_id ?? '',
      reporting_manager_id: employee?.reporting_manager_id ?? '',
      user_id: employee?.user?.id ?? '',

      ctc: employee?.ctc ?? '',
      salary_grade_id: employee?.salary_grade_id ?? '',
      notes: employee?.notes ?? '',

      ...(isEdit ? { change_reason: '' } : {}),
    }),
    [employee, isEdit],
  );

  const form = useForm<FieldValues>({
    resolver: zodResolver(isEdit ? editEmployeeSchema : createEmployeeSchema) as Resolver<FieldValues>,
    defaultValues: defaults as DefaultValues<FieldValues>,
    mode: 'onSubmit',
  });

  const { reset } = form;
  React.useEffect(() => {
    reset(defaults);
  }, [defaults, reset]);

  const submit = form.handleSubmit((values) => {
    onSubmit(values);
  });

  // Field-scoped API errors (a duplicate work address) attach to their input;
  // anything else falls through to the alert above the form.
  React.useEffect(() => {
    if (!error) return;
    for (const [field, message] of Object.entries(error.fieldErrorMap)) {
      form.setError(field, { type: 'server', message });
    }
  }, [error, form]);

  const generalError = error && Object.keys(error.fieldErrorMap).length === 0 ? error.message : null;
  const disabled = isSubmitting;

  return (
    <Form {...form}>
      <FormLayout onSubmit={submit}>
        {generalError ? (
          <Alert variant="destructive">
            <AlertDescription>{generalError}</AlertDescription>
          </Alert>
        ) : null}

        <FormSection title="Personal information" description="Who this person is.">
          <TextField
            control={form.control}
            name="first_name"
            label="First name"
            required
            disabled={disabled}
          />
          <TextField control={form.control} name="last_name" label="Last name" required disabled={disabled} />
          <SelectField
            control={form.control}
            name="gender"
            label="Gender"
            options={GENDER_OPTIONS}
            disabled={disabled}
          />
          <TextField
            control={form.control}
            name="date_of_birth"
            label="Date of birth"
            type="date"
            disabled={disabled}
          />
          <SelectField
            control={form.control}
            name="blood_group"
            label="Blood group"
            options={BLOOD_GROUP_OPTIONS}
            description="Recorded for emergencies."
            disabled={disabled}
          />
          <SelectField
            control={form.control}
            name="marital_status"
            label="Marital status"
            options={MARITAL_STATUS_OPTIONS}
            disabled={disabled}
          />
          <TextField control={form.control} name="nationality" label="Nationality" disabled={disabled} />
          <TextField
            control={form.control}
            name="photo_url"
            label="Photo URL"
            placeholder="https://…"
            disabled={disabled}
          />
        </FormSection>

        <FormSection title="Contact information" description="Personal contact details and next of kin.">
          <TextField
            control={form.control}
            name="personal_email"
            label="Personal email"
            type="email"
            description="The address that survives offboarding."
            disabled={disabled}
          />
          <TextField
            control={form.control}
            name="mobile_number"
            label="Mobile number"
            type="tel"
            placeholder="+91 98765 43210"
            disabled={disabled}
          />
          <TextField
            control={form.control}
            name="alternate_number"
            label="Alternate number"
            type="tel"
            disabled={disabled}
          />
          <TextField
            control={form.control}
            name="emergency_contact_name"
            label="Emergency contact"
            disabled={disabled}
          />
          <TextField
            control={form.control}
            name="emergency_contact_number"
            label="Emergency contact number"
            type="tel"
            disabled={disabled}
          />
          <TextField
            control={form.control}
            name="emergency_contact_relationship"
            label="Relationship"
            placeholder="Mother, spouse…"
            disabled={disabled}
          />
        </FormSection>

        <FormSection title="Official information" description="How this person is reached at work.">
          <TextField
            control={form.control}
            name="official_email"
            label="Official email"
            type="email"
            description="Unique across employees."
            required
            disabled={disabled}
          />
          <TextField
            control={form.control}
            name="official_mobile"
            label="Official mobile"
            type="tel"
            disabled={disabled}
          />
          <TextField control={form.control} name="extension_number" label="Extension" disabled={disabled} />
          <SelectField
            control={form.control}
            name="work_mode"
            label="Work mode"
            options={WORK_MODE_OPTIONS}
            disabled={disabled}
          />
        </FormSection>

        <FormSection
          title="Employment"
          description="Where this person sits, and on what terms. Every reference is optional."
        >
          <TextField
            control={form.control}
            name="joining_date"
            label="Joining date"
            type="date"
            required
            disabled={disabled}
          />
          <SelectField
            control={form.control}
            name="employment_status"
            label="Employment status"
            options={STATUS_OPTIONS}
            required
            disabled={disabled}
          />

          {ORG_FIELDS.map((field) => (
            <OrganizationField
              key={field.name}
              control={form.control}
              name={field.name}
              label={field.label}
              master={field.master}
              disabled={disabled}
            />
          ))}

          <ManagerField control={form.control} disabled={disabled} excludeId={employee?.id} />
        </FormSection>

        <FormSection
          title="Compensation"
          description="Basic only. Payroll components arrive with the payroll module."
        >
          <TextField
            control={form.control}
            name="ctc"
            label="CTC"
            placeholder="1450000"
            description="Annual cost to company."
            disabled={disabled}
          />
          <OrganizationField
            control={form.control}
            name="salary_grade_id"
            label="Salary grade"
            master="grades"
            disabled={disabled}
          />
        </FormSection>

        <FormSection title="Notes">
          <TextareaField
            control={form.control}
            name="notes"
            label="Notes"
            rows={3}
            className="sm:col-span-2"
            disabled={disabled}
          />
          {isEdit ? (
            <TextField
              control={form.control}
              name="change_reason"
              label="Reason for change"
              description="Recorded against any employment-history entry this edit produces."
              className="sm:col-span-2"
              disabled={disabled}
            />
          ) : null}
        </FormSection>

        <FormActions
          submitLabel={isEdit ? 'Save changes' : 'Create employee'}
          isSubmitting={isSubmitting}
          isDirty={!isEdit || form.formState.isDirty}
          cancelHref={cancelHref}
        />
      </FormLayout>
    </Form>
  );
}
