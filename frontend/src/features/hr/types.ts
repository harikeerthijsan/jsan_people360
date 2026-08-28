import type { PageMeta } from '@/lib/api/types';

export interface EmployeeSummary {
  id: string;
  employee_code: string;
  full_name: string;
  official_email: string;
  photo_url: string | null;
  employment_status: string;
}
export interface MasterSummary {
  id: string;
  name: string;
  code: string | null;
}
export interface HrEmployee {
  id: string;
  employee_code: string;
  full_name: string;
  official_email: string;
  official_mobile: string | null;
  mobile_number: string | null;
  designation: MasterSummary | null;
  business_unit: MasterSummary | null;
  team: MasterSummary | null;
  work_location: MasterSummary | null;
  employment_type: MasterSummary | null;
  reporting_manager: EmployeeSummary | null;
  joining_date: string;
  confirmation_date: string | null;
  employment_status: string;
  work_mode: string | null;
}
export interface HrDashboard {
  on_date: string;
  sections: string[];
  employees: null | {
    total_active: number;
    new_joiners_this_month: number;
    on_probation: number;
    exiting: number;
    by_business_unit: { label: string; count: number }[];
  };
  attendance: null | {
    present: number;
    absent: number;
    late_arrivals: number;
    on_leave: number;
    monthly_attendance_percentage: number;
  };
  leave: null | {
    pending_requests: number;
    pending_without_a_manager: number;
    approved_this_month: number;
    rejected_this_month: number;
    days_taken_this_month: string;
  };
  recruitment: null | {
    open_requisitions: number;
    active_candidates: number;
    interviews_scheduled: number;
    offers_pending: number;
    onboarding_in_progress: number;
  };
  documents: null | { pending_review: number; rejected: number; expiring_soon: number; expired: number };
  performance: null | {
    active_cycles: number;
    self_reviews_pending: number;
    manager_reviews_pending: number;
    completion_percentage: number;
  };
  requests: null | {
    documents_awaiting_review: number;
    documents_rejected: number;
    leave_without_a_manager: number;
    regularizations_without_a_manager: number;
    oldest_waiting_days: number;
  };
}
export interface HrAnalytics {
  months: number;
  headcount_trend: Trend[];
  hiring_trend: Trend[];
  leave_trend: Trend[];
  attendance_trend: Trend[];
  performance_completion: number;
  document_compliance: number;
}
export interface Trend {
  period: string;
  label: string;
  count: number;
}
export interface AttendanceRow {
  employee: EmployeeSummary;
  record: {
    id: string;
    attendance_date: string;
    check_in_at: string | null;
    check_out_at: string | null;
    worked_minutes: number;
    status: string;
    late_minutes: number;
    early_exit_minutes: number;
    overtime_minutes: number;
  };
}
export interface LeaveRow {
  employee: EmployeeSummary;
  request: {
    id: string;
    from_date: string;
    to_date: string;
    days: string;
    status: string;
    reason: string;
    leave_type: { name: string } | null;
  };
  reporting_manager: EmployeeSummary | null;
}
export interface TimesheetRow {
  employee: EmployeeSummary;
  timesheet: {
    id: string;
    week_start_date: string;
    total_hours: string;
    billable_hours: string;
    status: string;
    entries?: unknown[];
  };
}
export interface DocumentRow {
  id: string;
  document_code: string;
  name: string;
  status: string;
  owner_name: string | null;
  expiry_date: string | null;
  review_notes: string | null;
  created_at: string;
}
export interface Report {
  key: string;
  name: string;
  description: string;
  required_permissions: string[];
  available: boolean;
}
export interface LeavePolicy {
  id: string;
  name: string;
  code: string;
  annual_allocation: string;
  credit_frequency?: string;
  credit_amount?: string;
  carry_forward: boolean;
  max_carry_forward: string;
  status: string;
  effective_from?: string | null;
  effective_to?: string | null;
}
export interface HrAttendanceSummary {
  from_date: string;
  to_date: string;
  present_days: number;
  absent_days: number;
  leave_days: number;
  half_days: number;
  late_arrivals: number;
  worked_minutes: number;
  overtime_minutes: number;
}

export interface HrLeaveBalanceRow {
  leave_type_id: string;
  leave_type_name: string;
  year: number;
  allocated: string;
  used: string;
  pending: string;
  available: string;
}

export interface HrTimesheetSummary {
  draft: number;
  submitted: number;
  approved: number;
  rejected: number;
  total_hours: string;
  billable_hours: string;
}

export interface HrProjectRow {
  project_id: string;
  project_code: string;
  project_name: string;
  client_name: string | null;
  allocation_percentage: string;
  billable: boolean;
  start_date: string;
  end_date: string | null;
}

export interface HrPerformanceSummary {
  cycle_id: string | null;
  cycle_name: string | null;
  goals: number;
  goals_completed: number;
  goal_progress: number;
  self_review_status: string | null;
  manager_review_status: string | null;
  current_rating: number | null;
}

export interface HrActivityEntry {
  id: string;
  action: string;
  outcome: string;
  description: string | null;
  actor_email: string | null;
  created_at: string;
}

export interface HrProfile {
  employee: HrEmployee;
  attendance: HrAttendanceSummary;
  leave: HrLeaveBalanceRow[];
  timesheets: HrTimesheetSummary;
  projects: HrProjectRow[];
  performance: HrPerformanceSummary | null;
  documents: DocumentRow[];
  activity: HrActivityEntry[];
  can_read_activity: boolean;
}

// -- Workforce allocation (typed; was Record<string, unknown>) -----------
export interface HrProjectHeadcountRow {
  project_id: string;
  project: string;
  headcount: number;
}

export interface HrAllocationSection {
  total_clients: number;
  active_projects: number;
  completed_projects: number;
  employees_allocated: number;
  bench_employees: number;
  allocation_utilization_percent: number;
  projects_ending_soon: number;
  allocation_conflicts: number;
  project_headcount: HrProjectHeadcountRow[];
}

export interface HrBenchRow {
  employee_id: string;
  employee_code: string;
  name: string;
  bench_since: string | null;
  bench_duration_days: number;
  skills: string[];
  team: string | null;
  manager: string | null;
}

export interface HrProjectsSection {
  allocation: HrAllocationSection;
  bench: HrBenchRow[];
}

export interface HrPerformanceSection {
  active_cycles: number;
  goals_assigned: number;
  self_reviews_pending: number;
  manager_reviews_pending: number;
  final_ratings: number;
  completion_percentage: number;
}
export interface Paged<T> {
  items: T[];
  meta: PageMeta;
}
