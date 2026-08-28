/**
 * Domain types for the manager and team screens.
 *
 * Thin, like the employee portal's. An attendance row, a leave request and a
 * timesheet are the *same* rows the HR and personal screens show, so their
 * shapes are imported from the module that owns them rather than restated here.
 * What the manager API adds to each of them is one thing -- whose row it is --
 * and that is what the `Team*Row` wrappers below carry.
 *
 * Decimal quantities arrive as strings, for the reason the workforce module
 * gives: the API sends `Decimal` so half-days and part-allocations survive the
 * trip. Parse at the point of arithmetic, not at the boundary.
 */

import type { ApprovalStatus, LeaveRequest, Regularization, Timesheet } from '@/features/workforce/types';

export type { ApprovalStatus, LeaveRequest, Regularization, Timesheet };

/**
 * The attendance statuses the API actually sends.
 *
 * Declared here rather than imported from the workforce module, whose
 * `AttendanceStatus` has drifted: it lists `on_leave` and `weekly_off` where
 * the server sends `leave` and `weekend`. Importing it would mean a badge
 * rendering `undefined` for exactly the two days a manager most wants to see.
 */
export type TeamAttendanceStatus = 'present' | 'absent' | 'half_day' | 'leave' | 'holiday' | 'weekend';

export const TEAM_ATTENDANCE_STATUS_LABELS: Record<TeamAttendanceStatus, string> = {
  present: 'Present',
  absent: 'Absent',
  half_day: 'Half day',
  leave: 'On leave',
  holiday: 'Holiday',
  weekend: 'Weekly off',
};

export const TEAM_ATTENDANCE_STATUSES: readonly TeamAttendanceStatus[] = [
  'present',
  'absent',
  'half_day',
  'leave',
  'holiday',
  'weekend',
] as const;

export type EmploymentStatus =
  'probation' | 'confirmed' | 'active' | 'notice_period' | 'resigned' | 'inactive';

export const EMPLOYMENT_STATUS_LABELS: Record<EmploymentStatus, string> = {
  probation: 'Probation',
  confirmed: 'Confirmed',
  active: 'Active',
  notice_period: 'Notice period',
  resigned: 'Resigned',
  inactive: 'Inactive',
};

export interface MasterSummary {
  id: string;
  name: string;
  code: string | null;
  status: string;
}

export interface EmployeeSummary {
  id: string;
  employee_code: string;
  full_name: string;
  official_email: string;
  photo_url: string | null;
  employment_status: EmploymentStatus;
}

// ---------------------------------------------------------------------------
// The roster
// ---------------------------------------------------------------------------
export interface TeamAllocation {
  project_id: string;
  project_code: string;
  project_name: string;
  client_name: string | null;
  allocation_percentage: string;
  billable: boolean;
}

export interface TeamMember {
  id: string;
  employee_code: string;
  full_name: string;
  photo_url: string | null;
  official_email: string;
  employment_status: EmploymentStatus;

  designation: MasterSummary | null;
  business_unit: MasterSummary | null;
  team: MasterSummary | null;
  work_location: MasterSummary | null;
  employment_type: MasterSummary | null;

  allocations: TeamAllocation[];
  allocated_percentage: string;

  attendance_status: TeamAttendanceStatus | null;
  checked_in_at: string | null;
  checked_out_at: string | null;
  on_leave_type: string | null;
}

