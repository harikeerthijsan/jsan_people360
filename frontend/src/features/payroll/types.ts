/**
 * Payroll foundation types.
 *
 * Money travels as strings. The API serialises Decimal values as exact
 * decimal strings ("500000.00"), and parsing them into floats here would
 * reintroduce the rounding the backend went out of its way to avoid. The
 * screens display them and send them back verbatim.
 */

export type PayFrequency = 'monthly' | 'weekly' | 'biweekly';
export type StructureStatus = 'draft' | 'active' | 'inactive';
export type ComponentType = 'earning' | 'deduction';
export type CalculationType = 'fixed' | 'percentage';
export type PercentageBasis = 'basic' | 'gross';
export type CompensationStatus = 'active' | 'ended';

export const PAY_FREQUENCY_LABELS: Record<PayFrequency, string> = {
  monthly: 'Monthly',
  weekly: 'Weekly',
  biweekly: 'Biweekly',
};

export const STRUCTURE_STATUS_LABELS: Record<StructureStatus, string> = {
  draft: 'Draft',
  active: 'Active',
  inactive: 'Inactive',
};

export const COMPONENT_TYPE_LABELS: Record<ComponentType, string> = {
  earning: 'Earning',
  deduction: 'Deduction',
};

export const CALCULATION_TYPE_LABELS: Record<CalculationType, string> = {
  fixed: 'Fixed amount',
  percentage: 'Percentage',
};

export const PERCENTAGE_BASIS_LABELS: Record<PercentageBasis, string> = {
  basic: 'of Basic',
  gross: 'of Gross',
};

export interface SalaryComponent {
  id: string;
  name: string;
  code: string;
  component_type: ComponentType;
  calculation_type: CalculationType;
  value: string;
  percentage_basis: PercentageBasis | null;
  description: string | null;
  status: 'active' | 'inactive';
  // Pay behaviour flags (Phase 2). Read by a later calculation phase.
  proration_allowed: boolean;
  attendance_impact: boolean;
  leave_impact: boolean;
  overtime_eligible: boolean;
  is_taxable: boolean;
  created_at: string;
  updated_at: string;
}

export interface StructureComponent {
  id: string;
  component: SalaryComponent;
  default_value: string | null;
}

export interface SalaryStructure {
  id: string;
  name: string;
  description: string | null;
  pay_frequency: PayFrequency;
  currency: string;
  status: StructureStatus;
  effective_from: string | null;
  effective_to: string | null;
  created_by: string | null;
  created_at: string;
  updated_at: string;
  components: StructureComponent[];
}

export interface EmployeeSummary {
  id: string;
  employee_code: string;
  full_name: string;
}

export interface CompensationComponent {
  id: string;
  component_id: string;
  name: string;
  code: string;
  component_type: ComponentType;
  calculation_type: CalculationType;
  value: string;
  percentage_basis: PercentageBasis | null;
}

export interface Compensation {
  id: string;
  employee_id: string;
  structure: Omit<SalaryStructure, 'components'>;
  currency: string;
  annual_ctc: string;
  annual_gross: string;
  monthly_gross: string;
  basic_salary: string;
  status: CompensationStatus;
  effective_from: string;
  effective_to: string | null;
  components: CompensationComponent[];
  created_at: string;
}

export interface EmployeeCompensationData {
  employee: EmployeeSummary;
  current: Compensation | null;
  records: Compensation[];
}

export interface CompensationListRow {
  id: string;
  employee: EmployeeSummary;
  structure_name: string;
  currency: string;
  annual_ctc: string;
  monthly_gross: string;
  status: CompensationStatus;
  effective_from: string;
  effective_to: string | null;
}

export interface SalaryHistoryEntry {
  id: string;
  employee_id: string;
  previous_annual_ctc: string | null;
  new_annual_ctc: string;
  currency: string;
  effective_from: string;
  reason: string | null;
  changed_by_name: string | null;
  created_at: string;
}

// ---------------------------------------------------------------------------
// Write payloads
// ---------------------------------------------------------------------------
export interface ComponentCreateInput {
  name: string;
  code: string;
  component_type: ComponentType;
  calculation_type: CalculationType;
  value: string;
  percentage_basis?: PercentageBasis | null;
  description?: string | null;
  proration_allowed?: boolean;
  attendance_impact?: boolean;
  leave_impact?: boolean;
  overtime_eligible?: boolean;
  is_taxable?: boolean;
}

export interface ComponentUpdateInput {
  name?: string;
  calculation_type?: CalculationType;
  value?: string;
  percentage_basis?: PercentageBasis | null;
  description?: string | null;
  proration_allowed?: boolean;
  attendance_impact?: boolean;
  leave_impact?: boolean;
  overtime_eligible?: boolean;
  is_taxable?: boolean;
}

