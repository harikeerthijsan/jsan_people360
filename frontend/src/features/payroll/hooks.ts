'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult } from '@tanstack/react-query';

import { toast } from '@/components/ui/sonner';
import type { AppError } from '@/lib/errors';

import { payrollApi } from './api';
import type {
  ChecklistItem,
  Compensation,
  CompensationAssignInput,
  ComponentCreateInput,
  ComponentUpdateInput,
  EmployeeSettingsData,
  EmployeeSettingsUpsertInput,
  LeaveRule,
  LeaveRuleCreateInput,
  PayrollAdjustment,
  PayrollAdjustmentCreateInput,
  PayrollCalculationResult,
  PayrollChangeDetectionResult,
  PayrollConfig,
  PayrollConfigUpdateInput,
  PayrollInput,
  PayrollInputPrepareResult,
  PayrollPeriod,
  PayrollRun,
  PayrollRunException,
  Payslip,
  PayslipFilters,
  PayslipGenerationResult,
  PayrollReportFilters,
  PayrollReportKind,
  SettlementAdjustmentInput,
  SettlementDetail,
  PayrollPeriodInput,
  PayrollPeriodStatus,
  ReviewComment,
  ReviewReadiness,
  SalaryComponent,
  SalaryRevisionInput,
  SalaryStructure,
  StructureCreateInput,
  StructureStatus,
  StructureUpdateInput,
} from './types';

/**
 * Data hooks for the payroll screens.
 *
 * Two query roots, matching the two audiences: the employee's own page must
 * not be evicted every time an administrator edits a component, and the admin
 * register must not be evicted by an employee opening their payslip-to-be.
 *
 * Within the admin root, a write invalidates the whole root: assigning a
 * salary changes the register, the employee's salary page and their history
 * at once, and invalidating selectively is how two numbers on the same screen
 * end up disagreeing.
 */

const mineKey = ['me', 'payroll'] as const;
const adminKey = ['payroll'] as const;

// ---------------------------------------------------------------------------
// Employee
// ---------------------------------------------------------------------------
export const useMyCompensation = () =>
  useQuery({ queryKey: [...mineKey, 'compensation'], queryFn: () => payrollApi.mine.compensation() });

export const useMySalaryHistory = () =>
  useQuery({ queryKey: [...mineKey, 'history'], queryFn: () => payrollApi.mine.history() });

// ---------------------------------------------------------------------------
// Admin: reads
// ---------------------------------------------------------------------------
export const useSalaryComponents = (includeInactive = false) =>
  useQuery({
    queryKey: [...adminKey, 'components', includeInactive],
    queryFn: () => payrollApi.admin.components(includeInactive),
    // Master data: changes rarely, read on nearly every payroll screen.
    staleTime: 5 * 60_000,
  });

export const useSalaryStructures = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...adminKey, 'structures', params],
    queryFn: () => payrollApi.admin.structures(params),
    placeholderData: (previous) => previous,
  });

export const usePayrollRegister = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...adminKey, 'register', params],
    queryFn: () => payrollApi.admin.register(params),
    placeholderData: (previous) => previous,
  });

export const useEmployeeCompensation = (employeeId: string) =>
  useQuery({
    queryKey: [...adminKey, 'employee', employeeId],
    queryFn: () => payrollApi.admin.employeeCompensation(employeeId),
    enabled: Boolean(employeeId),
  });

export const useEmployeeSalaryHistory = (employeeId: string, enabled = true) =>
  useQuery({
    queryKey: [...adminKey, 'history', employeeId],
    queryFn: () => payrollApi.admin.history(employeeId),
    enabled: Boolean(employeeId) && enabled,
  });

// ---------------------------------------------------------------------------
// Admin: writes
// ---------------------------------------------------------------------------
const usePayrollMutation = <TInput, TResult>(
  fn: (input: TInput) => Promise<TResult>,
  message: string,
): UseMutationResult<TResult, AppError, TInput> => {
  const queryClient = useQueryClient();
  return useMutation<TResult, AppError, TInput>({
    mutationFn: fn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: adminKey });
      // A salary change is also visible on the employee's own page.
      void queryClient.invalidateQueries({ queryKey: mineKey });
      toast.success(message);
    },
    onError: (error) => toast.error(error.message),
  });
};

