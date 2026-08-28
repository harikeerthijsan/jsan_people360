'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import * as React from 'react';
import { useForm } from 'react-hook-form';

import { FormActions, FormLayout, FormSection } from '@/components/common/form-layout';
import { TextField } from '@/components/common/text-field';
import { useAuth } from '@/components/providers/auth-provider';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Form } from '@/components/ui/form';
import { toast } from '@/components/ui/sonner';
import { usersApi } from '@/features/users/api/users.api';
import { profileSchema, type ProfileValues } from '@/features/users/schemas/user.schemas';
import type { AppError } from '@/lib/errors';
import { queryKeys } from '@/lib/query-client';
import type { UserRecord } from '@/types/user';

/**
 * Self-service profile editor.
 *
 * Only the three fields a user owns. Names, username, official email and
 * organizational placement are administrative: the API rejects them here, so
 * rendering them would be offering something that cannot work.
 */
export function ProfileForm(): React.JSX.Element {
  const { user, setUser } = useAuth();
  const queryClient = useQueryClient();

  const mutation = useMutation<UserRecord, AppError, ProfileValues>({
    mutationFn: (values) => usersApi.updateProfile(values),
    onSuccess: (updated) => {
      setUser(updated);
      queryClient.setQueryData(queryKeys.auth.currentUser(), updated);
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.root });
      toast.success('Profile updated');
    },
  });

  const form = useForm<ProfileValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      personal_email: user?.personal_email ?? '',
      phone_number: user?.phone_number ?? '',
      avatar_url: user?.avatar_url ?? '',
    },
  });

  const submit = form.handleSubmit((values) => {
    mutation.mutate(values, {
      onSuccess: () => {
        form.reset(values);
      },
    });
  });

  return (
    <Form {...form}>
      <FormLayout onSubmit={submit}>
        {mutation.isError ? (
          <Alert variant="destructive">
            <AlertDescription>{mutation.error.message}</AlertDescription>
          </Alert>
        ) : null}

        <FormSection
          title="Your details"
          description="Your name, username and official email are managed by an administrator."
          columns={1}
        >
          <TextField
            control={form.control}
            name="personal_email"
            label="Personal email"
            type="email"
            description="Used for correspondence that should not go to your work address."
            disabled={mutation.isPending}
          />
          <TextField
            control={form.control}
            name="phone_number"
            label="Mobile number"
            type="tel"
            placeholder="+91 98765 43210"
            disabled={mutation.isPending}
          />
          <TextField
            control={form.control}
            name="avatar_url"
            label="Profile photo URL"
            placeholder="https://…"
            disabled={mutation.isPending}
          />
        </FormSection>

        <FormActions
          submitLabel="Save changes"
          isSubmitting={mutation.isPending}
          isDirty={form.formState.isDirty}
          cancelHref="/profile"
        />
      </FormLayout>
    </Form>
  );
}