export interface StructureComponentInput {
  component_id: string;
  default_value?: string | null;
}

export interface StructureCreateInput {
  name: string;
  description?: string | null;
  pay_frequency: PayFrequency;
  currency: string;
  effective_from?: string | null;
  effective_to?: string | null;
  components: StructureComponentInput[];
}

export type StructureUpdateInput = Partial<StructureCreateInput>;

export interface CompensationComponentInput {
  component_id: string;
  value: string;
}

export interface CompensationAssignInput {
  salary_structure_id: string;
  currency: string;
  annual_ctc: string;
  annual_gross: string;
  monthly_gross: string;
  basic_salary: string;
  effective_from: string;
  effective_to?: string | null;
  reason?: string | null;
  components: CompensationComponentInput[];
}

export interface SalaryRevisionInput {
  salary_structure_id: string;
  currency: string;
  annual_ctc: string;
  annual_gross: string;
  monthly_gross: string;
  basic_salary: string;
  effective_from: string;
  reason: string;
  components: CompensationComponentInput[];
}

// ---------------------------------------------------------------------------
// Phase 2 — payroll configuration and pay rules
// ---------------------------------------------------------------------------
export type WorkingDaysRule = 'calendar_days' | 'working_days' | 'custom_working_days';
export type PayrollDayBasis = 'calendar_days' | 'working_days';
export type UnpaidLeaveTreatment = 'deduct' | 'ignore';
export type RoundingRule = 'none' | 'nearest_whole' | 'nearest_half' | 'custom';
export type PayrollPeriodStatus =
  | 'open'
  | 'processing'
  | 'under_review'
  | 'approved'
  | 'finalized'
  | 'cancelled';
export type LeaveTreatment = 'paid' | 'unpaid';
export type PayrollEligibility = 'eligible' | 'not_eligible' | 'suspended';
export type PayrollEligibilityReason =
  | 'active_employee'
  | 'exited_employee'
  | 'contractor'
  | 'payroll_excluded'
  | 'pending_onboarding';

export const WORKING_DAYS_RULE_LABELS: Record<WorkingDaysRule, string> = {
  calendar_days: 'Calendar days',
  working_days: 'Working days',
  custom_working_days: 'Custom working days',
};

export const DAY_BASIS_LABELS: Record<PayrollDayBasis, string> = {
  calendar_days: 'Calendar days',
  working_days: 'Working days',
};

export const UNPAID_LEAVE_TREATMENT_LABELS: Record<UnpaidLeaveTreatment, string> = {
  deduct: 'Deduct from salary',
  ignore: 'Do not deduct',
};

export const ROUNDING_RULE_LABELS: Record<RoundingRule, string> = {
  none: 'No rounding',
  nearest_whole: 'Nearest whole number',
  nearest_half: 'Nearest 0.50',
  custom: 'Custom precision',
};

export const PERIOD_STATUS_LABELS: Record<PayrollPeriodStatus, string> = {
  open: 'Open',
  processing: 'Processing',
  under_review: 'Under review',
  approved: 'Approved',
  finalized: 'Finalized',
  cancelled: 'Cancelled',
};

/** Mirrors the server's transition table, for showing only reachable moves. */
export const PERIOD_TRANSITIONS: Record<PayrollPeriodStatus, PayrollPeriodStatus[]> = {
  open: ['processing', 'cancelled'],
  processing: ['under_review', 'open', 'cancelled'],
  under_review: ['approved', 'processing', 'cancelled'],
  approved: ['finalized', 'under_review', 'cancelled'],
  finalized: [],
  cancelled: [],
};

export const LEAVE_TREATMENT_LABELS: Record<LeaveTreatment, string> = {
  paid: 'Paid — no deduction',
  unpaid: 'Unpaid — salary deduction',
};

export const ELIGIBILITY_LABELS: Record<PayrollEligibility, string> = {
  eligible: 'Eligible',
  not_eligible: 'Not eligible',
  suspended: 'Suspended',
};

export const ELIGIBILITY_REASON_LABELS: Record<PayrollEligibilityReason, string> = {
  active_employee: 'Active employee',
  exited_employee: 'Exited employee',
  contractor: 'Contractor',
  payroll_excluded: 'Payroll excluded',
  pending_onboarding: 'Pending onboarding',
};

/** ISO weekday numbers as the API stores them: 0 = Monday .. 6 = Sunday. */
export const WEEKDAY_LABELS: readonly string[] = [
  'Monday',
  'Tuesday',
  'Wednesday',
  'Thursday',
  'Friday',
  'Saturday',
  'Sunday',
];

