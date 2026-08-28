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
import { Textarea } from '@/components/ui/textarea';

interface TextareaFieldProps<TFieldValues extends FieldValues> {
  control: Control<TFieldValues>;
  name: FieldPath<TFieldValues>;
  label: string;
  placeholder?: string;
  description?: string;
  rows?: number;
  required?: boolean;
  disabled?: boolean;
  className?: string;
}

/** A labelled, validated multi-line input bound to React Hook Form. */
export function TextareaField<TFieldValues extends FieldValues>({
  control,
  name,
  label,
  placeholder,
  description,
  rows = 3,
  required = false,
  disabled = false,
  className,
}: TextareaFieldProps<TFieldValues>): React.JSX.Element {
  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem className={className}>
          <FormLabel required={required}>{label}</FormLabel>
          <FormControl>
            <Textarea
              {...field}
              rows={rows}
              placeholder={placeholder}
              disabled={disabled}
              // RHF holds `undefined` for untouched fields; React needs a string
              // to keep the control from switching to uncontrolled.
              value={typeof field.value === 'string' ? field.value : ''}
            />
          </FormControl>
          {description ? <FormDescription>{description}</FormDescription> : null}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
