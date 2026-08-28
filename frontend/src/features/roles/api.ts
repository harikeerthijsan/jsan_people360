import { api } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';

import type { PermissionGroup, Role, UserRoles } from './types';

/** Transport for role and permission administration. */

const root = '/roles';

export const rolesApi = {
  catalogue: () => api.get<PermissionGroup[]>(`${root}/permissions`),
  reconcile: () => api.post<{ detail: string }>(`${root}/permissions/reconcile`),

  list: (params: Record<string, unknown>) => api.get<Page<Role>>(root, { params }),
  get: (id: string) => api.get<Role>(`${root}/${id}`),
  create: (data: unknown) => api.post<Role>(root, data),
  update: (id: string, data: unknown) => api.patch<Role>(`${root}/${id}`, data),
  remove: (id: string) => api.delete<{ detail: string }>(`${root}/${id}`),

  userRoles: (userId: string) => api.get<UserRoles>(`/users/${userId}/roles`),
  setUserRoles: (userId: string, roleIds: string[]) =>
    api.put<UserRoles>(`/users/${userId}/roles`, { role_ids: roleIds }),
};
