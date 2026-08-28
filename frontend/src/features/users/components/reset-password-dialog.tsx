'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import * as React from 'react';
import { useForm } from 'react-hook-form';

import { Modal } from '@/components/common/modal';
import { TextField } from '@/components/common/text-field';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Form, FormControl, FormField, FormItem, FormLabel } from '@/components/ui/form';
import { useResetUserPassword } from '@/features/users/hooks/use-users';
import { resetPasswordSchema, type ResetPasswordValues } from '@/features/users/schemas/user.schemas';
import type { UserRecord } from '@/features/users/types/user.types';

interface ResetPasswordDialogProps {
  user: UserRecord;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

/** An administrator setting another user's password. */
export function ResetPasswordDialog({
  user,
  open,
  onOpenChange,
}: ResetPasswordDialogProps): React.JSX.Element {
  const mutation = useResetUserPassword();

  const form = useForm<ResetPasswordValues>({
    resolver: zodResolver(resetPasswordSchema),
    defaultValues: {
      new_password: '',
      confirm_password: '',
      // Safe defaults: a reset is usually a response to a lost or compromised
      // password, so the user must choose their own and existing sessions end.
      force_password_change: true,
      revoke_sessions: true,
    },
  });

  // Clear the typed password whenever the dialog closes, so it is not sitting
  // in memory or waiting to reappear the next time it is opened.
  React.useEffect(() => {
    if (!open) form.reset();
  }, [form, open]);

  const submit = form.handleSubmit((values) => {
    mutation.mutate(
      {
        id: user.id,
        payload: {
          new_password: values.new_password,
          force_password_change: values.force_password_change,
          revoke_sessions: values.revoke_sessions,
        },
      },
      {
        onSuccess: () => {
          onOpenChange(false);
        },
        onError: (error) => {
          for (const [field, message] of Object.entries(error.fieldErrorMap)) {
            if (field === 'new_password') {
              form.setError('new_password', { type: 'server', message });
            }
          }
        },
      },
    );
  });

  const generalError =
    mutation.error && Object.keys(mutation.error.fieldErrorMap).length === 0 ? mutation.error.message : null;

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title="Reset password"
      description={`Set a new password for ${user.full_name} (${user.user_code}).`}
      footer={
        <div className="flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
          <Button
            variant="outline"
            onClick={() => {
              onOpenChange(false);
            }}
            disabled={mutation.isPending}
          >
            Cancel
          </Button>
          <Button onClick={submit} isLoading={mutation.isPending}>
            Reset password
          </Button>
        </div>
      }
    >
      <Form {...form}>
        <form onSubmit={submit} className="space-y-4" noValidate>
          {generalError ? (
            <Alert variant="destructive">
              <AlertDescription>{generalError}</AlertDescription>
            </Alert>
          ) : null}

          <TextField
            control={form.control}
            name="new_password"
            label="New password"
            type="password"
            description="At least 8 characters, with upper and lower case, a digit and a symbol."
            required
            disabled={mutation.isPending}
          />
          <TextField
            control={form.control}
            name="confirm_password"
            label="Confirm new password"
            type="password"
            required
            disabled={mutation.isPending}
          />

          <FormField
            control={form.control}
            name="force_password_change"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center gap-2 space-y-0">
                <FormControl>
                  <Checkbox
                    checked={field.value === true}
                    onCheckedChange={(checked) => {
                      field.onChange(checked === true);
                    }}
                    disabled={mutation.isPending}
                  />
                </FormControl>
                <FormLabel className="text-muted-foreground cursor-pointer text-sm font-normal">
                  Require a new password at their next sign-in
                </FormLabel>
              </FormItem>
            )}
          />

          <FormField
            control={form.control}
            name="revoke_sessions"
            render={({ field }) => (
              <FormItem className="flex flex-row items-center gap-2 space-y-0">
                <FormControl>
                  <Checkbox
                    checked={field.value === true}
                    onCheckedChange={(checked) => {
                      field.onChange(checked === true);
                    }}
                    disabled={mutation.isPending}
                  />
                </FormControl>
                <FormLabel className="text-muted-foreground cursor-pointer text-sm font-normal">
                  Sign them out of every active session
                </FormLabel>
              </FormItem>
            )}
          />
        </form>
      </Form>
    </Modal>
  );
}
