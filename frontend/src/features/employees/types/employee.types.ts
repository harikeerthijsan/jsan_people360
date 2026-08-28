/**
 * Domain types for the Employee Management module, mirroring the API's schemas.
 *
 * Unlike `UserRecord`, this lives inside the feature: nothing outside
 * `features/employees` needs the shape, and moving it to shared types before a
 * second consumer exists would be speculative.
 */

import type { MasterSummary } from '@/features/organization/types/organization.types';
import type { Gender } from '@/types/user';

export type { Gender };

export type EmploymentStatus =
  'probation' | 'confirmed' | 'active' | 'notice_period' | 'resigned' | 'inactive';

export type WorkMode = 'office' | 'remote' | 'hybrid';

export type MaritalStatus = 'single' | 'married' | 'divorced' | 'widowed' | 'separated';

export type BloodGroup = 'A+' | 'A-' | 'B+' | 'B-' | 'AB+' | 'AB-' | 'O+' | 'O-';

export type AddressType = 'current' | 'permanent';

export type EmploymentChangeType =
  | 'created'
  | 'confirmation'
  | 'promotion'
  | 'team_transfer'
  | 'designation_change'
  | 'grade_change'
  | 'manager_change'
  | 'location_change'
  | 'status_change'
  | 'details_updated';

/**
 * Ordered as the lifecycle runs, so a status filter reads in a sensible order
 * rather than alphabetically.
 */
export const EMPLOYMENT_STATUSES: readonly EmploymentStatus[] = [
  'probation',
  'confirmed',
  'active',
  'notice_period',
  'resigned',
  'inactive',
] as const;

export const EMPLOYMENT_STATUS_LABELS: Record<EmploymentStatus, string> = {
  probation: 'Probation',
  confirmed: 'Confirmed',
  active: 'Active',
  notice_period: 'Notice period',
  resigned: 'Resigned',
  inactive: 'Inactive',
};

export const WORK_MODE_LABELS: Record<WorkMode, string> = {
  office: 'Office',
  remote: 'Remote',
  hybrid: 'Hybrid',
};

export const MARITAL_STATUS_LABELS: Record<MaritalStatus, string> = {
  single: 'Single',
  married: 'Married',
  divorced: 'Divorced',
  widowed: 'Widowed',
  separated: 'Separated',
};

export const BLOOD_GROUPS: readonly BloodGroup[] = [
  'A+',
  'A-',
  'B+',
  'B-',
  'AB+',
  'AB-',
  'O+',
  'O-',
] as const;

export const CHANGE_TYPE_LABELS: Record<EmploymentChangeType, string> = {
  created: 'Joined',
  confirmation: 'Confirmed',
  promotion: 'Promoted',
  team_transfer: 'Transferred',
  designation_change: 'Designation changed',
  grade_change: 'Grade changed',
  manager_change: 'Manager changed',
  location_change: 'Location changed',
  status_change: 'Status changed',
  details_updated: 'Details updated',
};

/** Organizational placement, resolved to names rather than bare ids. */
export interface EmployeeOrganization {
  business_unit: MasterSummary | null;
  team: MasterSummary | null;
  designation: MasterSummary | null;
  grade: MasterSummary | null;
  salary_grade: MasterSummary | null;
  work_location: MasterSummary | null;
  employment_type: MasterSummary | null;
}

/** Compact employee reference, embedded in other payloads. */
export interface EmployeeSummary {
  id: string;
  employee_code: string;
  full_name: string;
  official_email: string;
  photo_url: string | null;
  employment_status: EmploymentStatus;
}

export interface EmployeeAddress {
  id: string;
  address_type: AddressType;
  address_line1: string;
  address_line2: string | null;
  landmark: string | null;
  city: string;
  state: string;
  country: string;
  postal_code: string;
}

/**
 * Bank details as they arrive from an ordinary read.
 *
 * `account_number` is **masked** by the server. The full value comes only from
 * the audited reveal endpoint, into `EmployeeBankReveal`.
 */
export interface EmployeeBankDetail {
  id: string;
  bank_name: string;
  account_number: string;
  account_holder_name: string | null;
  ifsc_code: string;
  branch_name: string;
}

/** Government identifiers as they arrive from an ordinary read: masked. */
export interface EmployeeIdentification {
  id: string;
  aadhaar_number: string | null;
  pan_number: string | null;
  passport_number: string | null;
  passport_expiry: string | null;
  driving_license_number: string | null;
  uan_number: string | null;
  pf_number: string | null;
  esi_number: string | null;
}

