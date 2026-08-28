'use client';

import * as React from 'react';
import type { Control } from 'react-hook-form';

import { NumberField } from '@/components/common/number-field';
import { SelectField, type SelectOption } from '@/components/common/select-field';
import { TextField } from '@/components/common/text-field';
import { TextareaField } from '@/components/common/textarea-field';
import type { MasterFieldConfig } from '@/features/organization/config/master-registry';
import { useMasterOptions } from '@/features/organization/hooks/use-masters';
import type { MasterFormValues } from '@/features/organization/types/organization.types';

interface MasterFormFieldProps {
  field: MasterFieldConfig;
  control: Control<MasterFormValues>;
  disabled?: boolean;
}

/**
 * Renders one configured field.
 *
 * The switch is the single place that maps a field *type* onto a component, so
 * every master's form is built from the same field implementations and picks up
 * their validation, ARIA wiring and error display for free.
 */
export function MasterFormField({
  field,
  control,
  disabled = false,
}: MasterFormFieldProps): React.JSX.Element {
  const className = field.wide === true ? 'sm:col-span-2' : undefined;

  // Only fires a request when the field actually is a reference; the hook is
  // disabled otherwise, so this respects the rules of hooks without fetching.
  const referenceQuery = useMasterOptions(field.type === 'reference' ? field.referenceMaster : undefined);

  switch (field.type) {
    case 'textarea':
      return (
        <TextareaField
          control={control}
          name={field.name}
          label={field.label}
          placeholder={field.placeholder}
          description={field.description}
          rows={field.rows}
          required={field.required}
          disabled={disabled}
          className={className}
        />
      );

    case 'number':
      return (
        <NumberField
          control={control}
          name={field.name}
          label={field.label}
          placeholder={field.placeholder}
          description={field.description}
          min={field.min}
          max={field.max}
          required={field.required}
          disabled={disabled}
          className={className}
        />
      );

    case 'select':
      return (
        <SelectField
          control={control}
          name={field.name}
          label={field.label}
          options={field.options ?? []}
          description={field.description}
          required={field.required}
          disabled={disabled}
          className={className}
        />
      );

    case 'reference': {
      const options: SelectOption[] = (referenceQuery.data?.items ?? []).map((record) => ({
        value: record.id,
        label: record.name,
        hint: record.code,
      }));

      return (
        <SelectField
          control={control}
          name={field.name}
          label={field.label}
          options={options}
          description={field.description}
          required={field.required}
          disabled={disabled}
          isLoading={referenceQuery.isPending}
          emptyMessage={`No active ${field.label.toLowerCase()} to choose from`}
          className={className}
        />
      );
    }

    case 'text':
      return (
        <TextField
          control={control}
          name={field.name}
          label={field.label}
          placeholder={field.placeholder}
          description={field.description}
          required={field.required}
          disabled={disabled}
          className={className}
        />
      );
  }
}
