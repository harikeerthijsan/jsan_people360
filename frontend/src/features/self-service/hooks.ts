'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult } from '@tanstack/react-query';

import { toast } from '@/components/ui/sonner';
import type { AppError } from '@/lib/errors';

import { selfServiceApi } from './api';

/**
 * Data hooks for the employee portal.
 *
 * Every mutation invalidates the whole `me` key, for the reason the workforce
 * module gives about its own: the figures interlock. Checking out changes
 * today's card, the month summary, the calendar and the dashboard's outstanding
 * list at once, and invalidating selectively would leave one of them stale until
 * two numbers on the same screen disagreed.
 *
 * The `me` key is also separate from `workforce`, so an HR screen and the portal
 * do not evict each other's caches on every action.
 */

const root = ['me'] as const;

export const useMyProfile = () =>
  useQuery({ queryKey: [...root, 'profile'], queryFn: () => selfServiceApi.profile() });

export const useMyDashboard = () =>
  useQuery({
    queryKey: [...root, 'dashboard'],
    queryFn: () => selfServiceApi.dashboard(),
    // The dashboard carries a live check-in state; a stale one shows the wrong
    // button. Cheap to refetch, expensive to be wrong about.
    staleTime: 30_000,
  });

export const useMyAttendanceToday = () =>
  useQuery({
    queryKey: [...root, 'attendance', 'today'],
    queryFn: () => selfServiceApi.today(),
    staleTime: 30_000,
  });

export const useMyAttendance = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'attendance', params],
    queryFn: () => selfServiceApi.attendance({ page: 1, page_size: 50, ...params }),
  });

export const useMyAttendanceSummary = (fromDate: string, toDate: string) =>
  useQuery({
    queryKey: [...root, 'attendance', 'summary', fromDate, toDate],
    queryFn: () => selfServiceApi.attendanceSummary(fromDate, toDate),
    enabled: Boolean(fromDate && toDate),
  });

export const useMyCalendar = (year: number, month: number) =>
  useQuery({
    queryKey: [...root, 'calendar', year, month],
    queryFn: () => selfServiceApi.calendar(year, month),
  });

export const useMyRegularizations = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'regularizations', params],
    queryFn: () => selfServiceApi.regularizations({ page: 1, page_size: 50, ...params }),
  });

export const useMyLeaveBalance = (year?: number) =>
  useQuery({
    queryKey: [...root, 'leave-balance', year ?? 'current'],
    queryFn: () => selfServiceApi.leaveBalance(year),
  });

export const useMyLeaveTypes = () =>
  useQuery({ queryKey: [...root, 'leave-types'], queryFn: () => selfServiceApi.leaveTypes() });

export const useMyLeave = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'leave', params],
    queryFn: () => selfServiceApi.leave({ page: 1, page_size: 50, ...params }),
  });

export const useMyTimesheetWeek = (weekStart?: string) =>
  useQuery({
    queryKey: [...root, 'timesheet-week', weekStart ?? 'current'],
    queryFn: () => selfServiceApi.currentWeek(weekStart),
  });

export const useMyTimesheets = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'timesheets', params],
    queryFn: () => selfServiceApi.timesheets({ page: 1, page_size: 50, ...params }),
  });

export const useMyDocuments = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...root, 'documents', params],
    queryFn: () => selfServiceApi.documents({ page: 1, page_size: 50, ...params }),
  });

export const useMyDocumentTypes = () =>
  useQuery({ queryKey: [...root, 'document-types'], queryFn: () => selfServiceApi.documentTypes() });

export const useMyProjects = () =>
  useQuery({ queryKey: [...root, 'projects'], queryFn: () => selfServiceApi.projects() });

export const useMyHolidays = (year?: number) =>
  useQuery({
    queryKey: [...root, 'holidays', year ?? 'current'],
    queryFn: () => selfServiceApi.holidays(year),
  });

// ---------------------------------------------------------------------------
// Mutations
// ---------------------------------------------------------------------------
function useMyMutation<TVariables, TResult>(
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
      // The server's message verbatim: it names the rule that was broken -- how
      // many days are left, which week is locked, which project is not mine --
      // and a generic failure would hide the part that says what to do next.
      toast.error(labels.failed, { description: error.message });
    },
  });
}

export const useCheckIn = () =>
  useMyMutation((data: unknown) => selfServiceApi.checkIn(data), {
    done: 'Checked in',
    failed: 'Could not check in',
  });

export const useCheckOut = () =>
  useMyMutation((data: unknown) => selfServiceApi.checkOut(data), {
    done: 'Checked out',
    failed: 'Could not check out',
  });

export const useRequestRegularization = () =>
  useMyMutation((data: unknown) => selfServiceApi.requestRegularization(data), {
    done: 'Correction requested',
    failed: 'Could not request this correction',
  });

export const useApplyForLeave = () =>
  useMyMutation((data: unknown) => selfServiceApi.applyForLeave(data), {
    done: 'Leave applied',
    failed: 'Could not apply for this leave',
  });

export const useCancelMyLeave = () =>
  useMyMutation((id: string) => selfServiceApi.cancelLeave(id), {
    done: 'Leave cancelled',
    failed: 'Could not cancel this leave',
  });

export const useSaveMyTimesheet = () =>
  useMyMutation((data: unknown) => selfServiceApi.saveTimesheet(data), {
    done: 'Timesheet saved',
    failed: 'Could not save this timesheet',
  });

export const useSubmitMyTimesheet = () =>
  useMyMutation((id: string) => selfServiceApi.submitTimesheet(id), {
    done: 'Timesheet submitted',
    failed: 'Could not submit this timesheet',
  });

export const useUploadMyDocument = () =>
  useMyMutation((form: FormData) => selfServiceApi.uploadDocument(form), {
    done: 'Document uploaded',
    failed: 'Could not upload this document',
  });

export const useReplaceMyDocument = () =>
  useMyMutation(({ id, form }: { id: string; form: FormData }) => selfServiceApi.replaceDocument(id, form), {
    done: 'Replacement uploaded',
    failed: 'Could not replace this document',
  });

export const useUpdateMyProfile = () =>
  useMyMutation((data: unknown) => selfServiceApi.updateProfile(data), {
    done: 'Profile updated',
    failed: 'Could not update your profile',
  });

export const useSetMyAddress = () =>
  useMyMutation((data: unknown) => selfServiceApi.setAddress(data), {
    done: 'Address updated',
    failed: 'Could not update your address',
  });
