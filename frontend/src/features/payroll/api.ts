import { api, apiClient } from '@/lib/api/client';
import { endpoints } from '@/lib/api/endpoints';
import type { Page } from '@/lib/api/types';

import type {
  ChecklistItem,
  Compensation,
  CompensationAssignInput,
  CompensationListRow,
  ComponentCreateInput,
  ComponentUpdateInput,
  EmployeeCompensationData,
  EmployeeSettingsData,
  EmployeeSettingsUpsertInput,
  EmployeePayrollSettings,
  LeaveRule,
  LeaveRuleCreateInput,
  PayrollAdjustment,
  PayrollAdjustmentCreateInput,
  PayrollApprovalSummary,
  PayrollCalculationResult,
  PayrollChangeDetectionResult,
  PayrollComparisonRow,
  PayrollConfig,
  PayrollConfigHistoryEntry,
  PayrollConfigUpdateInput,
  PayrollInput,
  PayrollInputDetail,
  PayrollInputPrepareResult,
  PayrollPeriod,
  PayrollReconciliation,
  PayrollRecord,
  PayrollRecordDetail,
  PayrollRun,
  PayrollRunException,
  PayrollSnapshot,
  Payslip,
  PayslipDetail,
  PayslipFilters,
  PayslipGenerationResult,
  EligibleExitRow,
  MySettlement,
  PayrollReport,
  PayrollReportFilters,
  PayrollReportKind,
  Settlement,
  SettlementAdjustmentInput,
  SettlementDetail,
  PayrollPeriodInput,
  PayrollPeriodStatus,
  PeriodExceptionRow,
  ReviewComment,
  ReviewReadiness,
  SalaryComponent,
  SalaryHistoryEntry,
  SalaryRevisionInput,
  SalaryStructure,
  StructureCreateInput,
  StructureStatus,
  StructureUpdateInput,
} from './types';

/**
 * Transport for the two payroll audiences.
 *
 * Split into `mine` and `admin` because the server splits them the same way,
 * and the split is the access model: nothing under `mine` carries an employee
 * id — there is nowhere to put one — and every id the admin calls pass is
 * checked against the caller's permissions and scope by the server before
 * anything is read. A manager holding `payroll:team_view` uses the same admin
 * detail call; the server decides whose records answer.
 */

const me = endpoints.me.root;
const root = endpoints.payroll.root;