export interface PayrollConfig {
  id: string;
  pay_frequency: PayFrequency;
  period_start_day: number;
  period_end_day: number;
  pay_day: number;
  cutoff_day: number;
  currency: string;
  working_days_rule: WorkingDaysRule;
  weekly_off_days: number[];
  holiday_calendar_id: string | null;
  holiday_calendar_name: string | null;
  proration_basis: PayrollDayBasis;
  unpaid_leave_treatment: UnpaidLeaveTreatment;
  unpaid_leave_basis: PayrollDayBasis;
  overtime_enabled: boolean;
  overtime_basis: PercentageBasis;
  overtime_multiplier: string;
  overtime_min_hours: string;
  overtime_max_hours: string | null;
  overtime_approval_required: boolean;
  standard_daily_hours: string;
  deduct_absence: boolean;
  deduct_late_arrival: boolean;
  deduct_early_exit: boolean;
  require_approved_attendance: boolean;
  rounding_rule: RoundingRule;
  rounding_precision: string | null;
  updated_at: string;
}

export interface PayrollConfigUpdateInput extends Partial<Omit<PayrollConfig, 'id' | 'updated_at'>> {
  reason: string;
  effective_from: string;
  clear_holiday_calendar?: boolean;
  clear_overtime_max_hours?: boolean;
}

export interface PayrollConfigHistoryEntry {
  id: string;
  field: string;
  previous_value: string | null;
  new_value: string | null;
  effective_from: string;
  reason: string;
  changed_by_name: string | null;
  created_at: string;
}

export interface PayrollPeriod {
  id: string;
  name: string;
  start_date: string;
  end_date: string;
  pay_date: string;
  status: PayrollPeriodStatus;
  notes: string | null;
  created_at: string;
  updated_at: string;
}

export interface PayrollPeriodInput {
  name: string;
  start_date: string;
  end_date: string;
  pay_date: string;
  notes?: string | null;
}

export interface LeaveRule {
  id: string;
  leave_type_id: string;
  leave_type_name: string;
  leave_type_code: string;
  leave_type_is_paid: boolean;
  treatment: LeaveTreatment;
  deduction_basis: PayrollDayBasis | null;
  description: string | null;
  status: 'active' | 'inactive';
  updated_at: string;
}

export interface LeaveRuleCreateInput {
  leave_type_id: string;
  treatment: LeaveTreatment;
  deduction_basis?: PayrollDayBasis | null;
  description?: string | null;
}

export interface EmployeePayrollSettings {
  id: string;
  employee: EmployeeSummary;
  eligibility: PayrollEligibility;
  eligibility_reason: PayrollEligibilityReason | null;
  frequency_override: PayFrequency | null;
  proration_override: PayrollDayBasis | null;
  overtime_eligible: boolean | null;
  unpaid_leave_deduction: boolean | null;
  payroll_effective_date: string | null;
  notes: string | null;
  updated_at: string;
}

export interface EmployeeSettingsData {
  employee: EmployeeSummary;
  has_active_compensation: boolean;
  settings: EmployeePayrollSettings | null;
}

export interface EmployeeSettingsUpsertInput {
  eligibility: PayrollEligibility;
  eligibility_reason?: PayrollEligibilityReason | null;
  frequency_override?: PayFrequency | null;
  proration_override?: PayrollDayBasis | null;
  overtime_eligible?: boolean | null;
  unpaid_leave_deduction?: boolean | null;
  payroll_effective_date?: string | null;
  notes?: string | null;
}

// ---------------------------------------------------------------------------
// Phase 3 — payroll inputs
// ---------------------------------------------------------------------------
export type PayrollInputStatus = 'ready' | 'requires_review' | 'excluded';
export type PayrollExceptionCategory = 'attendance' | 'leave' | 'overtime' | 'compensation';

export const INPUT_STATUS_LABELS: Record<PayrollInputStatus, string> = {
  ready: 'Ready',
  requires_review: 'Requires review',
  excluded: 'Excluded',
};

export const EXCEPTION_CATEGORY_LABELS: Record<PayrollExceptionCategory, string> = {
  attendance: 'Attendance',
  leave: 'Leave',
  overtime: 'Overtime',
  compensation: 'Compensation',
};

export interface PayrollInputException {
  id: string;
  category: PayrollExceptionCategory;
  code: string;
  message: string;
  source_type: string | null;
  source_id: string | null;
  occurred_on: string | null;
}

