'use client';

import * as React from 'react';
import type { Control, FieldPath, FieldValues } from 'react-hook-form';

import {
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';

interface NumberFieldProps<TFieldValues extends FieldValues> {
  control: Control<TFieldValues>;
  name: FieldPath<TFieldValues>;
  label: string;
  placeholder?: string;
  description?: string;
  min?: number;
  max?: number;
  required?: boolean;
  disabled?: boolean;
  className?: string;
}

/**
 * A labelled, validated numeric input bound to React Hook Form.
 *
 * A native number input reports its value as a string, and an empty field as
 * `""`. Both are converted here so the form state holds a real `number` or
 * `undefined` — otherwise Zod's `number()` rejects a perfectly valid entry.
 */
export function NumberField<TFieldValues extends FieldValues>({
  control,
  name,
  label,
  placeholder,
  description,
  min,
  max,
  required = false,
  disabled = false,
  className,
}: NumberFieldProps<TFieldValues>): React.JSX.Element {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem className={className}>
          <FormLabel required={required}>{label}</FormLabel>
          <FormControl>
            <Input
              type="number"
              inputMode="numeric"
              min={min}
              max={max}
              placeholder={placeholder}
              disabled={disabled}
              name={field.name}
              ref={field.ref}
              onBlur={field.onBlur}
              value={typeof field.value === 'number' ? String(field.value) : ''}
              onChange={(event) => {
                const raw = event.target.value;
                field.onChange(raw === '' ? undefined : Number(raw));
              }}
            />
          </FormControl>
          {description ? <FormDescription>{description}</FormDescription> : null}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