export const payrollApi = {
  /** The signed-in employee's own compensation. Read-only by construction. */
  mine: {
    compensation: () => api.get<EmployeeCompensationData>(`${me}/payroll`),
    history: () => api.get<SalaryHistoryEntry[]>(`${me}/payroll/history`),
  },

  /** HR and administrators. Each call is permission-guarded on the server. */
  admin: {
    components: (includeInactive = false) =>
      api.get<SalaryComponent[]>(endpoints.payroll.components, {
        params: { include_inactive: includeInactive },
      }),
    createComponent: (payload: ComponentCreateInput) =>
      api.post<SalaryComponent>(endpoints.payroll.components, payload),
    updateComponent: (componentId: string, payload: ComponentUpdateInput) =>
      api.put<SalaryComponent>(`${endpoints.payroll.components}/${componentId}`, payload),
    setComponentStatus: (componentId: string, status: 'active' | 'inactive') =>
      api.post<SalaryComponent>(`${endpoints.payroll.components}/${componentId}/status/${status}`),

    structures: (params: Record<string, unknown> = {}) =>
      api.get<Page<SalaryStructure>>(endpoints.payroll.structures, {
        params: { page: 1, page_size: 50, ...params },
      }),
    structure: (structureId: string) =>
      api.get<SalaryStructure>(`${endpoints.payroll.structures}/${structureId}`),
    createStructure: (payload: StructureCreateInput) =>
      api.post<SalaryStructure>(endpoints.payroll.structures, payload),
    updateStructure: (structureId: string, payload: StructureUpdateInput) =>
      api.put<SalaryStructure>(`${endpoints.payroll.structures}/${structureId}`, payload),
    setStructureStatus: (structureId: string, status: Exclude<StructureStatus, 'draft'>) =>
      api.post<SalaryStructure>(`${endpoints.payroll.structures}/${structureId}/status/${status}`),

    register: (params: Record<string, unknown> = {}) =>
      api.get<Page<CompensationListRow>>(endpoints.payroll.compensation, {
        params: { page: 1, page_size: 20, ...params },
      }),
    employeeCompensation: (employeeId: string) =>
      api.get<EmployeeCompensationData>(`${root}/employees/${employeeId}/compensation`),
    assign: (employeeId: string, payload: CompensationAssignInput) =>
      api.post<Compensation>(`${root}/employees/${employeeId}/compensation`, payload),
    revise: (employeeId: string, payload: SalaryRevisionInput) =>
      api.post<Compensation>(`${root}/employees/${employeeId}/revisions`, payload),
    history: (employeeId: string) =>
      api.get<SalaryHistoryEntry[]>(`${root}/employees/${employeeId}/history`),
  },

  /**
   * The payroll rulebook (Phase 2). Administration by default: none of these
   * paths is reachable by any seeded role below Administrator, and there is
   * deliberately no `mine` counterpart — an employee has no business here.
   */
  config: {
    get: () => api.get<PayrollConfig>(endpoints.payroll.config),
    update: (payload: PayrollConfigUpdateInput) =>
      api.put<PayrollConfig>(endpoints.payroll.config, payload),
    history: () => api.get<PayrollConfigHistoryEntry[]>(endpoints.payroll.configHistory),
  },

  periods: {
    list: (params: Record<string, unknown> = {}) =>
      api.get<Page<PayrollPeriod>>(endpoints.payroll.periods, {
        params: { page: 1, page_size: 50, ...params },
      }),
    create: (payload: PayrollPeriodInput) =>
      api.post<PayrollPeriod>(endpoints.payroll.periods, payload),
    update: (periodId: string, payload: Partial<PayrollPeriodInput>) =>
      api.put<PayrollPeriod>(`${endpoints.payroll.periods}/${periodId}`, payload),
    setStatus: (periodId: string, status: PayrollPeriodStatus) =>
      api.post<PayrollPeriod>(`${endpoints.payroll.periods}/${periodId}/status/${status}`),
  },

  leaveRules: {
    list: (includeInactive = false) =>
      api.get<LeaveRule[]>(endpoints.payroll.leaveRules, {
        params: { include_inactive: includeInactive },
      }),
    create: (payload: LeaveRuleCreateInput) =>
      api.post<LeaveRule>(endpoints.payroll.leaveRules, payload),
    update: (ruleId: string, payload: Partial<Omit<LeaveRuleCreateInput, 'leave_type_id'>>) =>
      api.put<LeaveRule>(`${endpoints.payroll.leaveRules}/${ruleId}`, payload),
    setStatus: (ruleId: string, status: 'active' | 'inactive') =>
      api.post<LeaveRule>(`${endpoints.payroll.leaveRules}/${ruleId}/status/${status}`),
  },

  employeeSettings: {
    list: (params: Record<string, unknown> = {}) =>
      api.get<Page<EmployeePayrollSettings>>(endpoints.payroll.employeeSettings, {
        params: { page: 1, page_size: 20, ...params },
      }),
    forEmployee: (employeeId: string) =>
      api.get<EmployeeSettingsData>(`${root}/employees/${employeeId}/settings`),
    upsert: (employeeId: string, payload: EmployeeSettingsUpsertInput) =>
      api.put<EmployeeSettingsData>(`${root}/employees/${employeeId}/settings`, payload),
  },

  /**
   * Payroll inputs (Phase 3): the prepared attendance/leave/overtime
   * summaries a later calculation phase will consume. Preparation and
   * change detection write only payroll's own snapshot tables — never a
   * source record.
   */
  inputs: {
    mine: () => api.get<PayrollInput[]>(`${me}/payroll/inputs`),
    list: (periodId: string, params: Record<string, unknown> = {}) =>
      api.get<Page<PayrollInput>>(`${root}/periods/${periodId}/inputs`, {
        params: { page: 1, page_size: 50, ...params },
      }),
    detail: (periodId: string, employeeId: string) =>
      api.get<PayrollInputDetail>(`${root}/periods/${periodId}/inputs/${employeeId}`),
    generate: (periodId: string) =>
      api.post<PayrollInputPrepareResult>(`${root}/periods/${periodId}/inputs/generate`),
    detectChanges: (periodId: string) =>
      api.post<PayrollChangeDetectionResult>(`${root}/periods/${periodId}/inputs/detect-changes`),
    exceptions: (periodId: string) =>
      api.get<PeriodExceptionRow[]>(`${root}/periods/${periodId}/exceptions`),
    review: (inputId: string, note: string | null) =>
      api.post<PayrollInput>(`${root}/inputs/${inputId}/review`, { note }),
  },

  /**
   * Payroll runs (Phase 4): the calculation engine. `mine` returns only the
   * caller's own calculated records; everything else is guarded run-by-run
   * on the server.
   */
  runs: {
    mine: () => api.get<PayrollRecordDetail[]>(`${me}/payroll/records`),
    list: (params: Record<string, unknown> = {}) =>
      api.get<Page<PayrollRun>>(endpoints.payroll.runs, {
        params: { page: 1, page_size: 50, ...params },
      }),
    get: (runId: string) => api.get<PayrollRun>(`${endpoints.payroll.runs}/${runId}`),
    create: (periodId: string, notes?: string | null) =>
      api.post<PayrollRun>(endpoints.payroll.runs, {
        payroll_period_id: periodId,
        notes: notes ?? null,
      }),
    calculate: (runId: string) =>
      api.post<PayrollCalculationResult>(`${endpoints.payroll.runs}/${runId}/calculate`),
    recalculate: (runId: string) =>
      api.post<PayrollCalculationResult>(`${endpoints.payroll.runs}/${runId}/recalculate`),
    records: (runId: string, params: Record<string, unknown> = {}) =>
      api.get<Page<PayrollRecord>>(`${endpoints.payroll.runs}/${runId}/records`, {
        params: { page: 1, page_size: 50, ...params },
      }),
    record: (runId: string, employeeId: string) =>
      api.get<PayrollRecordDetail>(`${endpoints.payroll.runs}/${runId}/employees/${employeeId}`),
  },

  /**
   * Payroll review (Phase 5): exceptions, adjustments, checklist,
   * reconciliation and completion. Originals are never edited — every
   * correction here is an additive adjustment, and nothing is deleted.
   */
  review: {
    exceptions: (runId: string, params: Record<string, unknown> = {}) =>
      api.get<PayrollRunException[]>(`${endpoints.payroll.runs}/${runId}/exceptions`, { params }),
    resolveException: (runId: string, exceptionId: string, resolution: string, notes?: string | null) =>
      api.post<PayrollRunException>(
        `${endpoints.payroll.runs}/${runId}/exceptions/${exceptionId}/resolve`,
        { resolution, notes: notes ?? null },
      ),
    adjustments: (runId: string) =>
      api.get<PayrollAdjustment[]>(`${endpoints.payroll.runs}/${runId}/adjustments`),
    createAdjustment: (runId: string, employeeId: string, payload: PayrollAdjustmentCreateInput) =>
      api.post<PayrollAdjustment>(
        `${endpoints.payroll.runs}/${runId}/employees/${employeeId}/adjustments`,
        payload,
      ),
    cancelAdjustment: (runId: string, adjustmentId: string, reason: string) =>
      api.post<PayrollAdjustment>(
        `${endpoints.payroll.runs}/${runId}/adjustments/${adjustmentId}/cancel`,
        { reason },
      ),
    markRecord: (runId: string, employeeId: string, recordStatus: 'reviewed' | 'adjustment_required', note?: string | null) =>
      api.post<null>(`${endpoints.payroll.runs}/${runId}/employees/${employeeId}/review-mark`, {
        status: recordStatus,
        note: note ?? null,
      }),
    checklist: (runId: string) =>
      api.get<ChecklistItem[]>(`${endpoints.payroll.runs}/${runId}/checklist`),
    updateChecklist: (runId: string, itemKey: string, completed: boolean) =>
      api.patch<ChecklistItem[]>(`${endpoints.payroll.runs}/${runId}/checklist/${itemKey}`, {
        completed,
      }),
    readiness: (runId: string) =>
      api.get<ReviewReadiness>(`${endpoints.payroll.runs}/${runId}/review-readiness`),
    complete: (runId: string) =>
      api.post<ReviewReadiness>(`${endpoints.payroll.runs}/${runId}/complete-review`),
    comments: (runId: string, employeeId?: string) =>
      api.get<ReviewComment[]>(`${endpoints.payroll.runs}/${runId}/comments`, {
        params: employeeId ? { employee_id: employeeId } : {},
      }),
    addComment: (runId: string, comment: string, employeeId?: string | null) =>
      api.post<ReviewComment>(`${endpoints.payroll.runs}/${runId}/comments`, {
        comment,
        employee_id: employeeId ?? null,
      }),
    reconciliation: (runId: string) =>
      api.get<PayrollReconciliation>(`${endpoints.payroll.runs}/${runId}/reconciliation`),
    comparison: (runId: string) =>
      api.get<PayrollComparisonRow[]>(`${endpoints.payroll.runs}/${runId}/comparison`),
  },

  /**
   * Payroll approval and finalization (Phase 6). There is no "set status"
   * call: submit, approve, return and finalize are the only doors between
   * states, and the server re-validates state and gates on every one.
   */
  approval: {
    queue: (params: Record<string, unknown> = {}) =>
      api.get<Page<PayrollRun>>(`${root}/approval`, {
        params: { page: 1, page_size: 50, ...params },
      }),
    history: (params: Record<string, unknown> = {}) =>
      api.get<Page<PayrollRun>>(`${root}/history`, {
        params: { page: 1, page_size: 50, ...params },
      }),
    summary: (runId: string) =>
      api.get<PayrollApprovalSummary>(`${endpoints.payroll.runs}/${runId}/approval-summary`),
    submit: (runId: string) =>
      api.post<PayrollRun>(`${endpoints.payroll.runs}/${runId}/submit-approval`),
    approve: (runId: string, comment: string) =>
      api.post<PayrollRun>(`${endpoints.payroll.runs}/${runId}/approve`, { comment }),
    sendBack: (runId: string, reason: string) =>
      api.post<PayrollRun>(`${endpoints.payroll.runs}/${runId}/return`, { reason }),
    finalize: (runId: string, comment?: string | null) =>
      api.post<PayrollRun>(`${endpoints.payroll.runs}/${runId}/finalize`, {
        comment: comment ?? null,
      }),
    snapshots: (runId: string) =>
      api.get<PayrollSnapshot[]>(`${endpoints.payroll.runs}/${runId}/snapshots`),
  },

  /**
   * Payslips (Phase 7). `mine` takes no employee id — the session decides
   * whose payslips answer. The administrator paths carry the employee id so
   * the server's scope guards apply, and a payslip that does not belong to
   * that employee is a 404, never a leak.
   */
  payslips: {
    mine: (params: PayslipFilters = {}) =>
      api.get<Page<Payslip>>(`${me}/payroll/payslips`, {
        params: { page: 1, page_size: 12, ...params },
      }),
    mineDetail: (payslipId: string) =>
      api.get<PayslipDetail>(`${me}/payroll/payslips/${payslipId}`),
    mineDownload: (payslipId: string) =>
      downloadPdf(`${me}/payroll/payslips/${payslipId}/download`),
    list: (params: PayslipFilters = {}) =>
      api.get<Page<Payslip>>(`${root}/payslips`, { params: { page: 1, page_size: 20, ...params } }),
    detail: (employeeId: string, payslipId: string) =>
      api.get<PayslipDetail>(`${root}/employees/${employeeId}/payslips/${payslipId}`),
    download: (employeeId: string, payslipId: string) =>
      downloadPdf(`${root}/employees/${employeeId}/payslips/${payslipId}/download`),
    generate: (runId: string) =>
      api.post<PayslipGenerationResult>(`${endpoints.payroll.runs}/${runId}/payslips/generate`),
    regenerate: (payslipId: string) =>
      api.post<Payslip>(`${root}/payslips/${payslipId}/regenerate`),
  },

  /** Payroll reports (Phase 8): finalized payroll, organization-wide. */
  reports: {
    get: (kind: PayrollReportKind, filters: PayrollReportFilters = {}) =>
      api.get<PayrollReport>(`${root}/reports/${kind}`, { params: filters }),
    export: async (
      kind: PayrollReportKind,
      filters: PayrollReportFilters = {},
      format: 'csv' | 'xlsx' = 'csv',
    ): Promise<string> => {
      const response = await apiClient.get<Blob>(`${root}/reports/${kind}/export`, {
        params: { ...filters, format },
        responseType: 'blob',
      });
      return saveBlob(response.data, String(response.headers['content-disposition'] ?? ''), `payroll-${kind}.${format}`);
    },
  },

  /** Full & final settlement (Phase 8). `mine` takes no id. */
  settlements: {
    mine: () => api.get<MySettlement>(`${me}/payroll/settlement`),
    exits: () => api.get<EligibleExitRow[]>(`${root}/final-settlement`),
    list: (params: Record<string, unknown> = {}) =>
      api.get<Page<Settlement>>(`${root}/final-settlement/settlements`, {
        params: { page: 1, page_size: 50, ...params },
      }),
    create: (caseId: string) => api.post<SettlementDetail>(`${root}/final-settlement/cases/${caseId}`),
    get: (settlementId: string) => api.get<SettlementDetail>(`${root}/final-settlement/${settlementId}`),
    update: (settlementId: string, payload: { notes?: string | null; exit_type?: string; exit_reason?: string | null }) =>
      api.patch<SettlementDetail>(`${root}/final-settlement/${settlementId}`, payload),
    calculate: (settlementId: string) =>
      api.post<SettlementDetail>(`${root}/final-settlement/${settlementId}/calculate`),
    addAdjustment: (settlementId: string, payload: SettlementAdjustmentInput) =>
      api.post<SettlementDetail>(`${root}/final-settlement/${settlementId}/adjustments`, payload),
    decideAdjustment: (settlementId: string, adjustmentId: string, approve: boolean, note?: string | null) =>
      api.post<SettlementDetail>(
        `${root}/final-settlement/${settlementId}/adjustments/${adjustmentId}/decide`,
        { approve, note: note ?? null },
      ),
    submit: (settlementId: string) =>
      api.post<SettlementDetail>(`${root}/final-settlement/${settlementId}/submit`),
    completeReview: (settlementId: string) =>
      api.post<SettlementDetail>(`${root}/final-settlement/${settlementId}/complete-review`),
    approve: (settlementId: string, comment: string) =>
      api.post<SettlementDetail>(`${root}/final-settlement/${settlementId}/approve`, { comment }),
    reopen: (settlementId: string, reason: string) =>
      api.post<SettlementDetail>(`${root}/final-settlement/${settlementId}/reopen`, { reason }),
    finalize: (settlementId: string, reference?: string | null) =>
      api.post<SettlementDetail>(`${root}/final-settlement/${settlementId}/finalize`, {
        settlement_reference: reference ?? null,
      }),
  },
};

function saveBlob(blob: Blob, disposition: string, fallback: string): string {
  const match = /filename="?([^";]+)"?/.exec(disposition);
  const filename = match?.[1] ?? fallback;
  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
  return filename;
}

/**
 * Fetch a PDF through the authenticated client and hand it to the browser
 * as a download. The filename comes from the server's Content-Disposition —
 * the payslip number — so the saved file is traceable by name.
 */
async function downloadPdf(url: string): Promise<string> {
  const response = await apiClient.get<Blob>(url, { responseType: 'blob' });
  const disposition = String(response.headers['content-disposition'] ?? '');
  const match = /filename="?([^";]+)"?/.exec(disposition);
  const filename = match?.[1] ?? 'payslip.pdf';
  const objectUrl = URL.createObjectURL(response.data);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(objectUrl);
  return filename;
}
