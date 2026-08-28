/**
 * Domain types for the employee portal.
 *
 * Deliberately thin. Attendance records, leave requests, timesheets and
 * documents are the *same* rows the HR screens show, so their shapes are
 * imported from the modules that own them rather than restated here -- a second
 * declaration of `LeaveRequest` is a second thing to update when a column is
 * added, and the two would disagree quietly.
 *
 * What is declared here is what only the portal has: the composed dashboard,
 * the five-figure leave balance, and an allocation seen from the inside.
 *
 * Decimal quantities arrive as strings, for the reason the workforce module
 * gives: the API sends `Decimal` so half-days and quarter-hours survive the
 * trip. Parse at the point of arithmetic, not at the boundary.
 */

import type { DocumentRecord } from '@/features/documents/types/document.types';
import type { MyAnnouncement } from '@/features/helpdesk/types';
import type {
  AttendanceRecord,
  AttendanceStatus,
  LeaveRequest,
  LeaveType,
  Timesheet,
} from '@/features/workforce/types';

export type { AttendanceRecord, LeaveRequest, LeaveType, Timesheet };

// ---------------------------------------------------------------------------
// Profile
// ---------------------------------------------------------------------------
export interface MyAddress {
  id: string;
  address_type: 'current' | 'permanent';
  address_line1: string;
  address_line2: string | null;
  landmark: string | null;
  city: string;
  state: string;
  country: string;
  postal_code: string;
}

export interface MasterSummary {
  id: string;
  name: string;
  code: string | null;
  status: string;
}

export interface MyOrganization {
  business_unit: MasterSummary | null;
  team: MasterSummary | null;
  designation: MasterSummary | null;
  grade: MasterSummary | null;
  salary_grade: MasterSummary | null;
  work_location: MasterSummary | null;
  employment_type: MasterSummary | null;
}

export interface EmployeeSummary {
  id: string;
  employee_code: string;
  full_name: string;
  official_email: string;
  photo_url: string | null;
  employment_status: string;
}

export interface MyProfile {
  id: string;
  employee_code: string;
  first_name: string;
  last_name: string;
  full_name: string;

  photo_url: string | null;
  personal_email: string | null;
  mobile_number: string | null;
  alternate_number: string | null;
  emergency_contact_name: string | null;
  emergency_contact_number: string | null;
  emergency_contact_relationship: string | null;
  addresses: MyAddress[];

  official_email: string;
  official_mobile: string | null;
  extension_number: string | null;
  date_of_birth: string | null;
  gender: string | null;
  blood_group: string | null;
  marital_status: string | null;
  nationality: string | null;
  joining_date: string;
  confirmation_date: string | null;
  employment_status: string;
  work_mode: string | null;
  organization: MyOrganization;
  reporting_manager: EmployeeSummary | null;

  /**
   * Which fields `PATCH /me/profile` accepts, named by the server.
   *
   * The form disables everything else from this list rather than from a
   * hard-coded copy, so a field the server starts or stops accepting changes
   * the UI without a frontend release.
   */
  editable_fields: string[];
}

// ---------------------------------------------------------------------------
// Attendance
// ---------------------------------------------------------------------------
export interface MyAttendanceToday {
  on_date: string;
  record: AttendanceRecord | null;
  checked_in: boolean;
  checked_out: boolean;
  can_check_in: boolean;
  can_check_out: boolean;
  status: AttendanceStatus | null;
  worked_minutes: number;
  /** Minutes since check-in for a day still open. The ticking timer starts here. */
  elapsed_minutes: number;
  /** Server clock at the moment of the response, so a skewed browser cannot drift. */
  server_time: string;
}

export interface MyAttendanceSummary {
  from_date: string;
  to_date: string;
  present_days: number;
  absent_days: number;
  leave_days: number;
  half_days: number;
  late_arrivals: number;
  early_exits: number;
  worked_minutes: number;
  overtime_minutes: number;
}

// ---------------------------------------------------------------------------
// Leave
// ---------------------------------------------------------------------------
export interface MyLeaveBalance {
  leave_type_id: string;
  leave_type: LeaveType | null;
  year: number;
  allocated: string;
  /** Credited so far: this year's allocation plus anything carried forward. */
  accrued: string;
  used: string;
  /** Held by a request awaiting a decision. Returned if it is turned down. */
  pending: string;
  available: string;
  is_paid: boolean;
  requires_document: boolean;
}

// ---------------------------------------------------------------------------
// Projects
// ---------------------------------------------------------------------------
export interface MyProject {
  allocation_id: string;
  project_id: string;
  project_code: string;
  project_name: string;
  client_name: string | null;
  role: string | null;
  allocation_percentage: string;
  start_date: string;
  end_date: string | null;
  billable: boolean;
  status: string;
  /** Today falls inside the allocation window. Only these may be booked against. */
  is_current: boolean;
}

// ---------------------------------------------------------------------------
// Timesheets
// ---------------------------------------------------------------------------
export interface MyTimesheetWeek {
  week_start_date: string;
  timesheet: Timesheet | null;
  /** False once submitted or approved; a rejected week is editable again. */
  editable: boolean;
  projects: MyProject[];
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------
export interface MyDocument extends DocumentRecord {
  /** False for anything HR issued: an offer letter is mine to read, not to reissue. */
  can_replace: boolean;
}

export interface MyDocumentType {
  id: string;
  name: string;
  code: string | null;
  category_id: string;
  category_name: string;
  requires_expiry: boolean;
  allowed_extensions: string | null;
}

export interface MyDocumentSummary {
  total: number;
  pending_review: number;
  approved: number;
  rejected: number;
  expiring_soon: number;
}

// ---------------------------------------------------------------------------
// Holidays
// ---------------------------------------------------------------------------
export interface MyHoliday {
  id: string;
  name: string;
  holiday_date: string;
  holiday_type: string;
  calendar_name: string;
  is_past: boolean;
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------
export interface PendingAction {
  code: string;
  label: string;
  detail: string | null;
  link: string;
}

export interface MyNotification {
  id: string;
  title: string;
  message: string;
  link: string | null;
  notification_type: string;
  is_read: boolean;
  created_at: string;
}

export interface MyDashboard {
  employee: EmployeeSummary;
  on_date: string;
  attendance: MyAttendanceToday;
  month_summary: MyAttendanceSummary;
  leave_balances: MyLeaveBalance[];
  pending_leave: LeaveRequest[];
  upcoming_holidays: MyHoliday[];
  current_timesheet: Timesheet | null;
  current_week_start: string;
  projects: MyProject[];
  documents: MyDocumentSummary;
  recent_documents: MyDocument[];
  pending_actions: PendingAction[];
  //: Real announcements now -- the field was the notification inbox until
  //: phase 20, when the platform grew an announcements module. The inbox is
  //: still here, under its own name.
  recent_announcements: MyAnnouncement[];
  recent_notifications: MyNotification[];
}

// ---------------------------------------------------------------------------
// Labels
// ---------------------------------------------------------------------------
export const HOLIDAY_TYPE_LABELS: Record<string, string> = {
  public: 'Public',
  restricted: 'Restricted',
  optional: 'Optional',
};

export const WORK_MODE_OPTIONS = [
  { value: 'office', label: 'Office' },
  { value: 'remote', label: 'Remote' },
  { value: 'hybrid', label: 'Hybrid' },
  { value: 'client_site', label: 'Client site' },
] as const;

export const ADDRESS_TYPE_OPTIONS = [
  { value: 'current', label: 'Current address' },
  { value: 'permanent', label: 'Permanent address' },
] as const;