export interface TeamAttendanceSummary {
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

export interface TeamLeaveBalance {
  leave_type_id: string;
  leave_type_name: string;
  year: number;
  allocated: string;
  used: string;
  pending: string;
  available: string;
}

export interface TeamTimesheetSummary {
  draft: number;
  submitted: number;
  approved: number;
  rejected: number;
  total_hours: string;
  billable_hours: string;
}

export interface TeamPerformance {
  employee: EmployeeSummary;
  cycle_id: string | null;
  cycle_name: string | null;
  goals: number;
  goals_completed: number;
  goal_progress: number;
  self_review_status: string | null;
  manager_review_status: string | null;
  current_rating: number | null;
  review_due: boolean;
}

export interface TeamMemberProfile {
  member: TeamMember;
  joining_date: string;
  confirmation_date: string | null;
  reporting_manager: EmployeeSummary | null;
  work_mode: string | null;
  attendance: TeamAttendanceSummary;
  leave: TeamLeaveBalance[];
  timesheets: TeamTimesheetSummary;
  performance: TeamPerformance | null;
}

// ---------------------------------------------------------------------------
// Rows: a module's own record, paired with whose it is
// ---------------------------------------------------------------------------
/** The attendance record as the manager API sends it -- the server's own values. */
export interface TeamAttendanceRecord {
  id: string;
  employee_id: string;
  attendance_date: string;
  shift_id: string | null;
  check_in_at: string | null;
  check_out_at: string | null;
  work_mode: string;
  status: TeamAttendanceStatus;
  worked_minutes: number;
  late_minutes: number;
  early_exit_minutes: number;
  overtime_minutes: number;
  notes: string | null;
}

export interface TeamAttendanceRow {
  employee: EmployeeSummary;
  record: TeamAttendanceRecord;
}

export interface TeamLeaveRow {
  employee: EmployeeSummary;
  request: LeaveRequest;
}

export interface TeamTimesheetRow {
  employee: EmployeeSummary;
  timesheet: Timesheet;
}

export interface TeamRegularizationRow {
  employee: EmployeeSummary;
  request: Regularization;
}

// ---------------------------------------------------------------------------
// Projects, calendar and documents
// ---------------------------------------------------------------------------
export interface TeamProjectMember {
  employee: EmployeeSummary;
  allocation_percentage: string;
  billable: boolean;
  start_date: string;
  end_date: string | null;
}

export interface TeamProject {
  project_id: string;
  project_code: string;
  project_name: string;
  client_name: string | null;
  status: string;
  start_date: string;
  end_date: string | null;
  team_size: number;
  total_allocation: string;
  billable_percentage: number;
  members: TeamProjectMember[];
}

export interface TeamAllocationSummary {
  allocated_members: number;
  unallocated_members: number;
  average_allocation: number;
  billable_members: number;
  active_projects: number;
}

export type CalendarEntryKind = 'leave' | 'holiday' | 'exception' | 'joining';

export interface TeamCalendarEntry {
  day: string;
  kind: CalendarEntryKind;
  label: string;
  employee_id: string | null;
  employee_name: string | null;
  detail: string | null;
}

export interface TeamCalendar {
  year: number;
  month: number;
  entries: TeamCalendarEntry[];
}

export const CALENDAR_KIND_LABELS: Record<CalendarEntryKind, string> = {
  leave: 'Leave',
  holiday: 'Holiday',
  exception: 'Attendance',
  joining: 'Joining',
};

export interface TeamDocumentStatus {
  employee: EmployeeSummary;
  total: number;
  approved: number;
  pending: number;
  rejected: number;
}

export interface TeamHoliday {
  id: string;
  name: string;
  holiday_date: string;
  holiday_type: string;
  calendar_name: string;
}

// ---------------------------------------------------------------------------
// Dashboard
// ---------------------------------------------------------------------------
export interface ManagerDashboard {
  manager: EmployeeSummary;
  on_date: string;

  team_size: number;
  present_today: number;
  absent_today: number;
  on_leave_today: number;
  not_recorded_today: number;

  pending_leave_approvals: number;
  pending_timesheet_approvals: number;
  pending_regularizations: number;
  pending_performance_reviews: number;

  upcoming_holidays: TeamHoliday[];
  active_projects: number;
  allocation: TeamAllocationSummary;

  leave_awaiting_decision: TeamLeaveRow[];
  timesheets_awaiting_decision: TeamTimesheetRow[];
  regularizations_awaiting_decision: TeamRegularizationRow[];
}

/** What a manager sends when they act on a request. */
export interface ApprovalDecision {
  approved: boolean;
  notes?: string | null;
}
