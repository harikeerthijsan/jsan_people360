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
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Spinner } from '@/components/common/loading-state';

export interface SelectOption {
  value: string;
  label: string;
  /** Shown beneath the label, e.g. a parent's name. */
  hint?: string;
  disabled?: boolean;
}

interface SelectFieldProps<TFieldValues extends FieldValues> {
  control: Control<TFieldValues>;
  name: FieldPath<TFieldValues>;
  label: string;
  options: SelectOption[];
  placeholder?: string;
  description?: string;
  required?: boolean;
  disabled?: boolean;
  /** Show a spinner and block interaction while options load. */
  isLoading?: boolean;
  /** Message shown in place of the list when there is nothing to choose. */
  emptyMessage?: string;
  className?: string;
}

/**
 * A labelled, validated select bound to React Hook Form.
 *
 * Handles the states a naive select forgets: options still loading, and no
 * options at all. Rendering an empty dropdown in either case leaves the user
 * unable to tell whether the data is missing or merely slow.
 */
export function SelectField<TFieldValues extends FieldValues>({
  control,
  name,
  label,
  options,
  placeholder = 'Select…',
  description,
  required = false,
  disabled = false,
  isLoading = false,
  emptyMessage = 'No options available',
  className,
}: SelectFieldProps<TFieldValues>): React.JSX.Element {
  const hasOptions = options.length > 0;

  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem className={className}>
          <FormLabel required={required}>{label}</FormLabel>

          <Select
            value={typeof field.value === 'string' ? field.value : ''}
            onValueChange={field.onChange}
            disabled={disabled || isLoading || !hasOptions}
          >
            <FormControl>
              <SelectTrigger>
                {isLoading ? (
                  <span className="text-muted-foreground flex items-center gap-2 text-sm">
                    <Spinner label="Loading options" />
                    Loading…
                  </span>
                ) : (
                  <SelectValue placeholder={hasOptions ? placeholder : emptyMessage} />
                )}
              </SelectTrigger>
            </FormControl>

            <SelectContent>
              {options.map((option) => (
                <SelectItem key={option.value} value={option.value} disabled={option.disabled}>
                  <span className="flex flex-col items-start">
                    <span>{option.label}</span>
                    {option.hint ? (
                      <span className="text-muted-foreground text-xs">{option.hint}</span>
                    ) : null}
                  </span>
                </SelectItem>
              ))}
            </SelectContent>
          </Select>

          {description ? <FormDescription>{description}</FormDescription> : null}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