export interface PayrollInputSourceLine {
  source_type: 'attendance' | 'regularization' | 'leave_request';
  source_id: string;
  source_updated_at: string;
}

export interface PayrollInput {
  id: string;
  period: PayrollPeriod;
  employee: EmployeeSummary;
  status: PayrollInputStatus;
  eligibility: PayrollEligibility;
  exclusion_reason: string | null;
  joining_date: string | null;
  exit_date: string | null;
  offboarding_status: string | null;
  eligible_days: number;
  non_eligible_days: number;
  proration_required: boolean;
  calendar_days: number;
  working_days: number;
  weekly_off_days: number;
  holiday_days: number;
  present_days: number;
  half_days: number;
  absent_days: number;
  late_days: number;
  early_exit_days: number;
  paid_leave_days: string;
  unpaid_leave_days: string;
  unpaid_leave_deduction: boolean;
  unpaid_leave_basis: PayrollDayBasis | null;
  overtime_hours: string;
  approved_overtime_hours: string;
  pending_overtime_hours: string;
  overtime_eligible: boolean;
  exception_count: number;
  source_changed: boolean;
  prepared_at: string;
  reviewed_at: string | null;
  reviewed_by_name: string | null;
  review_note: string | null;
}

export interface PayrollInputDetail extends PayrollInput {
  exceptions: PayrollInputException[];
  sources: PayrollInputSourceLine[];
}

export interface PayrollInputPrepareResult {
  prepared: number;
  ready: number;
  requires_review: number;
  excluded: number;
  removed: number;
}

export interface PayrollChangeDetectionResult {
  checked: number;
  flagged: number;
  flagged_employees: EmployeeSummary[];
}

export interface PeriodExceptionRow {
  employee: EmployeeSummary;
  category: PayrollExceptionCategory;
  code: string;
  message: string;
  source_type: string | null;
  occurred_on: string | null;
}

// ---------------------------------------------------------------------------
// Phase 4 — payroll runs and calculated records
// ---------------------------------------------------------------------------
export type PayrollRunStatus =
  | 'draft'
  | 'calculating'
  | 'requires_review'
  | 'calculated'
  | 'in_review'
  | 'review_complete'
  | 'pending_approval'
  | 'returned'
  | 'approved'
  | 'finalized';
export type PayrollRecordStatus =
  | 'calculated'
  | 'requires_review'
  | 'excluded'
  | 'reviewed'
  | 'adjustment_required'
  | 'ready_for_approval';
export type PayrollItemType = 'earning' | 'deduction';

export const RUN_STATUS_LABELS: Record<PayrollRunStatus, string> = {
  draft: 'Draft',
  calculating: 'Calculating',
  requires_review: 'Requires review',
  calculated: 'Calculated',
  in_review: 'In review',
  review_complete: 'Review complete',
  pending_approval: 'Pending approval',
  returned: 'Returned for correction',
  approved: 'Approved',
  finalized: 'Finalized',
};

export const RECORD_STATUS_LABELS: Record<PayrollRecordStatus, string> = {
  calculated: 'Calculated',
  requires_review: 'Requires review',
  excluded: 'Excluded',
  reviewed: 'Reviewed',
  adjustment_required: 'Adjustment required',
  ready_for_approval: 'Ready for approval',
};

export interface PayrollRun {
  id: string;
  run_code: string;
  period: PayrollPeriod;
  status: PayrollRunStatus;
  currency: string;
  employee_count: number;
  calculated_count: number;
  review_count: number;
  excluded_count: number;
  total_gross: string;
  total_deductions: string;
  total_net: string;
  calculated_at: string | null;
  calculated_by_name: string | null;
  notes: string | null;
  created_at: string;
  open_exception_count: number;
  open_critical_count: number;
  /** Approval workflow (Phase 6). */
  review_completed_at: string | null;
  review_completed_by_name: string | null;
  submitted_at: string | null;
  submitted_by_name: string | null;
  approved_at: string | null;
  approved_by_name: string | null;
  approval_comment: string | null;
  returned_at: string | null;
  returned_by_name: string | null;
  return_reason: string | null;
  finalized_at: string | null;
  finalized_by_name: string | null;
  adjustment_count: number;
}

export interface PayrollLineItem {
  id: string;
  item_type: PayrollItemType;
  source: 'component' | 'overtime' | 'unpaid_leave';
  code: string;
  name: string;
  calculation_basis: string;
  original_amount: string | null;
  prorated: boolean;
  amount: string;
}