export const useCreateComponent = (): UseMutationResult<SalaryComponent, AppError, ComponentCreateInput> =>
  usePayrollMutation((input) => payrollApi.admin.createComponent(input), 'Component created');

export const useUpdateComponent = () =>
  usePayrollMutation(
    ({ componentId, payload }: { componentId: string; payload: ComponentUpdateInput }) =>
      payrollApi.admin.updateComponent(componentId, payload),
    'Component updated',
  );

export const useSetComponentStatus = () =>
  usePayrollMutation(
    ({ componentId, status }: { componentId: string; status: 'active' | 'inactive' }) =>
      payrollApi.admin.setComponentStatus(componentId, status),
    'Status updated',
  );

export const useCreateStructure = (): UseMutationResult<SalaryStructure, AppError, StructureCreateInput> =>
  usePayrollMutation((input) => payrollApi.admin.createStructure(input), 'Structure created');

export const useUpdateStructure = () =>
  usePayrollMutation(
    ({ structureId, payload }: { structureId: string; payload: StructureUpdateInput }) =>
      payrollApi.admin.updateStructure(structureId, payload),
    'Structure updated',
  );

export const useSetStructureStatus = () =>
  usePayrollMutation(
    ({ structureId, status }: { structureId: string; status: Exclude<StructureStatus, 'draft'> }) =>
      payrollApi.admin.setStructureStatus(structureId, status),
    'Status updated',
  );

export const useAssignCompensation = (): UseMutationResult<
  Compensation,
  AppError,
  { employeeId: string; payload: CompensationAssignInput }
> =>
  usePayrollMutation(
    ({ employeeId, payload }) => payrollApi.admin.assign(employeeId, payload),
    'Compensation assigned',
  );

export const useReviseSalary = (): UseMutationResult<
  Compensation,
  AppError,
  { employeeId: string; payload: SalaryRevisionInput }
> =>
  usePayrollMutation(
    ({ employeeId, payload }) => payrollApi.admin.revise(employeeId, payload),
    'Salary revised',
  );

// ---------------------------------------------------------------------------
// Phase 2 — configuration, periods, rules, employee settings
// ---------------------------------------------------------------------------
export const usePayrollConfig = () =>
  useQuery({ queryKey: [...adminKey, 'config'], queryFn: () => payrollApi.config.get() });

export const usePayrollConfigHistory = () =>
  useQuery({
    queryKey: [...adminKey, 'config-history'],
    queryFn: () => payrollApi.config.history(),
  });

export const useUpdatePayrollConfig = (): UseMutationResult<
  PayrollConfig,
  AppError,
  PayrollConfigUpdateInput
> => usePayrollMutation((input) => payrollApi.config.update(input), 'Configuration updated');

export const usePayrollPeriods = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...adminKey, 'periods', params],
    queryFn: () => payrollApi.periods.list(params),
    placeholderData: (previous) => previous,
  });

export const useCreatePayrollPeriod = (): UseMutationResult<PayrollPeriod, AppError, PayrollPeriodInput> =>
  usePayrollMutation((input) => payrollApi.periods.create(input), 'Period created');

export const useUpdatePayrollPeriod = () =>
  usePayrollMutation(
    ({ periodId, payload }: { periodId: string; payload: Partial<PayrollPeriodInput> }) =>
      payrollApi.periods.update(periodId, payload),
    'Period updated',
  );

export const useSetPeriodStatus = () =>
  usePayrollMutation(
    ({ periodId, status }: { periodId: string; status: PayrollPeriodStatus }) =>
      payrollApi.periods.setStatus(periodId, status),
    'Status updated',
  );

export const useLeaveRules = (includeInactive = false) =>
  useQuery({
    queryKey: [...adminKey, 'leave-rules', includeInactive],
    queryFn: () => payrollApi.leaveRules.list(includeInactive),
  });

export const useCreateLeaveRule = (): UseMutationResult<LeaveRule, AppError, LeaveRuleCreateInput> =>
  usePayrollMutation((input) => payrollApi.leaveRules.create(input), 'Rule created');

export const useUpdateLeaveRule = () =>
  usePayrollMutation(
    ({
      ruleId,
      payload,
    }: {
      ruleId: string;
      payload: Partial<Omit<LeaveRuleCreateInput, 'leave_type_id'>>;
    }) => payrollApi.leaveRules.update(ruleId, payload),
    'Rule updated',
  );

