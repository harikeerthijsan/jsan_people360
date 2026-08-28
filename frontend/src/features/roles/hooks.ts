'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult } from '@tanstack/react-query';

import { toast } from '@/components/ui/sonner';
import type { AppError } from '@/lib/errors';

import { rolesApi } from './api';

/**
 * Data hooks for role administration.
 *
 * Mutations invalidate the whole `roles` key *and* the session: changing what a
 * role grants can change what the person doing the changing may see, and a
 * sidebar still showing an area they just revoked from themselves is a bug
 * report waiting to happen.
 */

const root = ['roles'] as const;

export const usePermissionCatalogue = () =>
  useQuery({ queryKey: [...root, 'catalogue'], queryFn: () => rolesApi.catalogue() });

export const useRoles = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'list', params],
    queryFn: () => rolesApi.list({ page: 1, page_size: 100, ...params }),
  });

export const useRole = (id: string | undefined) =>
  useQuery({
    queryKey: [...root, 'detail', id ?? ''],
    queryFn: () => rolesApi.get(id ?? ''),
    enabled: Boolean(id),
  });

export const useUserRoles = (userId: string | undefined) =>
  useQuery({
    queryKey: [...root, 'user', userId ?? ''],
    queryFn: () => rolesApi.userRoles(userId ?? ''),
    enabled: Boolean(userId),
  });

function useRoleMutation<TVariables, TResult>(
  mutationFn: (variables: TVariables) => Promise<TResult>,
  labels: { done: string; failed: string },
): UseMutationResult<TResult, AppError, TVariables> {
  const queryClient = useQueryClient();

  return useMutation<TResult, AppError, TVariables>({
    mutationFn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: root });
      toast.success(labels.done);
    },
    onError: (error) => {
      // Verbatim: the server names the rule -- last Super Admin, role still in
      // use, system role -- and that sentence is the whole answer.
      toast.error(labels.failed, { description: error.message });
    },
  });
}

export const useCreateRole = () =>
  useRoleMutation((data: unknown) => rolesApi.create(data), {
    done: 'Role created',
    failed: 'Could not create this role',
  });

export const useUpdateRole = (id: string) =>
  useRoleMutation((data: unknown) => rolesApi.update(id, data), {
    done: 'Role updated',
    failed: 'Could not update this role',
  });

export const useDeleteRole = () =>
  useRoleMutation((id: string) => rolesApi.remove(id), {
    done: 'Role deleted',
    failed: 'Could not delete this role',
  });

export const useSetUserRoles = (userId: string) =>
  useRoleMutation((roleIds: string[]) => rolesApi.setUserRoles(userId, roleIds), {
    done: 'Roles updated',
    failed: 'Could not update these roles',
  });
