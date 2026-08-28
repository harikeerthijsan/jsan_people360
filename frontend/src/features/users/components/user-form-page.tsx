'use client';

import { useRouter } from 'next/navigation';
import * as React from 'react';
import type { FieldValues } from 'react-hook-form';

import { ErrorState } from '@/components/common/error-state';
import { FormSkeleton } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { UserForm } from '@/features/users/components/user-form';
import { useCreateUser, useUpdateUser, useUser } from '@/features/users/hooks/use-users';

const BASE_PATH = '/users';

/** The create screen. */
export function UserCreatePage(): React.JSX.Element {
  const router = useRouter();
  const mutation = useCreateUser();

  return (
    <div className="space-y-6">
      <PageHeader
        title="New user"
        description="Provision an account. The staff code is generated automatically."
      />
      <UserForm
        isSubmitting={mutation.isPending}
        error={mutation.error}
        cancelHref={BASE_PATH}
        onSubmit={(values: FieldValues) => {
          mutation.mutate(values, {
            onSuccess: (created) => {
              router.push(`${BASE_PATH}/${created.id}`);
            },
          });
        }}
      />
    </div>
  );
}

/** The edit screen, reusing the same form. */
export function UserEditPage({ userId }: { userId: string }): React.JSX.Element {
  const router = useRouter();
  const query = useUser(userId);
  const mutation = useUpdateUser(userId);

  if (query.isPending) {
    return (
      <div className="space-y-6">
        <PageHeader title="Edit user" />
        <FormSkeleton fields={6} />
      </div>
    );
  }

  if (query.isError) {
    return (
      <div className="space-y-6">
        <PageHeader title="Edit user" />
        <ErrorState
          error={query.error}
          onRetry={() => {
            void query.refetch();
          }}
        />
      </div>
    );
  }

  const user = query.data;
  const isArchived = user.deleted_at !== null;

  return (
    <div className="space-y-6">
      <PageHeader title={`Edit ${user.full_name}`} description={user.user_code} />

      {isArchived ? (
        <Alert variant="warning">
          <AlertDescription>
            This account is archived and cannot be edited. Restore it first.
          </AlertDescription>
        </Alert>
      ) : (
        <UserForm
          user={user}
          isSubmitting={mutation.isPending}
          error={mutation.error}
          cancelHref={`${BASE_PATH}/${user.id}`}
          onSubmit={(values: FieldValues) => {
            mutation.mutate(values, {
              onSuccess: (updated) => {
                router.push(`${BASE_PATH}/${updated.id}`);
              },
            });
          }}
        />
      )}
    </div>
  );
}
