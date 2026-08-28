'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult } from '@tanstack/react-query';

import { toast } from '@/components/ui/sonner';
import type { AppError } from '@/lib/errors';

import { managerApi } from './api';
import type { ApprovalDecision } from './types';

/**
 * Data hooks for the manager screens.
 *
 * Every mutation invalidates the whole `manager` key, for the reason the
 * workforce module gives about its own: the figures interlock. Approving one
 * leave request changes the leave list, the dashboard's queue count, the team
 * roster's "on leave today" column and the calendar at once, and invalidating
 * selectively would leave one of them stale until two numbers on the same
 * screen disagreed.
 *
 * The key is separate from `me` and from `workforce`, so the employee portal
 * and the HR screens do not evict this cache on every action, or it theirs.
 */

const root = ['manager'] as const;

export const useManagerDashboard = () =>
  useQuery({
    queryKey: [...root, 'dashboard'],
    queryFn: () => managerApi.dashboard(),
    // Carries today's attendance and four live queues; a stale one shows work
    // that has already been done. Cheap to refetch, misleading to be wrong.
    staleTime: 30_000,
  });

export const useTeam = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'team', params],
    queryFn: () => managerApi.team({ page: 1, page_size: 50, ...params }),
  });

export const useTeamMember = (employeeId: string) =>
  useQuery({
    queryKey: [...root, 'member', employeeId],
    queryFn: () => managerApi.member(employeeId),
    enabled: Boolean(employeeId),
  });

export const useTeamAttendance = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'attendance', params],
    queryFn: () => managerApi.attendance({ page: 1, page_size: 50, ...params }),
  });

export const useTeamRegularizations = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'regularizations', params],
    queryFn: () => managerApi.regularizations({ page: 1, page_size: 50, ...params }),
  });

export const useTeamLeave = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'leave', params],
    queryFn: () => managerApi.leave({ page: 1, page_size: 50, ...params }),
  });

export const useTeamTimesheets = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'timesheets', params],
    queryFn: () => managerApi.timesheets({ page: 1, page_size: 50, ...params }),
  });

export const useTeamProjects = () =>
  useQuery({ queryKey: [...root, 'projects'], queryFn: () => managerApi.projects() });

export const useTeamPerformance = (cycleId?: string) =>
  useQuery({
    queryKey: [...root, 'performance', cycleId ?? 'current'],
    queryFn: () => managerApi.performance(cycleId),
  });

export const useTeamCalendar = (year: number, month: number) =>
  useQuery({
    queryKey: [...root, 'calendar', year, month],
    queryFn: () => managerApi.calendar(year, month),
  });

export const useTeamDocumentStatus = () =>
  useQuery({ queryKey: [...root, 'documents'], queryFn: () => managerApi.documentStatus() });

// ---------------------------------------------------------------------------
// Decisions
// ---------------------------------------------------------------------------
export interface DecisionVariables {
  id: string;
  decision: ApprovalDecision;
}

function useDecision<TResult>(
  mutationFn: (variables: DecisionVariables) => Promise<TResult>,
  labels: { done: string; failed: string },
): UseMutationResult<TResult, AppError, DecisionVariables> {
  const queryClient = useQueryClient();

  return useMutation<TResult, AppError, DecisionVariables>({
    mutationFn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: root });
      toast.success(labels.done);
    },
    onError: (error) => {
      // The server's message verbatim. It names the rule that was broken --
      // outside your team, your own request, already decided -- and a generic
      // failure would hide the part that says what happened.
      toast.error(labels.failed, { description: error.message });
    },
  });
}

export const useDecideLeave = () =>
  useDecision(({ id, decision }) => managerApi.decideLeave(id, decision), {
    done: 'Decision recorded',
    failed: 'Could not record this decision',
  });

export const useDecideTimesheet = () =>
  useDecision(({ id, decision }) => managerApi.decideTimesheet(id, decision), {
    done: 'Decision recorded',
    failed: 'Could not record this decision',
  });

export const useDecideRegularization = () =>
  useDecision(({ id, decision }) => managerApi.decideRegularization(id, decision), {
    done: 'Decision recorded',
    failed: 'Could not record this decision',
  });
