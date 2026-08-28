'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult } from '@tanstack/react-query';

import { toast } from '@/components/ui/sonner';
import type { AppError } from '@/lib/errors';

import { performanceApi } from './api';
import type { PerformanceCycleStatus } from './types';

/**
 * Data hooks for the performance screens.
 *
 * Every mutation invalidates the whole `performance` key. The module's figures
 * are interlocking -- assigning a goal changes the dashboard, the analytics and
 * the employee's review page -- so invalidating selectively would leave one of
 * them stale and nobody would notice until a number disagreed with itself.
 */

const root = ['performance'] as const;

export const usePerformanceDashboard = (cycleId?: string) =>
  useQuery({
    queryKey: [...root, 'dashboard', cycleId ?? 'active'],
    queryFn: () => performanceApi.dashboard(cycleId),
  });

export const usePerformanceAnalytics = (cycleId?: string) =>
  useQuery({
    queryKey: [...root, 'analytics', cycleId ?? 'all'],
    queryFn: () => performanceApi.analytics(cycleId),
  });

export const useCycles = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'cycles', params],
    queryFn: () => performanceApi.cycles({ page: 1, page_size: 100, ...params }),
  });

export const useCycle = (id: string | undefined) =>
  useQuery({
    queryKey: [...root, 'cycle', id ?? ''],
    queryFn: () => performanceApi.cycle(id ?? ''),
    enabled: Boolean(id),
  });

export const useGoals = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'goals', params],
    queryFn: () => performanceApi.goals({ page: 1, page_size: 100, ...params }),
  });

export const useGoal = (id: string | undefined) =>
  useQuery({
    queryKey: [...root, 'goal', id ?? ''],
    queryFn: () => performanceApi.goal(id ?? ''),
    enabled: Boolean(id),
  });

export const useEmployeePerformance = (cycleId: string | undefined, employeeId: string | undefined) =>
  useQuery({
    queryKey: [...root, 'review', cycleId ?? '', employeeId ?? ''],
    queryFn: () => performanceApi.employeePerformance(cycleId ?? '', employeeId ?? ''),
    enabled: Boolean(cycleId && employeeId),
  });

export const useRecognitions = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'recognitions', params],
    queryFn: () => performanceApi.recognitions({ page: 1, page_size: 100, ...params }),
  });

export const useFeedback = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'feedback', params],
    queryFn: () => performanceApi.feedback({ page: 1, page_size: 100, ...params }),
  });

export const usePerformanceHistory = (employeeId: string | undefined) =>
  useQuery({
    queryKey: [...root, 'history', employeeId ?? ''],
    queryFn: () => performanceApi.history(employeeId ?? ''),
    enabled: Boolean(employeeId),
  });

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------
function usePerformanceMutation<TVariables, TResult>(
  mutationFn: (variables: TVariables) => Promise<TResult>,
  labels: { done: string; failed: string },
): UseMutationResult<TResult, AppError, TVariables> {
  const queryClient = useQueryClient();

  return useMutation<TResult, AppError, TVariables>({
    mutationFn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: root });
      toast.success(labels.done);
    },
    onError: (error) => {
      // The server's message verbatim: it names the rule that was broken --
      // how much weightage is left, which stage is missing -- and a generic
      // failure would hide the part that tells the user what to do.
      toast.error(labels.failed, { description: error.message });
    },
  });
}

export const useCreateCycle = () =>
  usePerformanceMutation((data: unknown) => performanceApi.createCycle(data), {
    done: 'Performance cycle created',
    failed: 'Could not create this cycle',
  });

export const useUpdateCycle = (id: string) =>
  usePerformanceMutation((data: unknown) => performanceApi.updateCycle(id, data), {
    done: 'Performance cycle updated',
    failed: 'Could not update this cycle',
  });

export const useSetCycleStatus = (id: string) =>
  usePerformanceMutation((status: PerformanceCycleStatus) => performanceApi.setCycleStatus(id, status), {
    done: 'Cycle status changed',
    failed: 'Could not change the cycle status',
  });

export const useAssignGoal = () =>
  usePerformanceMutation((data: unknown) => performanceApi.assignGoal(data), {
    done: 'Goal assigned',
    failed: 'Could not assign this goal',
  });

export const useUpdateGoal = (id: string) =>
  usePerformanceMutation((data: unknown) => performanceApi.updateGoal(id, data), {
    done: 'Goal updated',
    failed: 'Could not update this goal',
  });

export const useRecordProgress = (id: string) =>
  usePerformanceMutation((data: unknown) => performanceApi.recordProgress(id, data), {
    done: 'Progress recorded',
    failed: 'Could not record progress',
  });

export const useSubmitSelfReview = (cycleId: string, employeeId: string) =>
  usePerformanceMutation((data: unknown) => performanceApi.submitSelfReview(cycleId, employeeId, data), {
    done: 'Self review submitted',
    failed: 'Could not submit this review',
  });

export const useSubmitManagerReview = (cycleId: string, employeeId: string) =>
  usePerformanceMutation((data: unknown) => performanceApi.submitManagerReview(cycleId, employeeId, data), {
    done: 'Manager review submitted',
    failed: 'Could not submit this review',
  });

export const useFinalise = (cycleId: string, employeeId: string) =>
  usePerformanceMutation((data: unknown) => performanceApi.finalise(cycleId, employeeId, data), {
    done: 'Performance finalised',
    failed: 'Could not finalise this review',
  });

export const useAddRecognition = () =>
  usePerformanceMutation((data: unknown) => performanceApi.addRecognition(data), {
    done: 'Recognition recorded',
    failed: 'Could not record this recognition',
  });

export const useAddFeedback = () =>
  usePerformanceMutation((data: unknown) => performanceApi.addFeedback(data), {
    done: 'Feedback recorded',
    failed: 'Could not record this feedback',
  });
