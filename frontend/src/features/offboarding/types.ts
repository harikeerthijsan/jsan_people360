/**
 * Resignation and offboarding types, mirroring the API schemas.
 *
 * The employee-facing and administrative shapes are separate types, exactly as
 * they are separate models on the server. `MyResignation` has no `hr_comments`
 * and no owner ids, because a type that never declares a field cannot render it
 * by accident.
 *
 * Nothing here carries an employee id on a *write*. Submitting a resignation
 * and completing an exit interview are about the signed-in user, and the server
 * resolves who that is -- so there is no id for a component to pass and no way
 * for it to pass the wrong one.
 */

export type ResignationStatus =
  | 'draft'
  | 'submitted'
  | 'manager_review'
  | 'hr_review'
  | 'approved'
  | 'rejected'
  | 'withdrawn'
  | 'notice_period'
  | 'clearance'
  | 'exit_interview'
  | 'completed'
  | 'cancelled';

export type OffboardingCaseStatus = 'not_started' | 'in_progress' | 'completed' | 'cancelled';
export type OffboardingTaskStatus = 'pending' | 'in_progress' | 'completed' | 'waived';
export type OffboardingDepartment = 'hr' | 'manager' | 'it' | 'admin' | 'finance';
export type HandoverStatus = 'not_started' | 'in_progress' | 'completed';
export type AssetReturnStatus = 'assigned' | 'returned' | 'damaged' | 'lost' | 'waived';
export type AccessClearanceStatus = 'pending' | 'revoked' | 'not_applicable';
export type SettlementStatus =
  'not_started' | 'in_progress' | 'pending_clearance' | 'ready_for_processing' | 'completed';
export type ExitDocumentType = 'experience_letter' | 'relieving_letter' | 'service_certificate';

export interface NoticePeriodView {
  resignation_date: string;
  notice_period_days: number;
  expected_last_working_day: string;
  proposed_last_working_day: string;
  approved_last_working_day: string | null;
  remaining_days: number;
  notice_served_days: number;
  notice_status: string;
  notice_period_adjusted: boolean;
}

export interface ResignationHistoryEntry {
  id: string;
  action: string;
  from_status: string | null;
  to_status: string | null;
  comments: string | null;
  is_override: boolean;
  created_at: string;
}

export interface EmployeeSummary {
  id: string;
  employee_code: string;
  full_name: string;
  designation: string | null;
  team: string | null;
}

/** The employee's own view. Deliberately carries no HR commentary. */
export interface MyResignation {
  id: string;
  resignation_code: string;
  status: ResignationStatus;
  resignation_date: string;
  proposed_last_working_day: string;
  approved_last_working_day: string | null;
  reason: string;
  comments: string | null;
  supporting_document_id: string | null;
  submitted_at: string | null;
  manager_comments: string | null;
  can_withdraw: boolean;
  notice: NoticePeriodView | null;
  history: ResignationHistoryEntry[];
}

export interface ResignationRead {
  id: string;
  resignation_code: string;
  employee: EmployeeSummary;
  status: ResignationStatus;
  resignation_date: string;
  proposed_last_working_day: string;
  recommended_last_working_day: string | null;
  approved_last_working_day: string | null;
  notice_period_days: number;
  notice_period_adjusted: boolean;
  reason: string;
  comments: string | null;
  supporting_document_id: string | null;
  submitted_at: string | null;
  manager_id: string | null;
  manager_decided_at: string | null;
  manager_comments: string | null;
  hr_owner_id: string | null;
  hr_processed_at: string | null;
  hr_comments: string | null;
  case_id: string | null;
  notice: NoticePeriodView | null;
  history: ResignationHistoryEntry[];
}

export interface OffboardingTask {
  id: string;
  title: string;
  department: OffboardingDepartment;
  owner_id: string | null;
  due_date: string;
  status: OffboardingTaskStatus;
  comments: string | null;
  completed_at: string | null;
  sequence: number;
}

export interface AssetClearance {
  id: string;
  asset_name: string;
  asset_tag: string | null;
  assigned_date: string | null;
  return_date: string | null;
  condition: string | null;
  status: AssetReturnStatus;
  comments: string | null;
}

export interface AccessClearance {
  id: string;
  system_name: string;
  category: string | null;
  status: AccessClearanceStatus;
  revoked_at: string | null;
  comments: string | null;
}

export interface HandoverRecord {
  id: string;
  status: HandoverStatus;
  projects: string | null;
  responsibilities: string | null;
  documentation: string | null;
  replacement_employee_id: string | null;
  notes: string | null;
  attachment_ids: string[];
  completed_at: string | null;
}

export interface SettlementRecord {
  id: string;
  status: SettlementStatus;
  settlement_reference: string | null;
  settlement_date: string | null;
  comments: string | null;
}

export interface ExitDocument {
  id: string;
  document_type: ExitDocumentType;
  document_id: string | null;
  issued_at: string | null;
  released: boolean;
}

export interface ClearanceProgress {
  tasks_total: number;
  tasks_settled: number;
  assets_total: number;
  assets_settled: number;
  access_total: number;
  access_settled: number;
  percent: number;
  outstanding_departments: OffboardingDepartment[];
}

