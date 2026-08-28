'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult } from '@tanstack/react-query';

import { toast } from '@/components/ui/sonner';
import type { AppError } from '@/lib/errors';

import { offboardingApi } from './api';
import type {
  ExitInterviewInput,
  HandoverInput,
  HrProcessInput,
  ManagerDecisionInput,
  MyResignation,
  OffboardingTaskStatus,
  ResignationSubmitInput,
  SettlementStatus,
} from './types';

/**
 * Data hooks for the separation screens.
 *
 * Three query roots rather than one, matching the three audiences: an
 * employee's own screens must not be evicted every time HR ticks a checklist
 * row on somebody else's case, and an HR list must not be evicted by an
 * employee saving their exit interview.
 *
 * Within a root, mutations invalidate the whole root. The figures interlock --
 * approving a resignation changes the list, the summary counters and the case
 * that opens behind it at once -- and invalidating selectively is how two
 * numbers on the same screen end up disagreeing.
 */

const mineKey = ['me', 'offboarding'] as const;
const teamKey = ['manager', 'offboarding'] as const;
const adminKey = ['offboarding'] as const;

// ---------------------------------------------------------------------------
// Employee
// ---------------------------------------------------------------------------
export const useMyResignation = () =>
  useQuery({
    queryKey: [...mineKey, 'resignation'],
    queryFn: () => offboardingApi.mine.resignation(),
  });

export const useMyOffboarding = () =>
  useQuery({
    queryKey: [...mineKey, 'case'],
    queryFn: () => offboardingApi.mine.offboarding(),
  });

export const useMyExitInterview = () =>
  useQuery({
    queryKey: [...mineKey, 'exit-interview'],
    queryFn: () => offboardingApi.mine.exitInterview(),
  });

export const useMyExitDocuments = () =>
  useQuery({
    queryKey: [...mineKey, 'exit-documents'],
    queryFn: () => offboardingApi.mine.exitDocuments(),
  });

const useMineMutation = <TInput, TResult>(
  fn: (input: TInput) => Promise<TResult>,
  message: string,
): UseMutationResult<TResult, AppError, TInput> => {
  const queryClient = useQueryClient();
  return useMutation<TResult, AppError, TInput>({
    mutationFn: fn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: mineKey });
      toast.success(message);
    },
    onError: (error) => toast.error(error.message),
  });
};

export const useSubmitResignation = (): UseMutationResult<MyResignation, AppError, ResignationSubmitInput> =>
  useMineMutation((input) => offboardingApi.mine.submit(input), 'Resignation submitted');

export const useWithdrawResignation = () =>
  useMineMutation(
    (comments: string | undefined) => offboardingApi.mine.withdraw(comments),
    'Resignation withdrawn',
  );

export const useSubmitExitInterview = () =>
  useMineMutation(
    (input: ExitInterviewInput) => offboardingApi.mine.submitExitInterview(input),
    'Exit interview submitted. Thank you.',
  );

// ---------------------------------------------------------------------------
// Manager
// ---------------------------------------------------------------------------
export const useTeamResignations = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...teamKey, 'resignations', params],
    queryFn: () => offboardingApi.team.resignations({ page: 1, page_size: 50, ...params }),
  });

export const useTeamOffboardingCases = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...teamKey, 'cases', params],
    queryFn: () => offboardingApi.team.cases({ page: 1, page_size: 50, ...params }),
  });

export const useTeamOffboardingCase = (caseId: string) =>
  useQuery({
    queryKey: [...teamKey, 'case', caseId],
    queryFn: () => offboardingApi.team.case(caseId),
    enabled: Boolean(caseId),
  });

const useTeamMutation = <TInput, TResult>(
  fn: (input: TInput) => Promise<TResult>,
  message: string,
): UseMutationResult<TResult, AppError, TInput> => {
  const queryClient = useQueryClient();
  return useMutation<TResult, AppError, TInput>({
    mutationFn: fn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: teamKey });
      toast.success(message);
    },
    onError: (error) => toast.error(error.message),
  });
};

export const useDecideResignation = () =>
  useTeamMutation(
    ({ id, payload }: { id: string; payload: ManagerDecisionInput }) =>
      offboardingApi.team.decide(id, payload),
    'Decision recorded',
  );