export const useSetLeaveRuleStatus = () =>
  usePayrollMutation(
    ({ ruleId, status }: { ruleId: string; status: 'active' | 'inactive' }) =>
      payrollApi.leaveRules.setStatus(ruleId, status),
    'Status updated',
  );

export const useEmployeeSettingsList = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...adminKey, 'employee-settings', params],
    queryFn: () => payrollApi.employeeSettings.list(params),
    placeholderData: (previous) => previous,
  });

export const useEmployeePayrollSettings = (employeeId: string) =>
  useQuery({
    queryKey: [...adminKey, 'employee-settings', 'detail', employeeId],
    queryFn: () => payrollApi.employeeSettings.forEmployee(employeeId),
    enabled: Boolean(employeeId),
  });

export const useUpsertEmployeeSettings = (): UseMutationResult<
  EmployeeSettingsData,
  AppError,
  { employeeId: string; payload: EmployeeSettingsUpsertInput }
> =>
  usePayrollMutation(
    ({ employeeId, payload }) => payrollApi.employeeSettings.upsert(employeeId, payload),
    'Settings saved',
  );

// ---------------------------------------------------------------------------
// Phase 3 — payroll inputs
// ---------------------------------------------------------------------------
export const useMyPayrollInputs = () =>
  useQuery({ queryKey: [...mineKey, 'inputs'], queryFn: () => payrollApi.inputs.mine() });

export const usePayrollInputs = (periodId: string, params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...adminKey, 'inputs', periodId, params],
    queryFn: () => payrollApi.inputs.list(periodId, params),
    enabled: Boolean(periodId),
    placeholderData: (previous) => previous,
  });

export const usePayrollInputDetail = (periodId: string, employeeId: string) =>
  useQuery({
    queryKey: [...adminKey, 'inputs', periodId, 'detail', employeeId],
    queryFn: () => payrollApi.inputs.detail(periodId, employeeId),
    enabled: Boolean(periodId) && Boolean(employeeId),
  });

export const usePeriodExceptions = (periodId: string) =>
  useQuery({
    queryKey: [...adminKey, 'inputs', periodId, 'exceptions'],
    queryFn: () => payrollApi.inputs.exceptions(periodId),
    enabled: Boolean(periodId),
  });

export const useGeneratePayrollInputs = (): UseMutationResult<
  PayrollInputPrepareResult,
  AppError,
  string
> => usePayrollMutation((periodId) => payrollApi.inputs.generate(periodId), 'Payroll inputs prepared');

export const useDetectInputChanges = (): UseMutationResult<
  PayrollChangeDetectionResult,
  AppError,
  string
> =>
  usePayrollMutation(
    (periodId) => payrollApi.inputs.detectChanges(periodId),
    'Change detection finished',
  );

export const useReviewPayrollInput = (): UseMutationResult<
  PayrollInput,
  AppError,
  { inputId: string; note: string | null }
> =>
  usePayrollMutation(
    ({ inputId, note }) => payrollApi.inputs.review(inputId, note),
    'Input reviewed',
  );

// ---------------------------------------------------------------------------
// Phase 4 — payroll runs
// ---------------------------------------------------------------------------
export const useMyPayrollRecords = () =>
  useQuery({ queryKey: [...mineKey, 'records'], queryFn: () => payrollApi.runs.mine() });

export const usePayrollRuns = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...adminKey, 'runs', params],
    queryFn: () => payrollApi.runs.list(params),
    placeholderData: (previous) => previous,
  });

export const usePayrollRun = (runId: string) =>
  useQuery({
    queryKey: [...adminKey, 'runs', 'detail', runId],
    queryFn: () => payrollApi.runs.get(runId),
    enabled: Boolean(runId),
  });

export const usePayrollRunRecords = (runId: string, params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...adminKey, 'runs', runId, 'records', params],
    queryFn: () => payrollApi.runs.records(runId, params),
    enabled: Boolean(runId),
    placeholderData: (previous) => previous,
  });

export const usePayrollRunRecord = (runId: string, employeeId: string) =>
  useQuery({
    queryKey: [...adminKey, 'runs', runId, 'record', employeeId],
    queryFn: () => payrollApi.runs.record(runId, employeeId),
    enabled: Boolean(runId) && Boolean(employeeId),
  });

export const useCreatePayrollRun = (): UseMutationResult<
  PayrollRun,
  AppError,
  { periodId: string; notes?: string | null }
