import * as React from 'react';

import { cn } from '@/lib/utils';

export type InputProps = React.InputHTMLAttributes<HTMLInputElement>;

const Input = React.forwardRef<HTMLInputElement, InputProps>(({ className, type, ...props }, ref) => (
  <input
    type={type}
    ref={ref}
    className={cn(
      'border-input bg-muted/60 flex h-11 w-full rounded-xl border border-transparent px-3.5 py-1 text-sm transition-[background-color,border-color,box-shadow] duration-200 hover:bg-muted focus:bg-background focus:border-input',
      'placeholder:text-muted-foreground',
      'focus-visible:ring-ring focus-visible:ring-2 focus-visible:ring-offset-1 focus-visible:outline-none',
      'disabled:cursor-not-allowed disabled:opacity-50',
      'file:border-0 file:bg-transparent file:text-sm file:font-medium',
      // `aria-invalid` is set by the form field wrapper, so error styling is
      // driven by the accessibility attribute rather than a parallel prop.
      'aria-[invalid=true]:border-destructive aria-[invalid=true]:focus-visible:ring-destructive',
      className,
    )}
    {...props}
  />
));
Input.displayName = 'Input';

export { Input };
