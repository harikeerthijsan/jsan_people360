/**
 * The canonical user shape, mirroring the API's `UserRead`.
 *
 * It lives in shared types rather than inside a feature because two features
 * legitimately need it: `auth` for the signed-in session, and `users` for the
 * directory. Defining it in one of them would force the other to import across
 * a feature boundary, which the architecture rules out.
 */

import type { MasterSummary, RecordStatus } from '@/features/organization/types/organization.types';

export type Gender = 'male' | 'female' | 'other' | 'prefer_not_to_say';

export const GENDER_LABELS: Record<Gender, string> = {
  male: 'Male',
  female: 'Female',
  other: 'Other',
  prefer_not_to_say: 'Prefer not to say',
};

/** Organizational placement, resolved to names rather than bare ids. */
export interface UserOrganization {
  business_unit: MasterSummary | null;
  team: MasterSummary | null;
  designation: MasterSummary | null;
  grade: MasterSummary | null;
  location: MasterSummary | null;
  employment_type: MasterSummary | null;
}

export interface UserRecord {
  id: string;
  /** System-generated staff identifier (USR-000001). Never editable. */
  user_code: string;
  username: string;
  first_name: string;
  last_name: string;
  /** Derived by the server from the name parts; never stored. */
  full_name: string;

  email: string;
  personal_email: string | null;
  phone_number: string | null;
  avatar_url: string | null;
  gender: Gender | null;
  date_of_birth: string | null;

  business_unit_id: string | null;
  team_id: string | null;
  designation_id: string | null;
  grade_id: string | null;
  location_id: string | null;
  employment_type_id: string | null;
  joining_date: string | null;
  organization: UserOrganization;

  is_active: boolean;
  status: RecordStatus;
  is_superuser: boolean;
  force_password_change: boolean;
  is_locked: boolean;

  last_login_at: string | null;
  password_changed_at: string | null;

  created_at: string;
  updated_at: string;
  created_by: string | null;
  updated_by: string | null;
  /** Non-null when the account is archived. */
  deleted_at: string | null;
}

/** True when the account has been soft deleted. */
export function isArchived(user: Pick<UserRecord, 'deleted_at'>): boolean {
  return user.deleted_at !== null;
}
