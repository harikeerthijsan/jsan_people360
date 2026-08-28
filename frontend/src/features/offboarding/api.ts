import { api } from '@/lib/api/client';
import { endpoints } from '@/lib/api/endpoints';
import type { Page } from '@/lib/api/types';

import type {
  AccessClearance,
  AssetClearance,
  ExitDocument,
  ExitDocumentType,
  ExitInterview,
  ExitInterviewInput,
  ExitInterviewListItem,
  HandoverInput,
  HandoverRecord,
  HrProcessInput,
  ManagerDecisionInput,
  MyOffboarding,
  MyResignation,
  OffboardingCase,
  OffboardingSummary,
  OffboardingTask,
  OffboardingTaskStatus,
  ResignationRead,
  ResignationSubmitInput,
  SettlementStatus,
} from './types';

/**
 * Transport for the three separation audiences.
 *
 * Split into `mine`, `team` and `admin` because the server splits them the same
 * way, and the split is the access model rather than a naming convention. No
 * call under `mine` carries an employee id -- there is nowhere to put one --
 * and the ids `team` and `admin` pass are record ids, checked against the
 * caller's scope by the server before anything is read.
 */

const me = endpoints.me.root;
const manager = endpoints.manager.root;
const root = endpoints.offboarding.root;

export const offboardingApi = {
  /** The signed-in employee's own separation. */
  mine: {
    resignation: () => api.get<MyResignation | null>(`${me}/resignation`),
    submit: (payload: ResignationSubmitInput) => api.post<MyResignation>(`${me}/resignation`, payload),
    withdraw: (comments?: string) =>
      api.post<MyResignation>(`${me}/resignation/withdraw`, { comments: comments ?? null }),
    offboarding: () => api.get<MyOffboarding>(`${me}/offboarding`),
    exitInterview: () => api.get<ExitInterview | null>(`${me}/exit-interview`),
    submitExitInterview: (payload: ExitInterviewInput) =>
      api.post<ExitInterview>(`${me}/exit-interview`, payload),
    exitDocuments: () => api.get<ExitDocument[]>(`${me}/exit-documents`),
  },

  /** A manager's direct reports, and nobody else's. */
  team: {
    resignations: (params: Record<string, unknown> = {}) =>
      api.get<Page<ResignationRead>>(`${manager}/resignations`, { params }),
    decide: (resignationId: string, payload: ManagerDecisionInput) =>
      api.post<ResignationRead>(`${manager}/resignations/${resignationId}/decision`, payload),
    cases: (params: Record<string, unknown> = {}) =>
      api.get<Page<OffboardingCase>>(`${manager}/offboarding`, { params }),
    case: (caseId: string) => api.get<OffboardingCase>(`${manager}/offboarding/${caseId}`),
    saveHandover: (caseId: string, payload: HandoverInput) =>
      api.put<HandoverRecord>(`${manager}/offboarding/${caseId}/handover`, payload),
    updateTask: (taskId: string, payload: { status?: OffboardingTaskStatus; comments?: string | null }) =>
      api.patch<OffboardingTask>(`${manager}/offboarding/tasks/${taskId}`, payload),
  },

  /** HR and administrators. Each call is permission-guarded on the server. */
  admin: {
    summary: () => api.get<OffboardingSummary>(`${root}/summary`),
    resignations: (params: Record<string, unknown> = {}) =>
      api.get<Page<ResignationRead>>(`${root}/resignations`, { params }),
    resignation: (id: string) => api.get<ResignationRead>(`${root}/resignations/${id}`),
    process: (id: string, payload: HrProcessInput) =>
      api.post<OffboardingCase>(`${root}/resignations/${id}/process`, payload),
    changeLastWorkingDay: (id: string, approved_last_working_day: string, reason: string) =>
      api.post<ResignationRead>(`${root}/resignations/${id}/last-working-day`, {
        approved_last_working_day,
        reason,
      }),
    cancel: (id: string, reason: string) =>
      api.post<ResignationRead>(`${root}/resignations/${id}/cancel`, { reason }),

    cases: (params: Record<string, unknown> = {}) =>
      api.get<Page<OffboardingCase>>(`${root}/cases`, { params }),
    case: (caseId: string) => api.get<OffboardingCase>(`${root}/cases/${caseId}`),
    updateTask: (
      taskId: string,
      payload: { status?: OffboardingTaskStatus; comments?: string | null; owner_id?: string | null },
    ) => api.patch<OffboardingTask>(`${root}/tasks/${taskId}`, payload),
    updateAsset: (
      assetId: string,
      payload: { status: string; return_date?: string | null; condition?: string | null },
    ) => api.patch<AssetClearance>(`${root}/assets/${assetId}`, payload),
    updateAccess: (itemId: string, payload: { status: string; comments?: string | null }) =>
      api.patch<AccessClearance>(`${root}/access/${itemId}`, payload),
    updateSettlement: (
      caseId: string,
      payload: {
        status: SettlementStatus;
        settlement_reference?: string | null;
        settlement_date?: string | null;
        comments?: string | null;
      },
    ) => api.put<OffboardingCase['settlement']>(`${root}/cases/${caseId}/settlement`, payload),
    generateDocument: (caseId: string, document_type: ExitDocumentType, release: boolean) =>
      api.post<ExitDocument>(`${root}/cases/${caseId}/documents`, { document_type, release }),
    complete: (caseId: string, comments: string | null, force: boolean) =>
      api.post<OffboardingCase>(`${root}/cases/${caseId}/complete`, { comments, force }),

    exitInterviews: (params: Record<string, unknown> = {}) =>
      api.get<Page<ExitInterviewListItem>>(`${root}/exit-interviews`, { params }),
    exitInterview: (caseId: string) =>
      api.get<ExitInterview | null>(`${root}/cases/${caseId}/exit-interview`),
  },
};