> =>
  usePayrollMutation(
    ({ periodId, notes }) => payrollApi.runs.create(periodId, notes),
    'Payroll run created',
  );

export const useCalculateRun = (): UseMutationResult<PayrollCalculationResult, AppError, string> =>
  usePayrollMutation((runId) => payrollApi.runs.calculate(runId), 'Payroll calculated');

export const useRecalculateRun = (): UseMutationResult<PayrollCalculationResult, AppError, string> =>
  usePayrollMutation((runId) => payrollApi.runs.recalculate(runId), 'Payroll recalculated');

// ---------------------------------------------------------------------------
// Phase 5 — payroll review
// ---------------------------------------------------------------------------
export const useRunExceptions = (runId: string, params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...adminKey, 'runs', runId, 'exceptions', params],
    queryFn: () => payrollApi.review.exceptions(runId, params),
    enabled: Boolean(runId),
  });

export const useRunAdjustments = (runId: string) =>
  useQuery({
    queryKey: [...adminKey, 'runs', runId, 'adjustments'],
    queryFn: () => payrollApi.review.adjustments(runId),
    enabled: Boolean(runId),
  });

export const useReviewChecklist = (runId: string) =>
  useQuery({
    queryKey: [...adminKey, 'runs', runId, 'checklist'],
    queryFn: () => payrollApi.review.checklist(runId),
    enabled: Boolean(runId),
  });

export const useReviewReadiness = (runId: string) =>
  useQuery({
    queryKey: [...adminKey, 'runs', runId, 'readiness'],
    queryFn: () => payrollApi.review.readiness(runId),
    enabled: Boolean(runId),
  });

export const useReviewComments = (runId: string, employeeId?: string) =>
  useQuery({
    queryKey: [...adminKey, 'runs', runId, 'comments', employeeId ?? 'all'],
    queryFn: () => payrollApi.review.comments(runId, employeeId),
    enabled: Boolean(runId),
  });

export const useRunReconciliation = (runId: string) =>
  useQuery({
    queryKey: [...adminKey, 'runs', runId, 'reconciliation'],
    queryFn: () => payrollApi.review.reconciliation(runId),
    enabled: Boolean(runId),
  });

export const useRunComparison = (runId: string) =>
  useQuery({
    queryKey: [...adminKey, 'runs', runId, 'comparison'],
    queryFn: () => payrollApi.review.comparison(runId),
    enabled: Boolean(runId),
  });

export const useResolveException = (): UseMutationResult<
  PayrollRunException,
  AppError,
  { runId: string; exceptionId: string; resolution: string; notes?: string | null }
> =>
  usePayrollMutation(
    ({ runId, exceptionId, resolution, notes }) =>
      payrollApi.review.resolveException(runId, exceptionId, resolution, notes),
    'Exception resolved',
  );

export const useCreateAdjustment = (): UseMutationResult<
  PayrollAdjustment,
  AppError,
  { runId: string; employeeId: string; payload: PayrollAdjustmentCreateInput }
> =>
  usePayrollMutation(
    ({ runId, employeeId, payload }) =>
      payrollApi.review.createAdjustment(runId, employeeId, payload),
    'Adjustment added',
  );

export const useCancelAdjustment = (): UseMutationResult<
  PayrollAdjustment,
  AppError,
  { runId: string; adjustmentId: string; reason: string }
> =>
  usePayrollMutation(
    ({ runId, adjustmentId, reason }) =>
      payrollApi.review.cancelAdjustment(runId, adjustmentId, reason),
    'Adjustment cancelled',
  );

export const useMarkRecord = (): UseMutationResult<
  null,
  AppError,
  { runId: string; employeeId: string; status: 'reviewed' | 'adjustment_required'; note?: string | null }
> =>
  usePayrollMutation(
    ({ runId, employeeId, status, note }) =>
      payrollApi.review.markRecord(runId, employeeId, status, note),
    'Record marked',
  );

export const useUpdateChecklistItem = (): UseMutationResult<
  ChecklistItem[],
  AppError,
  { runId: string; itemKey: string; completed: boolean }
> =>
  usePayrollMutation(
    ({ runId, itemKey, completed }) => payrollApi.review.updateChecklist(runId, itemKey, completed),
    'Checklist updated',
  );

export const useCompleteReview = (): UseMutationResult<ReviewReadiness, AppError, string> =>
  usePayrollMutation((runId) => payrollApi.review.complete(runId), 'Review completed');

