'use client';

import Link from 'next/link';
import * as React from 'react';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';

interface FormSectionProps {
  title: string;
  description?: string;
  children: React.ReactNode;
  /** Lay the fields out in two columns from the `sm` breakpoint up. */
  columns?: 1 | 2;
  className?: string;
}

/**
 * A titled group of fields inside a card.
 *
 * Long forms are far easier to scan when related fields are grouped and
 * labelled, so every form in the product is built from these rather than a flat
 * stack of inputs.
 */
export function FormSection({
  title,
  description,
  children,
  columns = 2,
  className,
}: FormSectionProps): React.JSX.Element {
  return (
    <Card className={cn('animate-rise overflow-hidden', className)}>
      <CardHeader className="flex flex-row items-start gap-3 pb-4">
        <span className="bg-primary mt-1.5 size-2 shrink-0 rounded-full" aria-hidden="true" />
        <div className="space-y-1">
          <CardTitle className="text-base">{title}</CardTitle>
          {description ? <CardDescription>{description}</CardDescription> : null}
        </div>
      </CardHeader>
      <CardContent className="pt-1">
        <div className={cn('grid gap-x-6 gap-y-5', columns === 2 && 'sm:grid-cols-2')}>{children}</div>
      </CardContent>
    </Card>
  );
}

interface FormActionsProps {
  /** Label for the submit button. */
  submitLabel?: string;
  isSubmitting?: boolean;
  /** Disables submit until something has changed. */
  isDirty?: boolean;
  /** Where Cancel navigates to. */
  cancelHref: string;
  cancelLabel?: string;
  className?: string;
}

/**
 * The Cancel / Save pair, laid out identically on every form and kept in
 * view at the bottom of the viewport while a long form scrolls.
 *
 * Cancel is a link rather than a button so it behaves like navigation:
 * middle-click and "open in new tab" work, and it needs no handler.
 */
export function FormActions({
  submitLabel = 'Save',
  isSubmitting = false,
  isDirty = true,
  cancelHref,
  cancelLabel = 'Cancel',
  className,
}: FormActionsProps): React.JSX.Element {
  return (
    <div
      className={cn(
        'bg-background/85 sticky bottom-0 z-10 -mx-4 flex flex-col-reverse items-stretch gap-2 border-t px-4 py-3 backdrop-blur sm:mx-0 sm:flex-row sm:items-center sm:justify-end sm:rounded-2xl sm:border sm:px-4',
        className,
      )}
    >
      <Button variant="outline" asChild disabled={isSubmitting}>
        <Link href={cancelHref}>{cancelLabel}</Link>
      </Button>

      <Button type="submit" isLoading={isSubmitting} disabled={!isDirty}>
        {submitLabel}
      </Button>
    </div>
  );
}

interface FormLayoutProps {
  onSubmit: React.FormEventHandler<HTMLFormElement>;
  children: React.ReactNode;
  className?: string;
}

/** The outer `<form>` element, with consistent spacing. */
export function FormLayout({ onSubmit, children, className }: FormLayoutProps): React.JSX.Element {
  return (
    <form onSubmit={onSubmit} className={cn('space-y-6', className)} noValidate>
      {children}
    </form>
  );
}
