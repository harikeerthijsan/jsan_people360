'use client';

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseMutationResult,
  type UseQueryResult,
} from '@tanstack/react-query';

import { toast } from '@/components/ui/sonner';
import { usersApi, type ResetPasswordPayload } from '@/features/users/api/users.api';
import type { UserListQuery, UserRecord } from '@/features/users/types/user.types';
import type { Page } from '@/lib/api/types';
import type { AppError } from '@/lib/errors';
import { queryKeys } from '@/lib/query-client';

/**
 * Data hooks for the user-management screens.
 *
 * Lifecycle actions share one mutation factory so the cache invalidation and
 * the failure toast behave identically for all four, rather than being
 * re-implemented per action with slightly different bugs.
 */

export function useUserList(query: UserListQuery): UseQueryResult<Page<UserRecord>, AppError> {
  return useQuery<Page<UserRecord>, AppError>({
    queryKey: queryKeys.users.list(query),
    queryFn: () => usersApi.list(query),
    // Keeps the previous page on screen while the next loads, so paging and
    // typing in the search box do not blank the table.
    placeholderData: (previous) => previous,
  });
}

export function useUser(id: string | undefined): UseQueryResult<UserRecord, AppError> {
  return useQuery<UserRecord, AppError>({
    queryKey: queryKeys.users.detail(id ?? ''),
    queryFn: () => usersApi.get(id ?? ''),
    enabled: Boolean(id),
  });
}

export function useCreateUser(): UseMutationResult<UserRecord, AppError, unknown> {
  const queryClient = useQueryClient();

  return useMutation<UserRecord, AppError, unknown>({
    mutationFn: (values) => usersApi.create(values),
    onSuccess: (user) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.root });
      toast.success('User created', { description: `${user.full_name} · ${user.user_code}` });
    },
  });
}

export function useUpdateUser(id: string): UseMutationResult<UserRecord, AppError, unknown> {
  const queryClient = useQueryClient();

  return useMutation<UserRecord, AppError, unknown>({
    mutationFn: (values) => usersApi.update(id, values),
    onSuccess: (user) => {
      queryClient.setQueryData(queryKeys.users.detail(user.id), user);
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.root });
      toast.success('User updated', { description: user.full_name });
    },
  });
}

type LifecycleAction = 'activate' | 'deactivate' | 'archive' | 'restore';

const LIFECYCLE_LABELS: Record<LifecycleAction, { done: string; failed: string }> = {
  activate: { done: 'User activated', failed: 'Could not activate this user' },
  deactivate: { done: 'User deactivated', failed: 'Could not deactivate this user' },
  archive: { done: 'User archived', failed: 'Could not archive this user' },
  restore: { done: 'User restored', failed: 'Could not restore this user' },
};

/**
 * Activate, deactivate, archive or restore an account.
 *
 * The failure toast shows the server's message verbatim: these actions are
 * refused for specific, actionable reasons -- the last active account, a user
 * who still manages a team -- and a generic "something went wrong" would hide
 * exactly the part the administrator needs.
 */
export function useUserLifecycleAction(
  action: LifecycleAction,
): UseMutationResult<UserRecord, AppError, string> {
  const queryClient = useQueryClient();
  const labels = LIFECYCLE_LABELS[action];

  return useMutation<UserRecord, AppError, string>({
    mutationFn: (id) => usersApi[action](id),
    onSuccess: (user) => {
      queryClient.setQueryData(queryKeys.users.detail(user.id), user);
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.root });
      toast.success(labels.done, { description: user.full_name });
    },
    onError: (error) => {
      toast.error(labels.failed, { description: error.message });
    },
  });
}

interface ResetPasswordArgs {
  id: string;
  payload: ResetPasswordPayload;
}

export function useResetUserPassword(): UseMutationResult<UserRecord, AppError, ResetPasswordArgs> {
  const queryClient = useQueryClient();

  return useMutation<UserRecord, AppError, ResetPasswordArgs>({
    mutationFn: ({ id, payload }) => usersApi.resetPassword(id, payload),
    onSuccess: (user) => {
      queryClient.setQueryData(queryKeys.users.detail(user.id), user);
      void queryClient.invalidateQueries({ queryKey: queryKeys.users.root });
      toast.success('Password reset', {
        description: user.force_password_change
          ? `${user.full_name} must choose a new password at their next sign-in.`
          : user.full_name,
      });
    },
  });
}