export interface PayrollRecord {
  id: string;
  run_id: string;
  employee: EmployeeSummary;
  status: PayrollRecordStatus;
  exception_reason: string | null;
  currency: string;
  gross_earnings: string;
  total_deductions: string;
  net_pay: string;
  /** Review adjustments (Phase 5): originals above are never edited. */
  adjustment_earnings: string;
  adjustment_deductions: string;
  final_gross: string;
  final_deductions: string;
  final_net: string;
  calendar_days: number;
  working_days: number;
  eligible_days: number;
  present_days: number;
  paid_leave_days: string;
  unpaid_leave_days: string;
  overtime_hours_paid: string;
  proration_basis: PayrollDayBasis | null;
}

export interface PayrollRecordDetail extends PayrollRecord {
  period: PayrollPeriod;
  structure_name: string | null;
  monthly_basic: string | null;
  monthly_gross: string | null;
  annual_ctc: string | null;
  line_items: PayrollLineItem[];
  adjustments: PayrollAdjustment[];
}

export interface PayrollCalculationResult {
  run: PayrollRun;
  calculated: number;
  requires_review: number;
  excluded: number;
}

// ---------------------------------------------------------------------------
// Phase 5 — payroll review and adjustments
// ---------------------------------------------------------------------------
export type PayrollExceptionSeverity = 'warning' | 'error' | 'critical';
export type PayrollExceptionStatus = 'open' | 'resolved';
export type PayrollAdjustmentStatus = 'active' | 'cancelled';
export type PayrollRunExceptionType =
  | 'missing_salary'
  | 'invalid_compensation'
  | 'missing_attendance'
  | 'unresolved_correction'
  | 'unapproved_overtime'
  | 'invalid_leave'
  | 'negative_leave_balance'
  | 'invalid_component'
  | 'calculation_mismatch'
  | 'missing_input'
  | 'other';

export const EXCEPTION_SEVERITY_LABELS: Record<PayrollExceptionSeverity, string> = {
  warning: 'Warning',
  error: 'Error',
  critical: 'Critical',
};

export const EXCEPTION_STATUS_LABELS: Record<PayrollExceptionStatus, string> = {
  open: 'Open',
  resolved: 'Resolved',
};

export const EXCEPTION_TYPE_LABELS: Record<PayrollRunExceptionType, string> = {
  missing_salary: 'Missing salary',
  invalid_compensation: 'Invalid compensation',
  missing_attendance: 'Missing attendance',
  unresolved_correction: 'Unresolved correction',
  unapproved_overtime: 'Unapproved overtime',
  invalid_leave: 'Invalid leave',
  negative_leave_balance: 'Negative leave balance',
  invalid_component: 'Invalid component',
  calculation_mismatch: 'Calculation mismatch',
  missing_input: 'Input requires review',
  other: 'Other',
};

export const ADJUSTMENT_STATUS_LABELS: Record<PayrollAdjustmentStatus, string> = {
  active: 'Active',
  cancelled: 'Cancelled',
};

export interface PayrollRunException {
  id: string;
  run_id: string;
  employee: EmployeeSummary;
  exception_type: PayrollRunExceptionType;
  severity: PayrollExceptionSeverity;
  description: string;
  status: PayrollExceptionStatus;
  resolution: string | null;
  resolution_notes: string | null;
  resolved_by_name: string | null;
  resolved_at: string | null;
  created_at: string;
}

export interface PayrollAdjustment {
  id: string;
  run_id: string;
  employee: EmployeeSummary;
  item_type: PayrollItemType;
  name: string;
  amount: string;
  reason: string;
  notes: string | null;
  status: PayrollAdjustmentStatus;
  previous_net: string;
  new_net: string;
  created_at: string;
  cancelled_at: string | null;
  cancel_reason: string | null;
}

export interface PayrollAdjustmentCreateInput {
  item_type: PayrollItemType;
  name: string;
  amount: string;
  reason: string;
  notes?: string | null;
}

export interface ChecklistItem {
  item_key: string;
  label: string;
  completed: boolean;
  completed_by_name: string | null;
  completed_at: string | null;
}

export interface ReviewComment {
  id: string;
  run_id: string;
  employee: EmployeeSummary | null;
  comment: string;
  author_name: string | null;
  created_at: string;
}

export interface ReviewReadiness {
  can_complete: boolean;
  open_critical_exceptions: number;
  records_requiring_review: number;
  records_adjustment_required: number;
  incomplete_checklist_items: string[];
}

export interface PayrollReconciliation {
  run_id: string;
  currency: string;
  original_gross: string;
  adjustment_earnings: string;
  final_gross: string;
  original_deductions: string;
  adjustment_deductions: string;
  final_deductions: string;
  original_net: string;
  net_adjustment: string;
  final_net: string;
  adjustment_count: number;
  cancelled_adjustment_count: number;
  total_adjustment_amount: string;
  employees_affected: number;
}

