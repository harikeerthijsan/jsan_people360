/**
 * Domain types for Workforce Operations.
 *
 * Money-like quantities -- leave days, timesheet hours -- arrive as strings.
 * The API sends `Decimal` rather than a float precisely so half-days and
 * quarter-hours survive the trip, and parsing them into numbers on arrival
 * would throw that away. Parse at the point of arithmetic, not at the boundary.
 */

export type ShiftType = 'general' | 'morning' | 'evening' | 'night' | 'flexible';
export type RecordStatus = 'active' | 'inactive';
export type AttendanceStatus = 'present' | 'absent' | 'half_day' | 'on_leave' | 'holiday' | 'weekly_off';
export type WorkMode = 'office' | 'remote' | 'hybrid' | 'client_site';
export type ApprovalStatus = 'pending' | 'approved' | 'rejected' | 'cancelled';
export type LeaveDayPart = 'full_day' | 'first_half' | 'second_half';
export type HolidayType = 'public' | 'restricted' | 'optional';
export type TimesheetStatus = 'draft' | 'submitted' | 'approved' | 'rejected';

/** Monday = 0, matching `Date.prototype.getDay()` shifted, and Python's `weekday()`. */
export const WEEKDAYS = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
] as const;

export const MAX_DAILY_HOURS = 24;

export const SHIFT_TYPE_LABELS: Record<ShiftType, string> = {
  general: 'General',
  morning: 'Morning',
  evening: 'Evening',
  night: 'Night',
  flexible: 'Flexible',
};

export const SHIFT_TYPES: readonly ShiftType[] = [
  'general',
  'morning',
  'evening',
  'night',
  'flexible',
] as const;

export const ATTENDANCE_STATUS_LABELS: Record<AttendanceStatus, string> = {
  present: 'Present',
  absent: 'Absent',
  half_day: 'Half day',
  on_leave: 'On leave',
  holiday: 'Holiday',
  weekly_off: 'Weekly off',
};

export const ATTENDANCE_STATUSES: readonly AttendanceStatus[] = [
  'present',
  'absent',
  'half_day',
  'on_leave',
  'holiday',
  'weekly_off',
] as const;

export const WORK_MODE_LABELS: Record<WorkMode, string> = {
  office: 'Office',
  remote: 'Remote',
  hybrid: 'Hybrid',
  client_site: 'Client site',
};

export const WORK_MODES: readonly WorkMode[] = ['office', 'remote', 'hybrid', 'client_site'] as const;

export const APPROVAL_STATUS_LABELS: Record<ApprovalStatus, string> = {
  pending: 'Pending',
  approved: 'Approved',
  rejected: 'Rejected',
  cancelled: 'Cancelled',
};

export const APPROVAL_STATUSES: readonly ApprovalStatus[] = [
  'pending',
  'approved',
  'rejected',
  'cancelled',
] as const;

export const LEAVE_DAY_PART_LABELS: Record<LeaveDayPart, string> = {
  full_day: 'Full day',
  first_half: 'First half',
  second_half: 'Second half',
};

export const HOLIDAY_TYPE_LABELS: Record<HolidayType, string> = {
  public: 'Public holiday',
  restricted: 'Restricted holiday',
  optional: 'Optional holiday',
};

export const HOLIDAY_TYPES: readonly HolidayType[] = ['public', 'restricted', 'optional'] as const;

/** Ordered as a timesheet moves, not alphabetically. */
export const TIMESHEET_STATUSES: readonly TimesheetStatus[] = [
  'draft',
  'submitted',
  'approved',
  'rejected',
] as const;

export const TIMESHEET_STATUS_LABELS: Record<TimesheetStatus, string> = {
  draft: 'Draft',
  submitted: 'Submitted',
  approved: 'Approved',
  rejected: 'Rejected',
};

// ---------------------------------------------------------------------------
// Records
// ---------------------------------------------------------------------------
export interface Shift {
  id: string;
  name: string;
  code: string;
  shift_type: ShiftType;
  start_time: string;
  end_time: string;
  grace_minutes: number;
  break_minutes: number;
  weekly_off: number[];
  status: RecordStatus;
  created_at: string;
  deleted_at: string | null;
}

export interface EmployeeShift {
  id: string;
  employee_id: string;
  shift_id: string;
  effective_from: string;
  /** Null while this is the assignment in force. */
  effective_to: string | null;
  shift: Shift | null;
}

