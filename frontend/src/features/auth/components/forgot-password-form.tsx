'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { CheckCircle2 } from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';
import { useForm } from 'react-hook-form';

import { TextField } from '@/components/common/text-field';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Form } from '@/components/ui/form';
import { routes } from '@/config/site';
import { useForgotPassword } from '@/features/auth/hooks/use-auth-mutations';
import { forgotPasswordSchema, type ForgotPasswordFormValues } from '@/features/auth/schemas/auth.schemas';
import { isProduction } from '@/lib/env';

/** Requests a password reset link. */
export function ForgotPasswordForm(): React.JSX.Element {
  const forgotPassword = useForgotPassword();

  const form = useForm<ForgotPasswordFormValues>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: '' },
  });

  const onSubmit = form.handleSubmit((values) => {
    forgotPassword.mutate(values.email);
  });

  // The endpoint returns 200 whether or not the address is registered, so the
  // UI must not imply that an account exists.
  if (forgotPassword.isSuccess) {
    const resetToken = forgotPassword.data.data?.reset_token ?? null;

    return (
      <div className="space-y-5">
        <Alert variant="success">
          <CheckCircle2 aria-hidden="true" />
          <AlertDescription>{forgotPassword.data.message}</AlertDescription>
        </Alert>

        {!isProduction && resetToken ? (
          <Alert variant="info">
            <AlertDescription className="space-y-2">
              <p className="font-medium">Development shortcut</p>
              <p className="text-xs">
                No mail server is configured, so the reset token is shown here. It will never appear in
                production.
              </p>
              <Link
                href={`${routes.resetPassword}?token=${encodeURIComponent(resetToken)}`}
                className="text-primary inline-block text-xs font-medium underline underline-offset-2"
              >
                Continue to reset your password
              </Link>
            </AlertDescription>
          </Alert>
        ) : null}

        <Button variant="outline" className="w-full" asChild>
          <Link href={routes.login}>Back to sign in</Link>
        </Button>
      </div>
    );
  }

  return (
    <Form {...form}>
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        {forgotPassword.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{forgotPassword.error.message}</AlertDescription>
          </Alert>
        ) : null}

        <TextField
          control={form.control}
          name="email"
          label="Email address"
          type="email"
          placeholder="you@company.com"
          autoComplete="email"
          description="We'll email you a link to choose a new password."
          required
          disabled={forgotPassword.isPending}
        />

        <Button type="submit" className="w-full" size="lg" isLoading={forgotPassword.isPending}>
          {forgotPassword.isPending ? 'Sending…' : 'Send reset link'}
        </Button>

        <Button variant="ghost" className="w-full" asChild>
          <Link href={routes.login}>Back to sign in</Link>
        </Button>
      </form>
    </Form>
  );
}
