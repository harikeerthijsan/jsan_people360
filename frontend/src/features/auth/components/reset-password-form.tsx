'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { CheckCircle2 } from 'lucide-react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import * as React from 'react';
import { useForm } from 'react-hook-form';

import { TextField } from '@/components/common/text-field';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Form } from '@/components/ui/form';
import { routes } from '@/config/site';
import { useResetPassword } from '@/features/auth/hooks/use-auth-mutations';
import { resetPasswordSchema, type ResetPasswordFormValues } from '@/features/auth/schemas/auth.schemas';

/** Sets a new password using the token from the emailed reset link. */
export function ResetPasswordForm(): React.JSX.Element {
  const searchParams = useSearchParams();
  const token = searchParams.get('token') ?? '';
  const resetPassword = useResetPassword();

  const form = useForm<ResetPasswordFormValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: { token, new_password: '', confirm_password: '' },
  });

  // The token arrives in the URL, so it is registered as a hidden field value
  // rather than a rendered input.
  React.useEffect(() => {
    form.setValue('token', token);
  }, [form, token]);

  const onSubmit = form.handleSubmit((values) => {
    resetPassword.mutate(values);
  });

  if (!token) {
    return (
      <div className="space-y-5">
        <Alert variant="destructive">
          <AlertDescription>
            This password reset link is incomplete. Request a new one to continue.
          </AlertDescription>
        </Alert>
        <Button className="w-full" asChild>
          <Link href={routes.forgotPassword}>Request a new link</Link>
        </Button>
      </div>
    );
  }

  if (resetPassword.isSuccess) {
    return (
      <div className="space-y-5">
        <Alert variant="success">
          <CheckCircle2 aria-hidden="true" />
          <AlertDescription>{resetPassword.data.detail}</AlertDescription>
        </Alert>
        <Button className="w-full" size="lg" asChild>
          <Link href={routes.login}>Continue to sign in</Link>
        </Button>
      </div>
    );
  }

  return (
    <Form {...form}>
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        {resetPassword.isError ? (
          <Alert variant="destructive">
            <AlertDescription className="space-y-2">
              <p>{resetPassword.error.message}</p>
              <Link
                href={routes.forgotPassword}
                className="inline-block text-xs font-medium underline underline-offset-2"
              >
                Request a new reset link
              </Link>
            </AlertDescription>
          </Alert>
        ) : null}

        <TextField
          control={form.control}
          name="new_password"
          label="New password"
          type="password"
          autoComplete="new-password"
          description="At least 10 characters, with upper and lower case, a digit and a symbol."
          required
          disabled={resetPassword.isPending}
        />

        <TextField
          control={form.control}
          name="confirm_password"
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
          required
          disabled={resetPassword.isPending}
        />

        <Button type="submit" className="w-full" size="lg" isLoading={resetPassword.isPending}>
          {resetPassword.isPending ? 'Updating…' : 'Set new password'}
        </Button>
      </form>
    </Form>
  );
}