export interface OffboardingCase {
  id: string;
  case_code: string;
  employee: EmployeeSummary;
  resignation_id: string;
  resignation_code: string | null;
  resignation_status: ResignationStatus | null;
  last_working_day: string;
  notice_period_days: number;
  hr_owner_id: string | null;
  manager_id: string | null;
  status: OffboardingCaseStatus;
  progress_percent: number;
  created_at: string;
  completed_at: string | null;
  tasks: OffboardingTask[];
  assets: AssetClearance[];
  access_items: AccessClearance[];
  handover: HandoverRecord | null;
  settlement: SettlementRecord | null;
  exit_documents: ExitDocument[];
  exit_interview_submitted: boolean;
  clearance: ClearanceProgress | null;
  notice: NoticePeriodView | null;
}

export interface MyPendingAction {
  key: string;
  label: string;
  link: string;
}

export interface MyOffboarding {
  resignation: MyResignation | null;
  case_code: string | null;
  last_working_day: string | null;
  case_status: OffboardingCaseStatus | null;
  clearance: ClearanceProgress | null;
  my_tasks: OffboardingTask[];
  pending_actions: MyPendingAction[];
  exit_interview_submitted: boolean;
  exit_interview_available: boolean;
  exit_documents: ExitDocument[];
  settlement_status: SettlementStatus | null;
}

export interface ExitInterview {
  id: string;
  case_id: string;
  employee_id: string;
  reason_for_leaving: string;
  overall_experience: number | null;
  management_rating: number | null;
  work_environment_rating: number | null;
  career_growth_rating: number | null;
  compensation_rating: number | null;
  management_feedback: string | null;
  work_environment_feedback: string | null;
  career_growth_feedback: string | null;
  compensation_feedback: string | null;
  suggestions: string | null;
  would_recommend: boolean | null;
  would_rejoin: boolean | null;
  submitted_at: string | null;
}

export interface ExitInterviewListItem {
  id: string;
  case_id: string;
  employee: EmployeeSummary;
  reason_for_leaving: string;
  overall_experience: number | null;
  would_recommend: boolean | null;
  would_rejoin: boolean | null;
  submitted_at: string | null;
}

export interface OffboardingSummary {
  active_resignations: number;
  pending_manager_review: number;
  pending_hr_review: number;
  serving_notice: number;
  exiting_this_month: number;
  pending_clearance: number;
  exit_interviews_pending: number;
  exit_documents_pending: number;
  settlement_pending: number;
}

// -- Request payloads ----------------------------------------------------
export interface ResignationSubmitInput {
  resignation_date: string;
  proposed_last_working_day: string;
  reason: string;
  comments?: string | null;
  supporting_document_id?: string | null;
}

export interface ManagerDecisionInput {
  decision: 'approve' | 'reject';
  comments?: string | null;
  recommended_last_working_day?: string | null;
}

export interface HrProcessInput {
  approved_last_working_day?: string | null;
  notice_period_days?: number | null;
  adjustment_reason?: string | null;
  comments?: string | null;
}

export interface HandoverInput {
  status: HandoverStatus;
  projects?: string | null;
  responsibilities?: string | null;
  documentation?: string | null;
  replacement_employee_id?: string | null;
  notes?: string | null;
  attachment_ids?: string[];
}

export interface ExitInterviewInput {
  reason_for_leaving: string;
  overall_experience?: number | null;
  management_rating?: number | null;
  work_environment_rating?: number | null;
  career_growth_rating?: number | null;
  compensation_rating?: number | null;
  management_feedback?: string | null;
  work_environment_feedback?: string | null;
  career_growth_feedback?: string | null;
  compensation_feedback?: string | null;
  suggestions?: string | null;
  would_recommend?: boolean | null;
  would_rejoin?: boolean | null;
}

export const RESIGNATION_STATUS_LABELS: Record<ResignationStatus, string> = {
  draft: 'Draft',
  submitted: 'Submitted',
  manager_review: 'With your manager',
  hr_review: 'With HR',
  approved: 'Approved',
  rejected: 'Rejected',
  withdrawn: 'Withdrawn',
  notice_period: 'Serving notice',
  clearance: 'Clearance',
  exit_interview: 'Exit interview',
  completed: 'Completed',
  cancelled: 'Cancelled',
};

export const DEPARTMENT_LABELS: Record<OffboardingDepartment, string> = {
  hr: 'HR',
  manager: 'Manager',
  it: 'IT',
  admin: 'Admin',
  finance: 'Finance',
};

export const TASK_STATUS_LABELS: Record<OffboardingTaskStatus, string> = {
  pending: 'Pending',
  in_progress: 'In progress',
  completed: 'Completed',
  waived: 'Waived',
};

export const SETTLEMENT_STATUS_LABELS: Record<SettlementStatus, string> = {
  not_started: 'Not started',
  in_progress: 'In progress',
  pending_clearance: 'Pending clearance',
  ready_for_processing: 'Ready for processing',
  completed: 'Completed',
};

export const EXIT_DOCUMENT_LABELS: Record<ExitDocumentType, string> = {
  experience_letter: 'Experience letter',
  relieving_letter: 'Relieving letter',
  service_certificate: 'Service certificate',
};