// ---------------------------------------------------------------------------
// Phase 6 — payroll approval and finalization
// ---------------------------------------------------------------------------
export type PayrollApprovalAction = 'submitted' | 'approved' | 'returned' | 'finalized';

export const APPROVAL_ACTION_LABELS: Record<PayrollApprovalAction, string> = {
  submitted: 'Submitted for approval',
  approved: 'Approved',
  returned: 'Returned for correction',
  finalized: 'Finalized',
};

export interface PayrollApprovalStep {
  id: string;
  run_id: string;
  action: PayrollApprovalAction;
  actor_name: string | null;
  comment: string | null;
  employee_count: number;
  total_gross: string;
  total_deductions: string;
  total_net: string;
  created_at: string;
}

export interface ApprovalEmployeeSummary {
  included: number;
  excluded: number;
  with_adjustments: number;
  with_exceptions: number;
}

export interface ApprovalReviewSummary {
  review_completed: boolean;
  reviewer_name: string | null;
  critical_exceptions: number;
  error_exceptions: number;
  warning_exceptions: number;
  open_exceptions: number;
  adjustment_count: number;
}

export interface PayrollApprovalSummary {
  run: PayrollRun;
  employees: ApprovalEmployeeSummary;
  review: ApprovalReviewSummary;
  blockers: string[];
  can_approve: boolean;
  trail: PayrollApprovalStep[];
}

export interface PayrollSnapshotLine {
  item_type: PayrollItemType;
  source: string;
  code: string;
  name: string;
  calculation_basis: string;
  original_amount: string | null;
  prorated: boolean;
  amount: string;
}

export interface PayrollSnapshotAdjustment {
  name: string;
  item_type: PayrollItemType;
  amount: string;
  reason: string;
  status: PayrollAdjustmentStatus;
  cancel_reason: string | null;
  created_at: string;
}

export interface PayrollSnapshot {
  id: string;
  run_id: string;
  employee_id: string;
  employee_code: string;
  employee_name: string;
  period_name: string;
  period_start: string;
  period_end: string;
  pay_date: string;
  status: PayrollRecordStatus;
  exception_reason: string | null;
  currency: string;
  structure_name: string | null;
  monthly_basic: string | null;
  monthly_gross: string | null;
  annual_ctc: string | null;
  gross_earnings: string;
  total_deductions: string;
  net_pay: string;
  adjustment_earnings: string;
  adjustment_deductions: string;
  final_gross: string;
  final_deductions: string;
  final_net: string;
  line_items: PayrollSnapshotLine[];
  adjustments: PayrollSnapshotAdjustment[];
  approved_by_name: string | null;
  approved_at: string | null;
  finalized_by_name: string | null;
  finalized_at: string;
}

// ---------------------------------------------------------------------------
// Phase 7 — payslips
// ---------------------------------------------------------------------------
export type PayslipStatus = 'generated';

export const PAYSLIP_STATUS_LABELS: Record<PayslipStatus, string> = {
  generated: 'Generated',
};

export interface Payslip {
  id: string;
  payslip_number: string;
  run_id: string;
  employee: EmployeeSummary;
  period: PayrollPeriod;
  payroll_month: string;
  status: PayslipStatus;
  currency: string;
  gross_earnings: string;
  total_deductions: string;
  net_pay: string;
  generated_at: string;
  regenerated_at: string | null;
}

export interface PayslipEmployer {
  name: string | null;
  address: string | null;
  logo_url: string | null;
}

export interface PayslipEmployeeDetails {
  name: string;
  employee_code: string;
  department: string | null;
  designation: string | null;
  joining_date: string | null;
  bank_name: string | null;
  account_masked: string | null;
}

export interface PayslipLine {
  name: string;
  code: string | null;
  calculation_basis: string | null;
  amount: string;
}

export interface PayslipDetail extends Payslip {
  employer: PayslipEmployer;
  employee_details: PayslipEmployeeDetails;
  period_start: string;
  period_end: string;
  pay_date: string;
  pay_frequency: PayFrequency;
  earnings: PayslipLine[];
  deductions: PayslipLine[];
  amount_in_words: string;
  generated_by_name: string | null;
  structure_name: string | null;
}

export interface PayslipGenerationResult {
  run_id: string;
  generated: number;
  already_existed: number;
  skipped_excluded: number;
  payslips: Payslip[];
}

export interface PayslipFilters {
  employee_id?: string;
  month?: string;
  team_id?: string;
  payslip_number?: string;
  run_id?: string;
  page?: number;
  page_size?: number;
}