export const useAddReviewComment = (): UseMutationResult<
  ReviewComment,
  AppError,
  { runId: string; comment: string; employeeId?: string | null }
> =>
  usePayrollMutation(
    ({ runId, comment, employeeId }) => payrollApi.review.addComment(runId, comment, employeeId),
    'Comment added',
  );

// ---------------------------------------------------------------------------
// Phase 6 — approval and finalization
// ---------------------------------------------------------------------------
export const useApprovalQueue = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...adminKey, 'approval', params],
    queryFn: () => payrollApi.approval.queue(params),
    placeholderData: (previous) => previous,
  });

export const usePayrollHistory = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...adminKey, 'history', 'runs', params],
    queryFn: () => payrollApi.approval.history(params),
    placeholderData: (previous) => previous,
  });

export const useApprovalSummary = (runId: string) =>
  useQuery({
    queryKey: [...adminKey, 'runs', runId, 'approval-summary'],
    queryFn: () => payrollApi.approval.summary(runId),
    enabled: Boolean(runId),
  });

export const useRunSnapshots = (runId: string, enabled = true) =>
  useQuery({
    queryKey: [...adminKey, 'runs', runId, 'snapshots'],
    queryFn: () => payrollApi.approval.snapshots(runId),
    enabled: Boolean(runId) && enabled,
  });

export const useSubmitForApproval = (): UseMutationResult<PayrollRun, AppError, string> =>
  usePayrollMutation((runId) => payrollApi.approval.submit(runId), 'Submitted for approval');

export const useApprovePayroll = (): UseMutationResult<
  PayrollRun,
  AppError,
  { runId: string; comment: string }
> =>
  usePayrollMutation(
    ({ runId, comment }) => payrollApi.approval.approve(runId, comment),
    'Payroll approved',
  );

export const useReturnPayroll = (): UseMutationResult<
  PayrollRun,
  AppError,
  { runId: string; reason: string }
> =>
  usePayrollMutation(
    ({ runId, reason }) => payrollApi.approval.sendBack(runId, reason),
    'Returned for correction',
  );

// ---------------------------------------------------------------------------
// Phase 7 — payslips
// ---------------------------------------------------------------------------
export const useMyPayslips = (params: PayslipFilters = {}) =>
  useQuery({
    queryKey: [...mineKey, 'payslips', params],
    queryFn: () => payrollApi.payslips.mine(params),
    placeholderData: (previous) => previous,
  });

export const useMyPayslip = (payslipId: string) =>
  useQuery({
    queryKey: [...mineKey, 'payslips', 'detail', payslipId],
    queryFn: () => payrollApi.payslips.mineDetail(payslipId),
    enabled: Boolean(payslipId),
  });

export const usePayslips = (params: PayslipFilters = {}) =>
  useQuery({
    queryKey: [...adminKey, 'payslips', params],
    queryFn: () => payrollApi.payslips.list(params),
    placeholderData: (previous) => previous,
  });

export const usePayslip = (employeeId: string, payslipId: string) =>
  useQuery({
    queryKey: [...adminKey, 'payslips', 'detail', employeeId, payslipId],
    queryFn: () => payrollApi.payslips.detail(employeeId, payslipId),
    enabled: Boolean(employeeId) && Boolean(payslipId),
  });

/** A download is a side effect, not a cache entry: a mutation with toasts. */
export const useDownloadPayslip = (): UseMutationResult<
  string,
  AppError,
  { payslipId: string; employeeId?: string }
> =>
  useMutation<string, AppError, { payslipId: string; employeeId?: string }>({
    mutationFn: ({ payslipId, employeeId }) =>
      employeeId
        ? payrollApi.payslips.download(employeeId, payslipId)
        : payrollApi.payslips.mineDownload(payslipId),
    onSuccess: (filename) => toast.success(`Downloaded ${filename}`),
    onError: (error) => toast.error(error.message),
  });

export const useGeneratePayslips = (): UseMutationResult<PayslipGenerationResult, AppError, string> =>
  usePayrollMutation((runId) => payrollApi.payslips.generate(runId), 'Payslips generated');

export const useRegeneratePayslip = (): UseMutationResult<Payslip, AppError, string> =>
  usePayrollMutation((payslipId) => payrollApi.payslips.regenerate(payslipId), 'Payslip PDF regenerated');