export interface AttendanceRecord {
  id: string;
  employee_id: string;
  attendance_date: string;
  shift_id: string | null;
  check_in_at: string | null;
  check_out_at: string | null;
  worked_minutes: number;
  late_minutes: number;
  early_exit_minutes: number;
  overtime_minutes: number;
  status: AttendanceStatus;
  work_mode: WorkMode;
  notes: string | null;
}

export interface Regularization {
  id: string;
  employee_id: string;
  attendance_date: string;
  requested_check_in_at: string | null;
  requested_check_out_at: string | null;
  reason: string;
  supporting_document_id: string | null;
  status: ApprovalStatus;
  decided_by_id: string | null;
  decided_at: string | null;
  decision_notes: string | null;
  created_at: string;
}

export interface LeaveType {
  id: string;
  name: string;
  code: string;
  description: string | null;
  annual_allocation: string;
  carry_forward: boolean;
  max_carry_forward: string;
  allows_negative: boolean;
  is_paid: boolean;
  requires_document: boolean;
  status: RecordStatus;
}

export interface LeaveRequest {
  id: string;
  employee_id: string;
  leave_type_id: string;
  from_date: string;
  to_date: string;
  day_part: LeaveDayPart;
  /** Working days only -- weekends and holidays are already excluded. */
  days: string;
  reason: string;
  supporting_document_id: string | null;
  status: ApprovalStatus;
  decided_by_id: string | null;
  decided_at: string | null;
  decision_notes: string | null;
  created_at: string;
  leave_type: LeaveType | null;
}

export interface LeaveBalance {
  id: string;
  employee_id: string;
  leave_type_id: string;
  year: number;
  opening_balance: string;
  allocated: string;
  used: string;
  /** Held by requests awaiting a decision, not yet spent. */
  pending: string;
  remaining: string;
  leave_type: LeaveType | null;
}

export interface Holiday {
  id: string;
  calendar_id: string;
  name: string;
  holiday_date: string;
  holiday_type: HolidayType;
}

export interface HolidayCalendar {
  id: string;
  name: string;
  year: number;
  location_id: string | null;
  description: string | null;
  status: RecordStatus;
  holidays: Holiday[];
}

export interface TimesheetEntry {
  id: string;
  timesheet_id: string;
  project_id: string;
  work_date: string;
  task: string;
  hours: string;
  billable: boolean;
  comments: string | null;
}

export interface Timesheet {
  id: string;
  timesheet_code: string;
  employee_id: string;
  week_start_date: string;
  total_hours: string;
  billable_hours: string;
  status: TimesheetStatus;
  submitted_at: string | null;
  decided_by_id: string | null;
  decided_at: string | null;
  decision_notes: string | null;
  entries: TimesheetEntry[];
}

// ---------------------------------------------------------------------------
// Dashboards, calendar and reports
// ---------------------------------------------------------------------------
export interface CountByLabel {
  label: string;
  count: number;
}

export interface WorkforceDashboard {
  on_date: string;
  present: number;
  absent: number;
  on_leave: number;
  remote: number;
  late_arrivals: number;
  missing_timesheets: number;
  leave_requests_pending: number;
  regularizations_pending: number;
  monthly_attendance_percentage: number;
  headcount: number;
  by_work_mode: CountByLabel[];
  by_attendance_status: CountByLabel[];
}

export interface TimesheetDashboard {
  draft: number;
  submitted: number;
  approved: number;
  rejected: number;
  /** Employees with no timesheet at all for the week. */
  missing: number;
}

/** One square in the month grid: what happened on that date. */
export interface CalendarDay {
  day: string;
  is_weekend: boolean;
  holiday_name: string | null;
  attendance_status: AttendanceStatus | null;
  worked_minutes: number;
  leave_type: string | null;
  timesheet_hours: string;
}

export type WorkforceReport =
  'attendance' | 'leave-register' | 'leave-balance' | 'timesheet' | 'overtime' | 'shift';

export type ExportFormat = 'csv' | 'xlsx' | 'pdf';

export const WORKFORCE_REPORT_LABELS: Record<WorkforceReport, string> = {
  attendance: 'Attendance register',
  'leave-register': 'Leave register',
  'leave-balance': 'Leave balances',
  timesheet: 'Timesheet summary',
  overtime: 'Overtime',
  shift: 'Shift assignments',
};
