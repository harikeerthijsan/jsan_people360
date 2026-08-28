/**
 * Domain types for the User Management module.
 *
 * The record shape itself lives in shared types because the auth feature needs
 * it too; only the query shape is specific to this module.
 */

import type { RecordStatus } from '@/features/organization/types/organization.types';

export type { Gender, UserOrganization, UserRecord } from '@/types/user';
export { GENDER_LABELS, isArchived } from '@/types/user';

/** Query parameters accepted by the user list endpoint. */
export interface UserListQuery {
  page: number;
  page_size: number;
  search?: string;
  status?: RecordStatus;
  archived: boolean;
  sort_by: string;
  sort_order: 'asc' | 'desc';
  business_unit_id?: string;
  designation_id?: string;
  location_id?: string;
}