// ---------------------------------------------------------------------------
// Phase 8 — reports and full & final settlement
// ---------------------------------------------------------------------------
export type PayrollReportKind =
  | 'summary'
  | 'monthly'
  | 'earnings'
  | 'deductions'
  | 'overtime'
  | 'unpaid_leave';

export const REPORT_KIND_LABELS: Record<PayrollReportKind, string> = {
  summary: 'Summary',
  monthly: 'Monthly payroll',
  earnings: 'Earnings',
  deductions: 'Deductions',
  overtime: 'Overtime',
  unpaid_leave: 'Unpaid leave',
};

export interface PayrollReportFilters {
  period_id?: string;
  date_from?: string;
  date_to?: string;
  team_id?: string;
  location_id?: string;
  employee_id?: string;
  status?: PayrollRunStatus;
}

export interface PayrollReportSummary {
  employee_count: number;
  run_count: number;
  gross_payroll: string;
  total_deductions: string;
  net_payroll: string;
  total_adjustments: string;
  total_overtime: string;
  total_overtime_hours: string;
  total_unpaid_leave: string;
  total_unpaid_leave_days: string;
  total_employer_cost: string;
  employer_cost_supported: boolean;
  currency: string;
}

export interface MonthlyReportRow {
  employee_id: string;
  employee_name: string;
  employee_code: string;
  department: string | null;
  location: string | null;
  period_name: string;
  period_end: string;
  run_status: PayrollRunStatus;
  record_status: string;
  gross: string;
  deductions: string;
  adjustments: string;
  net_pay: string;
  currency: string;
}

export interface EarningsReportRow {
  employee_id: string;
  employee_name: string;
  employee_code: string;
  department: string | null;
  period_name: string;
  basic_salary: string;
  allowances: string;
  bonus: string;
  overtime: string;
  other_earnings: string;
  total_gross: string;
  currency: string;
}

export interface DeductionReportRow {
  employee_id: string;
  employee_name: string;
  employee_code: string;
  department: string | null;
  period_name: string;
  component: string;
  code: string | null;
  amount: string;
  currency: string;
}

export interface OvertimeReportRow {
  employee_id: string;
  employee_name: string;
  employee_code: string;
  department: string | null;
  period_name: string;
  approved_overtime_hours: string;
  overtime_amount: string;
  currency: string;
}

export interface UnpaidLeaveReportRow {
  employee_id: string;
  employee_name: string;
  employee_code: string;
  department: string | null;
  period_name: string;
  unpaid_leave_days: string;
  deduction_basis: string | null;
  deduction_amount: string;
  currency: string;
}

export interface PayrollReport {
  kind: PayrollReportKind;
  filters: PayrollReportFilters;
  summary: PayrollReportSummary;
  monthly: MonthlyReportRow[];
  earnings: EarningsReportRow[];
  deductions: DeductionReportRow[];
  overtime: OvertimeReportRow[];
  unpaid_leave: UnpaidLeaveReportRow[];
}

export type FinalSettlementStatus = 'draft' | 'under_review' | 'approved' | 'settled';
export type SettlementListStatus = FinalSettlementStatus | 'not_started';
export type SettlementAdjustmentType =
  | 'final_bonus'
  | 'incentive'
  | 'leave_encashment'
  | 'other_earning'
  | 'recovery'
  | 'asset_recovery'
  | 'other_deduction';
export type SettlementAdjustmentStatus = 'pending' | 'approved' | 'rejected';
export type SettlementItemCategory = 'earning' | 'encashment' | 'adjustment' | 'deduction';

export const SETTLEMENT_STATUS_LABELS: Record<SettlementListStatus, string> = {
  not_started: 'Not started',
  draft: 'Draft',
  under_review: 'Under review',
  approved: 'Approved',
  settled: 'Settled',
};

export const SETTLEMENT_ADJUSTMENT_TYPE_LABELS: Record<SettlementAdjustmentType, string> = {
  final_bonus: 'Final bonus',
  incentive: 'Incentive',
  leave_encashment: 'Leave encashment',
  other_earning: 'Other approved earning',
  recovery: 'Recovery',
  asset_recovery: 'Asset recovery',
  other_deduction: 'Other approved deduction',
};

export const SETTLEMENT_ITEM_CATEGORY_LABELS: Record<SettlementItemCategory, string> = {
  earning: 'Final earnings',
  encashment: 'Approved encashments',
  adjustment: 'Approved adjustments',
  deduction: 'Final deductions',
};