/** The unmasked payload returned by `GET /employees/{id}/sensitive`. */
export interface EmployeeSensitiveReveal {
  employee_id: string;
  bank_detail: (Omit<EmployeeBankDetail, 'id'> & { id: string }) | null;
  identification: EmployeeIdentification | null;
}

/** The login account attached to an employee, if any. */
export interface EmployeeUserLink {
  id: string;
  user_code: string;
  username: string;
  email: string;
  is_active: boolean;
}

export interface EmployeeRecord {
  id: string;
  /** System-generated employee identifier (JSAN336). Never editable. */
  employee_code: string;

  first_name: string;
  last_name: string;
  /** Derived by the server from the name parts; never stored. */
  full_name: string;

  gender: Gender | null;
  date_of_birth: string | null;
  blood_group: BloodGroup | null;
  marital_status: MaritalStatus | null;
  nationality: string | null;

  personal_email: string | null;
  mobile_number: string | null;
  alternate_number: string | null;
  emergency_contact_name: string | null;
  emergency_contact_number: string | null;
  emergency_contact_relationship: string | null;
  photo_url: string | null;

  official_email: string;
  official_mobile: string | null;
  extension_number: string | null;
  work_mode: WorkMode | null;

  joining_date: string;
  confirmation_date: string | null;
  employment_status: EmploymentStatus;

  employment_type_id: string | null;
  business_unit_id: string | null;
  team_id: string | null;
  designation_id: string | null;
  grade_id: string | null;
  work_location_id: string | null;
  salary_grade_id: string | null;
  reporting_manager_id: string | null;

  organization: EmployeeOrganization;
  reporting_manager: EmployeeSummary | null;
  user: EmployeeUserLink | null;

  ctc: string | null;
  notes: string | null;

  addresses: EmployeeAddress[];
  bank_detail: EmployeeBankDetail | null;
  identification: EmployeeIdentification | null;

  created_at: string;
  updated_at: string;
  created_by: string | null;
  updated_by: string | null;
  /** Non-null when the employee has been archived. */
  deleted_at: string | null;
}

export interface EmploymentHistoryEntry {
  id: string;
  change_type: EmploymentChangeType;
  effective_date: string;
  employment_status: EmploymentStatus;

  team: MasterSummary | null;
  designation: MasterSummary | null;
  grade: MasterSummary | null;
  work_location: MasterSummary | null;
  reporting_manager: EmployeeSummary | null;

  summary: string;
  reason: string | null;
  notes: string | null;

  created_at: string;
  created_by: string | null;
}

/** One audit-trail entry concerning an employee. */
export interface EmployeeAuditEntry {
  id: string;
  action: string;
  outcome: string;
  description: string | null;
  actor_id: string | null;
  actor_email: string | null;
  context: Record<string, unknown> | null;
  created_at: string;
}

export interface CountByLabel {
  label: string;
  count: number;
}

export interface EmployeeDashboardStats {
  total_employees: number;
  employed: number;
  by_status: CountByLabel[];
  by_business_unit: CountByLabel[];
  by_work_mode: CountByLabel[];
  joining_this_month: number;
  on_probation: number;
  on_notice: number;
  archived: number;
}

/** Query parameters accepted by the employee list endpoint. */
export interface EmployeeListQuery {
  page: number;
  page_size: number;
  search?: string;
  archived: boolean;
  sort_by: string;
  sort_order: 'asc' | 'desc';

  employment_status?: EmploymentStatus;
  business_unit_id?: string;
  team_id?: string;
  designation_id?: string;
  grade_id?: string;
  work_location_id?: string;
  employment_type_id?: string;
  reporting_manager_id?: string;
  work_mode?: WorkMode;
  joined_from?: string;
  joined_to?: string;
}

export type ExportFormat = 'csv' | 'xlsx';

/** True when the employee has been soft deleted. */
export function isArchived(employee: Pick<EmployeeRecord, 'deleted_at'>): boolean {
  return employee.deleted_at !== null;
}

/** True while the person is still on the books, whatever stage they are at. */
export function isEmployed(employee: Pick<EmployeeRecord, 'employment_status'>): boolean {
  return employee.employment_status !== 'resigned' && employee.employment_status !== 'inactive';
}
