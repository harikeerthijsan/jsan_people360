'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import * as React from 'react';
import { useForm, type Control, type DefaultValues, type FieldValues, type Resolver } from 'react-hook-form';

import { FormActions, FormLayout, FormSection } from '@/components/common/form-layout';
import { SelectField, type SelectOption } from '@/components/common/select-field';
import { TextField } from '@/components/common/text-field';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Checkbox } from '@/components/ui/checkbox';
import { Form, FormControl, FormField, FormItem, FormLabel } from '@/components/ui/form';
import { useMasterOptions } from '@/features/organization/hooks/use-masters';
import type { MasterSlug } from '@/features/organization/types/organization.types';
import { createUserSchema, editUserSchema } from '@/features/users/schemas/user.schemas';
import type { UserRecord } from '@/features/users/types/user.types';
import type { AppError } from '@/lib/errors';

const STATUS_OPTIONS: SelectOption[] = [
  { value: 'active', label: 'Active' },
  { value: 'inactive', label: 'Inactive' },
];

const GENDER_OPTIONS: SelectOption[] = [
  { value: 'male', label: 'Male' },
  { value: 'female', label: 'Female' },
  { value: 'other', label: 'Other' },
  { value: 'prefer_not_to_say', label: 'Prefer not to say' },
];

/** The eight organizational references, in hierarchy order. */
const ORG_FIELDS: { name: string; label: string; master: MasterSlug }[] = [
  { name: 'business_unit_id', label: 'Business unit', master: 'business-units' },
  { name: 'team_id', label: 'Team', master: 'teams' },
  { name: 'designation_id', label: 'Designation', master: 'designations' },
  { name: 'grade_id', label: 'Grade', master: 'grades' },
  { name: 'location_id', label: 'Location', master: 'locations' },
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

interface UserFormProps {
  /** Omit to create; supply to edit. */
  user?: UserRecord;
  isSubmitting: boolean;
  error: AppError | null;
  onSubmit: (values: FieldValues) => void;
  cancelHref: string;
}

/**
 * The multi-section user form, shared by create and edit.
 *
 * The only structural difference is the Account section: creating an account
 * needs an initial password, editing one does not -- setting someone else's
 * password is a separate, separately audited action.
 */
export function UserForm({
  user,
  isSubmitting,
  error,
  onSubmit,
  cancelHref,
}: UserFormProps): React.JSX.Element {
  const isEdit = user !== undefined;

  const defaults: FieldValues = React.useMemo(
    () => ({
      first_name: user?.first_name ?? '',
      last_name: user?.last_name ?? '',
      username: user?.username ?? '',
      email: user?.email ?? '',
      personal_email: user?.personal_email ?? '',
      phone_number: user?.phone_number ?? '',
      gender: user?.gender ?? undefined,
      date_of_birth: user?.date_of_birth ?? '',
      avatar_url: user?.avatar_url ?? '',
      business_unit_id: user?.business_unit_id ?? '',
      team_id: user?.team_id ?? '',
      designation_id: user?.designation_id ?? '',
      grade_id: user?.grade_id ?? '',
      location_id: user?.location_id ?? '',
      employment_type_id: user?.employment_type_id ?? '',
      joining_date: user?.joining_date ?? '',
      status: user?.status ?? 'active',
      ...(isEdit ? {} : { password: '', force_password_change: false }),
    }),
    [isEdit, user],
  );

  const form = useForm<FieldValues>({
    resolver: zodResolver(isEdit ? editUserSchema : createUserSchema) as Resolver<FieldValues>,
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

  // Field-scoped API errors (a duplicate email or username) attach to their
  // input; anything else falls through to the alert above the form.
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

        <FormSection
          title="Personal information"
          description="How this person is identified across the platform."
        >
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
          <TextField
            control={form.control}
            name="avatar_url"
            label="Profile photo URL"
            placeholder="https://…"
            className="sm:col-span-2"
            disabled={disabled}
          />
        </FormSection>

        <FormSection title="Contact information">
          <TextField
            control={form.control}
            name="email"
            label="Official email"
            type="email"
            description="Also the sign-in identifier."
            required
            disabled={disabled}
          />
          <TextField
            control={form.control}
            name="personal_email"
            label="Personal email"
            type="email"
            disabled={disabled}
          />
          <TextField
            control={form.control}
            name="phone_number"
            label="Mobile number"
            type="tel"
            placeholder="+91 98765 43210"
            disabled={disabled}
          />
        </FormSection>

        <FormSection
          title="Organization"
          description="Every field is optional and drawn from the organization master data."
        >
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
          <TextField
            control={form.control}
            name="joining_date"
            label="Joining date"
            type="date"
            disabled={disabled}
          />
        </FormSection>

        <FormSection title="Account">
          <TextField
            control={form.control}
            name="username"
            label="Username"
            description="Lower-case letters, digits, dots, hyphens and underscores."
            required
            disabled={disabled}
          />
          <SelectField
            control={form.control}
            name="status"
            label="Status"
            options={STATUS_OPTIONS}
            description="Inactive accounts cannot sign in."
            required
            disabled={disabled}
          />

          {isEdit ? null : (
            <>
              <TextField
                control={form.control}
                name="password"
                label="Initial password"
                type="password"
                description="At least 8 characters, with upper and lower case, a digit and a symbol."
                required
                disabled={disabled}
              />
              <FormField
                control={form.control}
                name="force_password_change"
                render={({ field }) => (
                  <FormItem className="flex flex-row items-center gap-2 space-y-0 sm:col-span-2">
                    <FormControl>
                      <Checkbox
                        checked={field.value === true}
                        onCheckedChange={(checked) => {
                          field.onChange(checked === true);
                        }}
                        disabled={disabled}
                      />
                    </FormControl>
                    <FormLabel className="text-muted-foreground cursor-pointer text-sm font-normal">
                      Require this person to choose their own password at first sign-in
                    </FormLabel>
                  </FormItem>
                )}
              />
            </>
          )}
        </FormSection>

        <FormActions
          submitLabel={isEdit ? 'Save changes' : 'Create user'}
          isSubmitting={isSubmitting}
          isDirty={!isEdit || form.formState.isDirty}
          cancelHref={cancelHref}
        />
      </FormLayout>
    </Form>
  );
}

/** Re-exported so pages need not import the router just to build a cancel link. */
export { STATUS_OPTIONS, GENDER_OPTIONS };