export interface EligibleExitRow {
  employee: EmployeeSummary;
  department: string | null;
  joining_date: string | null;
  last_working_date: string;
  exit_type: string;
  exit_reason: string | null;
  offboarding_case_id: string;
  offboarding_status: string;
  final_period_name: string | null;
  settlement_id: string | null;
  settlement_status: SettlementListStatus;
  eligible: boolean;
  ineligibility_reason: string | null;
}

export interface SettlementItem {
  id: string;
  category: SettlementItemCategory;
  code: string;
  name: string;
  basis: string | null;
  quantity: string | null;
  amount: string;
  source: string;
}

export interface SettlementAdjustment {
  id: string;
  adjustment_type: SettlementAdjustmentType;
  is_earning: boolean;
  name: string;
  amount: string;
  reason: string;
  notes: string | null;
  status: SettlementAdjustmentStatus;
  created_by_name: string | null;
  created_at: string;
  decided_by_name: string | null;
  decided_at: string | null;
  decision_note: string | null;
}

export interface SettlementAdjustmentInput {
  adjustment_type: SettlementAdjustmentType;
  name: string;
  amount: string;
  reason: string;
  notes?: string | null;
}

export interface SettlementIssue {
  severity: 'critical' | 'warning' | 'info' | string;
  message: string;
}

export interface SettlementLeaveRow {
  leave_type: string;
  code: string;
  is_paid: boolean;
  eligible: string;
  used: string;
  remaining: string;
  encashable: boolean;
}

export interface SettlementAssetRow {
  asset_name: string;
  asset_tag: string | null;
  assignment_status: string;
  return_status: string;
  recovery_amount: string | null;
  recovery_approved: boolean;
}

export interface Settlement {
  id: string;
  settlement_code: string;
  employee: EmployeeSummary;
  department: string | null;
  status: FinalSettlementStatus;
  currency: string;
  joining_date: string | null;
  last_working_date: string;
  exit_type: string;
  exit_reason: string | null;
  final_period_name: string | null;
  final_earnings: string;
  approved_encashments: string;
  approved_adjustments: string;
  final_deductions: string;
  settlement_amount: string;
  calculated_at: string | null;
  submitted_at: string | null;
  review_completed_at: string | null;
  approved_at: string | null;
  settled_at: string | null;
  created_at: string;
}

export interface SettlementDetail extends Settlement {
  notes: string | null;
  offboarding_case_id: string;
  offboarding_status: string;
  monthly_gross: string | null;
  basic_salary: string | null;
  daily_rate: string | null;
  paid_through: string | null;
  unpaid_salary_days: number;
  unpaid_leave_days: string;
  overtime_hours: string;
  leave_summary: SettlementLeaveRow[];
  assets: SettlementAssetRow[];
  issues: SettlementIssue[];
  critical_issue_count: number;
  items: SettlementItem[];
  adjustments: SettlementAdjustment[];
  submitted_by_name: string | null;
  review_completed_by_name: string | null;
  approved_by_name: string | null;
  approval_comment: string | null;
  settled_by_name: string | null;
  settlement_reference: string | null;
  can_approve: boolean;
}

export interface MySettlement {
  settlement_code: string;
  status: FinalSettlementStatus;
  currency: string;
  last_working_date: string;
  settled_at: string | null;
  final_earnings: string;
  approved_encashments: string;
  approved_adjustments: string;
  final_deductions: string;
  settlement_amount: string;
  items: SettlementItem[];
  settlement_reference: string | null;
}

export interface PayrollComparisonRow {
  employee: EmployeeSummary;
  previous_gross: string | null;
  current_gross: string;
  gross_difference: string | null;
  previous_deductions: string | null;
  current_deductions: string;
  deduction_difference: string | null;
  previous_net: string | null;
  current_net: string;
  net_difference: string | null;
  notable: boolean;
}

/**
 * Display formatting only. The exact decimal string stays the source of
 * truth; this renders it with the currency for humans.
 */
export function formatMoney(value: string, currency: string): string {
  const amount = Number(value);
  if (Number.isNaN(amount)) return value;
  try {
    return new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency,
      maximumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${currency} ${value}`;
  }
}

/** "40.00" + percentage/basic -> "40% of Basic"; fixed -> "₹ 40.00". */
export function describeComponentValue(component: {
  calculation_type: CalculationType;
  value: string;
  percentage_basis: PercentageBasis | null;
}): string {
  if (component.calculation_type === 'percentage') {
    const basis = component.percentage_basis
      ? ` ${PERCENTAGE_BASIS_LABELS[component.percentage_basis]}`
      : '';
    return `${component.value}%${basis}`;
  }
  return component.value;
}
