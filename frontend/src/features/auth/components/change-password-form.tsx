'use client';

import * as React from 'react';
import { zodResolver } from '@hookform/resolvers/zod';
import { useForm } from 'react-hook-form';

import { TextField } from '@/components/common/text-field';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Form } from '@/components/ui/form';
import { toast } from '@/components/ui/sonner';
import { useAuth } from '@/components/providers/auth-provider';
import { useChangePassword } from '@/features/auth/hooks/use-auth-mutations';
import { changePasswordSchema, type ChangePasswordFormValues } from '@/features/auth/schemas/auth.schemas';

/**
 * Changes the signed-in user's password.
 *
 * The backend revokes every session on success, so the user is signed out
 * immediately afterwards and must authenticate again.
 */
export function ChangePasswordForm(): React.JSX.Element {
  const { logout } = useAuth();
  const changePassword = useChangePassword();

  const form = useForm<ChangePasswordFormValues>({
    resolver: zodResolver(changePasswordSchema),
    defaultValues: { current_password: '', new_password: '', confirm_password: '' },
  });

  const onSubmit = form.handleSubmit((values) => {
    changePassword.mutate(values, {
      onSuccess: (result) => {
        toast.success('Password changed', { description: result.detail });
        form.reset();
        void logout();
      },
      onError: (error) => {
        const message = error.fieldErrorMap['current_password'];
        if (error.status === 401) {
          form.setError('current_password', {
            type: 'server',
            message: message ?? 'Your current password is incorrect.',
          });
        }
      },
    });
  });

  const generalError =
    changePassword.error && changePassword.error.status !== 401 ? changePassword.error.message : null;

  return (
    <Form {...form}>
      <form onSubmit={onSubmit} className="max-w-md space-y-5" noValidate>
        {generalError ? (
          <Alert variant="destructive">
            <AlertDescription>{generalError}</AlertDescription>
          </Alert>
        ) : null}

        <Alert variant="info">
          <AlertDescription className="text-xs">
            Changing your password signs you out of every device, including this one.
          </AlertDescription>
        </Alert>

        <TextField
          control={form.control}
          name="current_password"
          label="Current password"
          type="password"
          autoComplete="current-password"
          required
          disabled={changePassword.isPending}
        />

        <TextField
          control={form.control}
          name="new_password"
          label="New password"
          type="password"
          autoComplete="new-password"
          description="At least 10 characters, with upper and lower case, a digit and a symbol."
          required
          disabled={changePassword.isPending}
        />

        <TextField
          control={form.control}
          name="confirm_password"
          label="Confirm new password"
          type="password"
          autoComplete="new-password"
          required
          disabled={changePassword.isPending}
        />

        <Button type="submit" isLoading={changePassword.isPending}>
          {changePassword.isPending ? 'Updating…' : 'Change password'}
        </Button>
      </form>
    </Form>
  );
}