export const useSaveHandover = () =>
  useTeamMutation(
    ({ caseId, payload }: { caseId: string; payload: HandoverInput }) =>
      offboardingApi.team.saveHandover(caseId, payload),
    'Handover saved',
  );

export const useCompleteTeamTask = () =>
  useTeamMutation(
    ({ taskId, status }: { taskId: string; status: OffboardingTaskStatus }) =>
      offboardingApi.team.updateTask(taskId, { status }),
    'Task updated',
  );

// ---------------------------------------------------------------------------
// HR and admin
// ---------------------------------------------------------------------------
export const useOffboardingSummary = () =>
  useQuery({
    queryKey: [...adminKey, 'summary'],
    queryFn: () => offboardingApi.admin.summary(),
    staleTime: 30_000,
  });

export const useResignations = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...adminKey, 'resignations', params],
    queryFn: () => offboardingApi.admin.resignations({ page: 1, page_size: 20, ...params }),
  });

export const useOffboardingCases = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...adminKey, 'cases', params],
    queryFn: () => offboardingApi.admin.cases({ page: 1, page_size: 20, ...params }),
  });

export const useOffboardingCase = (caseId: string) =>
  useQuery({
    queryKey: [...adminKey, 'case', caseId],
    queryFn: () => offboardingApi.admin.case(caseId),
    enabled: Boolean(caseId),
  });

export const useExitInterviews = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...adminKey, 'exit-interviews', params],
    queryFn: () => offboardingApi.admin.exitInterviews({ page: 1, page_size: 20, ...params }),
  });

const useAdminMutation = <TInput, TResult>(
  fn: (input: TInput) => Promise<TResult>,
  message: string,
): UseMutationResult<TResult, AppError, TInput> => {
  const queryClient = useQueryClient();
  return useMutation<TResult, AppError, TInput>({
    mutationFn: fn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: adminKey });
      toast.success(message);
    },
    onError: (error) => toast.error(error.message),
  });
};

export const useProcessResignation = () =>
  useAdminMutation(
    ({ id, payload }: { id: string; payload: HrProcessInput }) => offboardingApi.admin.process(id, payload),
    'Offboarding started',
  );

export const useChangeLastWorkingDay = () =>
  useAdminMutation(
    ({ id, date, reason }: { id: string; date: string; reason: string }) =>
      offboardingApi.admin.changeLastWorkingDay(id, date, reason),
    'Last working day updated',
  );

export const useCancelSeparation = () =>
  useAdminMutation(
    ({ id, reason }: { id: string; reason: string }) => offboardingApi.admin.cancel(id, reason),
    'Separation cancelled',
  );

export const useUpdateCaseTask = () =>
  useAdminMutation(
    ({
      taskId,
      status,
      comments,
    }: {
      taskId: string;
      status?: OffboardingTaskStatus;
      comments?: string | null;
    }) => offboardingApi.admin.updateTask(taskId, { status, comments }),
    'Task updated',
  );

export const useUpdateAsset = () =>
  useAdminMutation(
    ({ assetId, status }: { assetId: string; status: string }) =>
      offboardingApi.admin.updateAsset(assetId, { status }),
    'Asset clearance updated',
  );

export const useUpdateAccess = () =>
  useAdminMutation(
    ({ itemId, status }: { itemId: string; status: string }) =>
      offboardingApi.admin.updateAccess(itemId, { status }),
    'Access clearance updated',
  );

export const useUpdateSettlement = () =>
  useAdminMutation(
    ({
      caseId,
      status,
      reference,
    }: {
      caseId: string;
      status: SettlementStatus;
      reference?: string | null;
    }) =>
      offboardingApi.admin.updateSettlement(caseId, {
        status,
        settlement_reference: reference ?? null,
      }),
    'Settlement status updated',
  );

export const useGenerateExitDocument = () =>
  useAdminMutation(
    ({
      caseId,
      documentType,
      release,
    }: {
      caseId: string;
      documentType: Parameters<typeof offboardingApi.admin.generateDocument>[1];
      release: boolean;
    }) => offboardingApi.admin.generateDocument(caseId, documentType, release),
    'Exit document generated',
  );

export const useCompleteOffboarding = () =>
  useAdminMutation(
    ({ caseId, comments, force }: { caseId: string; comments: string | null; force: boolean }) =>
      offboardingApi.admin.complete(caseId, comments, force),
    'Offboarding completed',
  );
