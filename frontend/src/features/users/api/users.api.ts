import { api } from '@/lib/api/client';
import { endpoints } from '@/lib/api/endpoints';
import type { Page } from '@/lib/api/types';
import type { UserListQuery, UserRecord } from '@/features/users/types/user.types';

/** Transport for the user-management endpoints. */

function toQueryParams(query: UserListQuery): Record<string, string> {
  const params: Record<string, string> = {
    page: String(query.page),
    page_size: String(query.page_size),
    sort_by: query.sort_by,
    sort_order: query.sort_order,
    archived: String(query.archived),
  };

  if (query.search) params['search'] = query.search;
  if (query.status) params['status'] = query.status;
  if (query.business_unit_id) params['business_unit_id'] = query.business_unit_id;
  if (query.designation_id) params['designation_id'] = query.designation_id;
  if (query.location_id) params['location_id'] = query.location_id;

  return params;
}

export interface ResetPasswordPayload {
  new_password: string;
  force_password_change: boolean;
  revoke_sessions: boolean;
}

export const usersApi = {
  list: (query: UserListQuery): Promise<Page<UserRecord>> =>
    api.get<Page<UserRecord>>(endpoints.users.root, { params: toQueryParams(query) }),

  get: (id: string): Promise<UserRecord> => api.get<UserRecord>(`${endpoints.users.root}/${id}`),

  create: (values: unknown): Promise<UserRecord> => api.post<UserRecord>(endpoints.users.root, values),

  update: (id: string, values: unknown): Promise<UserRecord> =>
    api.patch<UserRecord>(`${endpoints.users.root}/${id}`, values),

  activate: (id: string): Promise<UserRecord> =>
    api.post<UserRecord>(`${endpoints.users.root}/${id}/activate`),

  deactivate: (id: string): Promise<UserRecord> =>
    api.post<UserRecord>(`${endpoints.users.root}/${id}/deactivate`),

  archive: (id: string): Promise<UserRecord> => api.post<UserRecord>(`${endpoints.users.root}/${id}/archive`),

  restore: (id: string): Promise<UserRecord> => api.post<UserRecord>(`${endpoints.users.root}/${id}/restore`),

  resetPassword: (id: string, payload: ResetPasswordPayload): Promise<UserRecord> =>
    api.post<UserRecord>(`${endpoints.users.root}/${id}/reset-password`, payload),

  // -- Self service ---------------------------------------------------
  me: (): Promise<UserRecord> => api.get<UserRecord>(endpoints.users.me),

  updateProfile: (values: unknown): Promise<UserRecord> => api.patch<UserRecord>(endpoints.users.me, values),
};