// ---------------------------------------------------------------------------
// Phase 8 — reports and full & final settlement
// ---------------------------------------------------------------------------
export const usePayrollReport = (kind: PayrollReportKind, filters: PayrollReportFilters = {}) =>
  useQuery({
    queryKey: [...adminKey, 'reports', kind, filters],
    queryFn: () => payrollApi.reports.get(kind, filters),
    placeholderData: (previous) => previous,
  });

export const useExportPayrollReport = (): UseMutationResult<
  string,
  AppError,
  { kind: PayrollReportKind; filters: PayrollReportFilters; format: 'csv' | 'xlsx' }
> =>
  useMutation<string, AppError, { kind: PayrollReportKind; filters: PayrollReportFilters; format: 'csv' | 'xlsx' }>({
    mutationFn: ({ kind, filters, format }) => payrollApi.reports.export(kind, filters, format),
    onSuccess: (filename) => toast.success(`Exported ${filename}`),
    onError: (error) => toast.error(error.message),
  });

export const useMySettlement = () =>
  useQuery({
    queryKey: [...mineKey, 'settlement'],
    queryFn: () => payrollApi.settlements.mine(),
    retry: false,
  });

export const useExitingEmployees = () =>
  useQuery({ queryKey: [...adminKey, 'settlements', 'exits'], queryFn: () => payrollApi.settlements.exits() });

export const useSettlement = (settlementId: string) =>
  useQuery({
    queryKey: [...adminKey, 'settlements', 'detail', settlementId],
    queryFn: () => payrollApi.settlements.get(settlementId),
    enabled: Boolean(settlementId),
  });

export const useCreateSettlement = (): UseMutationResult<SettlementDetail, AppError, string> =>
  usePayrollMutation((caseId) => payrollApi.settlements.create(caseId), 'Settlement opened');

export const useCalculateSettlement = (): UseMutationResult<SettlementDetail, AppError, string> =>
  usePayrollMutation((id) => payrollApi.settlements.calculate(id), 'Settlement recalculated');

export const useAddSettlementAdjustment = (): UseMutationResult<
  SettlementDetail,
  AppError,
  { settlementId: string; payload: SettlementAdjustmentInput }
> =>
  usePayrollMutation(
    ({ settlementId, payload }) => payrollApi.settlements.addAdjustment(settlementId, payload),
    'Adjustment proposed',
  );

export const useDecideSettlementAdjustment = (): UseMutationResult<
  SettlementDetail,
  AppError,
  { settlementId: string; adjustmentId: string; approve: boolean; note?: string | null }
> =>
  usePayrollMutation(
    ({ settlementId, adjustmentId, approve, note }) =>
      payrollApi.settlements.decideAdjustment(settlementId, adjustmentId, approve, note),
    'Adjustment decided',
  );

export const useSubmitSettlement = (): UseMutationResult<SettlementDetail, AppError, string> =>
  usePayrollMutation((id) => payrollApi.settlements.submit(id), 'Submitted for review');

export const useCompleteSettlementReview = (): UseMutationResult<SettlementDetail, AppError, string> =>
  usePayrollMutation((id) => payrollApi.settlements.completeReview(id), 'Review completed');

export const useApproveSettlement = (): UseMutationResult<
  SettlementDetail,
  AppError,
  { settlementId: string; comment: string }
> =>
  usePayrollMutation(
    ({ settlementId, comment }) => payrollApi.settlements.approve(settlementId, comment),
    'Settlement approved',
  );

export const useReopenSettlement = (): UseMutationResult<
  SettlementDetail,
  AppError,
  { settlementId: string; reason: string }
> =>
  usePayrollMutation(
    ({ settlementId, reason }) => payrollApi.settlements.reopen(settlementId, reason),
    'Settlement reopened',
  );

export const useFinalizeSettlement = (): UseMutationResult<
  SettlementDetail,
  AppError,
  { settlementId: string; reference?: string | null }
> =>
  usePayrollMutation(
    ({ settlementId, reference }) => payrollApi.settlements.finalize(settlementId, reference),
    'Settlement settled',
  );

export const useFinalizePayroll = (): UseMutationResult<
  PayrollRun,
  AppError,
  { runId: string; comment?: string | null }
> =>
  usePayrollMutation(
    ({ runId, comment }) => payrollApi.approval.finalize(runId, comment),
    'Payroll finalized',
  );
