'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult } from '@tanstack/react-query';

import { toast } from '@/components/ui/sonner';
import type { AppError } from '@/lib/errors';

import { workforceApi } from './api';

/**
 * Data hooks for the workforce screens.
 *
 * Every mutation invalidates the whole `workforce` key. The module's figures
 * are interlocking -- approving leave changes a balance, the day's attendance,
 * the calendar and the dashboard at once -- so invalidating selectively would
 * leave one of them stale, and nobody would notice until two numbers on the
 * same screen disagreed.
 */

const root = ['workforce'] as const;

export const useWorkforceDashboard = (on?: string) =>
  useQuery({
    queryKey: [...root, 'dashboard', on ?? 'today'],
    queryFn: () => workforceApi.dashboard(on),
  });

export const useTimesheetDashboard = (weekStart?: string) =>
  useQuery({
    queryKey: [...root, 'timesheet-dashboard', weekStart ?? 'current'],
    queryFn: () => workforceApi.timesheetDashboard(weekStart),
  });

export const useWorkforceCalendar = (employeeId: string | undefined, year: number, month: number) =>
  useQuery({
    queryKey: [...root, 'calendar', employeeId ?? '', year, month],
    queryFn: () => workforceApi.calendar(employeeId ?? '', year, month),
    enabled: Boolean(employeeId),
  });

export const useShifts = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'shifts', params],
    queryFn: () => workforceApi.shifts({ page: 1, page_size: 100, ...params }),
  });

export const useShiftHistory = (employeeId: string | undefined) =>
  useQuery({
    queryKey: [...root, 'shift-history', employeeId ?? ''],
    queryFn: () => workforceApi.shiftHistory(employeeId ?? ''),
    enabled: Boolean(employeeId),
  });

export const useAttendance = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'attendance', params],
    queryFn: () => workforceApi.attendance({ page: 1, page_size: 50, ...params }),
  });

export const useRegularizations = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'regularizations', params],
    queryFn: () => workforceApi.regularizations({ page: 1, page_size: 50, ...params }),
  });

export const useLeaveTypes = () =>
  useQuery({ queryKey: [...root, 'leave-types'], queryFn: () => workforceApi.leaveTypes() });

export const useLeaveBalances = (employeeId: string | undefined, year?: number) =>
  useQuery({
    queryKey: [...root, 'leave-balances', employeeId ?? '', year ?? 'current'],
    queryFn: () => workforceApi.leaveBalances(employeeId ?? '', year),
    enabled: Boolean(employeeId),
  });

export const useLeaveRequests = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'leave', params],
    queryFn: () => workforceApi.leaveRequests({ page: 1, page_size: 50, ...params }),
  });

export const useHolidayCalendars = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'holidays', params],
    queryFn: () => workforceApi.holidayCalendars(params),
  });

export const useTimesheets = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'timesheets', params],
    queryFn: () => workforceApi.timesheets({ page: 1, page_size: 50, ...params }),
  });

export const useTimesheet = (id: string | undefined) =>
  useQuery({
    queryKey: [...root, 'timesheet', id ?? ''],
    queryFn: () => workforceApi.timesheet(id ?? ''),
    enabled: Boolean(id),
  });

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------
function useWorkforceMutation<TVariables, TResult>(
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
      // how many days are left, which week is locked -- and a generic failure
      // would hide the part that tells the user what to do next.
      toast.error(labels.failed, { description: error.message });
    },
  });
}

export const useCreateShift = () =>
  useWorkforceMutation((data: unknown) => workforceApi.createShift(data), {
    done: 'Shift created',
    failed: 'Could not create this shift',
  });

export const useUpdateShift = (id: string) =>
  useWorkforceMutation((data: unknown) => workforceApi.updateShift(id, data), {
    done: 'Shift updated',
    failed: 'Could not update this shift',
  });

export const useAssignShift = () =>
  useWorkforceMutation((data: unknown) => workforceApi.assignShift(data), {
    done: 'Shift assigned',
    failed: 'Could not assign this shift',
  });

export const useCheckIn = (employeeId: string) =>
  useWorkforceMutation((data: unknown) => workforceApi.checkIn(employeeId, data), {
    done: 'Checked in',
    failed: 'Could not check in',
  });

export const useCheckOut = (employeeId: string) =>
  useWorkforceMutation((data: unknown) => workforceApi.checkOut(employeeId, data), {
    done: 'Checked out',
    failed: 'Could not check out',
  });

export const useRequestRegularization = (employeeId: string) =>
  useWorkforceMutation((data: unknown) => workforceApi.requestRegularization(employeeId, data), {
    done: 'Correction requested',
    failed: 'Could not request this correction',
  });

export const useDecideRegularization = () =>
  useWorkforceMutation(
    ({ id, ...data }: { id: string; approved: boolean; notes: string | null }) =>
      workforceApi.decideRegularization(id, data),
    { done: 'Decision recorded', failed: 'Could not record this decision' },
  );

export const useCreateLeaveType = () =>
  useWorkforceMutation((data: unknown) => workforceApi.createLeaveType(data), {
    done: 'Leave type created',
    failed: 'Could not create this leave type',
  });

export const useUpdateLeaveType = (id: string) =>
  useWorkforceMutation((data: unknown) => workforceApi.updateLeaveType(id, data), {
    done: 'Leave type updated',
    failed: 'Could not update this leave type',
  });

export const useApplyForLeave = (employeeId: string) =>
  useWorkforceMutation((data: unknown) => workforceApi.applyForLeave(employeeId, data), {
    done: 'Leave applied',
    failed: 'Could not apply for this leave',
  });

export const useDecideLeave = () =>
  useWorkforceMutation(
    ({ id, ...data }: { id: string; approved: boolean; notes: string | null }) =>
      workforceApi.decideLeave(id, data),
    { done: 'Decision recorded', failed: 'Could not record this decision' },
  );

export const useCancelLeave = () =>
  useWorkforceMutation((id: string) => workforceApi.cancelLeave(id), {
    done: 'Leave cancelled',
    failed: 'Could not cancel this leave',
  });

export const useCreateHolidayCalendar = () =>
  useWorkforceMutation((data: unknown) => workforceApi.createHolidayCalendar(data), {
    done: 'Holiday calendar created',
    failed: 'Could not create this calendar',
  });

export const useSaveTimesheet = (employeeId: string) =>
  useWorkforceMutation((data: unknown) => workforceApi.saveTimesheet(employeeId, data), {
    done: 'Timesheet saved',
    failed: 'Could not save this timesheet',
  });

export const useSubmitTimesheet = () =>
  useWorkforceMutation((id: string) => workforceApi.submitTimesheet(id), {
    done: 'Timesheet submitted',
    failed: 'Could not submit this timesheet',
  });

export const useDecideTimesheet = () =>
  useWorkforceMutation(
    ({ id, ...data }: { id: string; approved: boolean; notes: string | null }) =>
      workforceApi.decideTimesheet(id, data),
    { done: 'Decision recorded', failed: 'Could not record this decision' },
  );
