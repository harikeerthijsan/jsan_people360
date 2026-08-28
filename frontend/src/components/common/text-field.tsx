'use client';

import { Eye, EyeOff } from 'lucide-react';
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
import { cn } from '@/lib/utils';

interface TextFieldProps<TFieldValues extends FieldValues> {
  control: Control<TFieldValues>;
  name: FieldPath<TFieldValues>;
  label: string;
  placeholder?: string;
  description?: string;
  type?: React.HTMLInputTypeAttribute;
  autoComplete?: string;
  required?: boolean;
  disabled?: boolean;
  className?: string;
}

/**
 * A labelled, validated text input bound to React Hook Form.
 *
 * This is the field every form should use: it wires label, description, error
 * message and ARIA attributes together, so a screen only declares intent.
 * Password fields additionally get a show/hide toggle.
 */
export function TextField<TFieldValues extends FieldValues>({
  control,
  name,
  label,
  placeholder,
  description,
  type = 'text',
  autoComplete,
  required = false,
  disabled = false,
  className,
}: TextFieldProps<TFieldValues>): React.JSX.Element {
  const [isRevealed, setIsRevealed] = React.useState(false);
  const isPassword = type === 'password';
  const resolvedType = isPassword && isRevealed ? 'text' : type;

  return (
    <FormField
      control={control}
      name={name}
      render={({ field }) => (
        <FormItem className={className}>
          <FormLabel required={required}>{label}</FormLabel>

          <div className="relative">
            <FormControl>
              <Input
                {...field}
                type={resolvedType}
                placeholder={placeholder}
                autoComplete={autoComplete}
                disabled={disabled}
                className={cn(isPassword && 'pr-10')}
                // RHF holds `undefined` for untouched fields; React needs a string
                // to keep the input controlled from the first render.
                value={field.value ?? ''}
              />
            </FormControl>

            {isPassword ? (
              <button
                type="button"
                onClick={() => {
                  setIsRevealed((previous) => !previous);
                }}
                className="text-muted-foreground hover:text-foreground focus-visible:ring-ring absolute top-0 right-0 flex h-9 w-10 items-center justify-center transition-colors focus-visible:ring-2 focus-visible:outline-none"
                aria-label={isRevealed ? 'Hide password' : 'Show password'}
                tabIndex={-1}
              >
                {isRevealed ? (
                  <EyeOff className="size-4" aria-hidden="true" />
                ) : (
                  <Eye className="size-4" aria-hidden="true" />
                )}
              </button>
            ) : null}
          </div>

          {description ? <FormDescription>{description}</FormDescription> : null}
          <FormMessage />
        </FormItem>
      )}
    />
  );
}
