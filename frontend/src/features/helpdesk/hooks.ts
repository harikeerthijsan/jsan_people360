'use client';

import { useMutation, useQuery, useQueryClient, type UseMutationResult } from '@tanstack/react-query';

import { toast } from '@/components/ui/sonner';
import type { AppError } from '@/lib/errors';

import { helpdeskApi } from './api';
import type {
  Announcement,
  AnnouncementInput,
  MyTicket,
  TicketCommentInput,
  TicketFilters,
  TicketRaiseInput,
  TicketStatusInput,
} from './types';

/**
 * Data hooks for the helpdesk and for announcements.
 *
 * Two query roots per module, matching the two audiences. An agent working
 * through a queue should not evict the employee's own request list, and an
 * employee acknowledging a notice should not evict the acknowledgement roll an
 * HR user is reading beside it.
 *
 * Within a root, every mutation invalidates the whole root. A ticket's figures
 * interlock -- resolving one changes the list, the dashboard counters, the
 * ticket's own detail and its history at once -- and invalidating selectively
 * is how two numbers on the same screen end up disagreeing.
 */

const myTicketsKey = ['me', 'helpdesk'] as const;
const myAnnouncementsKey = ['me', 'announcements'] as const;
const deskKey = ['helpdesk'] as const;
const announcementsKey = ['announcements'] as const;

// ---------------------------------------------------------------------------
// The employee's own
// ---------------------------------------------------------------------------
export const useMyTickets = () =>
  useQuery({ queryKey: myTicketsKey, queryFn: () => helpdeskApi.mine.tickets() });

export const useMyTicket = (ticketId: string) =>
  useQuery({
    queryKey: [...myTicketsKey, ticketId],
    queryFn: () => helpdeskApi.mine.ticket(ticketId),
    enabled: Boolean(ticketId),
  });

export const useMyTicketCategories = () =>
  useQuery({
    queryKey: [...myTicketsKey, 'categories'],
    queryFn: () => helpdeskApi.mine.categories(),
    // Master data: changes rarely, read every time the raise dialog opens.
    staleTime: 5 * 60_000,
  });

export const useMyAnnouncements = () =>
  useQuery({ queryKey: myAnnouncementsKey, queryFn: () => helpdeskApi.mine.announcements() });

/**
 * A mutation an employee makes about their own request.
 *
 * Refreshes the desk root too. An agent watching a queue wants the reply that
 * just arrived, and the alternative -- a stale list until something else
 * happens to refetch it -- is how a request sits unanswered.
 */
const useMyMutation = <TInput, TResult>(
  fn: (input: TInput) => Promise<TResult>,
  message: string,
): UseMutationResult<TResult, AppError, TInput> => {
  const queryClient = useQueryClient();
  return useMutation<TResult, AppError, TInput>({
    mutationFn: fn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: myTicketsKey });
      void queryClient.invalidateQueries({ queryKey: deskKey });
      toast.success(message);
    },
    onError: (error) => toast.error(error.message),
  });
};

export const useRaiseTicket = (): UseMutationResult<MyTicket, AppError, TicketRaiseInput> =>
  useMyMutation((input: TicketRaiseInput) => helpdeskApi.mine.raise(input), 'Request raised');

export const useReplyToTicket = () =>
  useMyMutation(
    ({ ticketId, body }: { ticketId: string; body: string }) => helpdeskApi.mine.reply(ticketId, body),
    'Reply sent',
  );

export const useReopenTicket = () =>
  useMyMutation(
    ({ ticketId, note }: { ticketId: string; note?: string }) => helpdeskApi.mine.reopen(ticketId, note),
    'Request reopened',
  );

export const useAcknowledgeAnnouncement = () => {
  const queryClient = useQueryClient();
  return useMutation<unknown, AppError, string>({
    mutationFn: (announcementId) => helpdeskApi.mine.acknowledge(announcementId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: myAnnouncementsKey });
      // The sender's acknowledgement count moved.
      void queryClient.invalidateQueries({ queryKey: announcementsKey });
      toast.success('Acknowledged');
    },
    onError: (error) => toast.error(error.message),
  });
};

// ---------------------------------------------------------------------------
// The desk
// ---------------------------------------------------------------------------
export const useTickets = (filters: TicketFilters = {}) =>
  useQuery({
    queryKey: [...deskKey, 'list', filters],
    queryFn: () => helpdeskApi.admin.tickets(filters),
    // Filtered server-side, so a new filter is a new query rather than a
    // re-filter of something already in memory.
    placeholderData: (previous) => previous,
  });

export const useTicket = (ticketId: string) =>
  useQuery({
    queryKey: [...deskKey, 'detail', ticketId],
    queryFn: () => helpdeskApi.admin.ticket(ticketId),
    enabled: Boolean(ticketId),
  });

export const useHelpdeskDashboard = () =>
  useQuery({
    queryKey: [...deskKey, 'dashboard'],
    queryFn: () => helpdeskApi.admin.dashboard(),
    staleTime: 30_000,
  });

export const useTicketCategories = (includeInactive = false) =>
  useQuery({
    queryKey: [...deskKey, 'categories', includeInactive],
    queryFn: () => helpdeskApi.admin.categories(includeInactive),
    // Master data: changes rarely, read on nearly every helpdesk screen.
    staleTime: 5 * 60_000,
  });

const useDeskMutation = <TInput, TResult>(
  fn: (input: TInput) => Promise<TResult>,
  message: string,
): UseMutationResult<TResult, AppError, TInput> => {
  const queryClient = useQueryClient();
  return useMutation<TResult, AppError, TInput>({
    mutationFn: fn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: deskKey });
      // The requester is watching the same ticket from the other side.
      void queryClient.invalidateQueries({ queryKey: myTicketsKey });
      toast.success(message);
    },
    onError: (error) => toast.error(error.message),
  });
};

export const useCommentOnTicket = () =>
  useDeskMutation(
    ({ ticketId, payload }: { ticketId: string; payload: TicketCommentInput }) =>
      helpdeskApi.admin.comment(ticketId, payload),
    'Comment added',
  );

export const useChangeTicketStatus = () =>
  useDeskMutation(
    ({ ticketId, payload }: { ticketId: string; payload: TicketStatusInput }) =>
      helpdeskApi.admin.changeStatus(ticketId, payload),
    'Status updated',
  );

export const useAssignTicket = () =>
  useDeskMutation(
    ({ ticketId, assignedToId }: { ticketId: string; assignedToId: string | null }) =>
      helpdeskApi.admin.assign(ticketId, assignedToId),
    'Request assigned',
  );

export const useReclassifyTicket = () =>
  useDeskMutation(
    ({ ticketId, payload }: { ticketId: string; payload: { category_id?: string; priority?: string } }) =>
      helpdeskApi.admin.reclassify(ticketId, payload),
    'Request reclassified',
  );

// ---------------------------------------------------------------------------
// Announcements
// ---------------------------------------------------------------------------
export const useAnnouncements = (params: Record<string, unknown> = {}) =>
  useQuery({
    queryKey: [...announcementsKey, 'list', params],
    queryFn: () => helpdeskApi.announcements.list(params),
    placeholderData: (previous) => previous,
  });

export const useAnnouncement = (announcementId: string) =>
  useQuery({
    queryKey: [...announcementsKey, 'detail', announcementId],
    queryFn: () => helpdeskApi.announcements.get(announcementId),
    enabled: Boolean(announcementId),
  });

const useAnnouncementMutation = <TInput, TResult>(
  fn: (input: TInput) => Promise<TResult>,
  message: string,
): UseMutationResult<TResult, AppError, TInput> => {
  const queryClient = useQueryClient();
  return useMutation<TResult, AppError, TInput>({
    mutationFn: fn,
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: announcementsKey });
      // Publishing puts a notice on every reader's screen, including the
      // sender's own portal and the employee dashboard.
      void queryClient.invalidateQueries({ queryKey: myAnnouncementsKey });
      void queryClient.invalidateQueries({ queryKey: ['me', 'dashboard'] });
      toast.success(message);
    },
    onError: (error) => toast.error(error.message),
  });
};

export const useCreateAnnouncement = (): UseMutationResult<Announcement, AppError, AnnouncementInput> =>
  useAnnouncementMutation(
    (input: AnnouncementInput) => helpdeskApi.announcements.create(input),
    'Draft saved',
  );

export const useUpdateAnnouncement = () =>
  useAnnouncementMutation(
    ({ announcementId, payload }: { announcementId: string; payload: Partial<AnnouncementInput> }) =>
      helpdeskApi.announcements.update(announcementId, payload),
    'Announcement updated',
  );

export const usePublishAnnouncement = () =>
  useAnnouncementMutation(
    ({ announcementId, publishAt }: { announcementId: string; publishAt?: string | null }) =>
      helpdeskApi.announcements.publish(announcementId, publishAt),
    'Announcement sent',
  );

export const useArchiveAnnouncement = () =>
  useAnnouncementMutation(
    (announcementId: string) => helpdeskApi.announcements.archive(announcementId),
    'Announcement archived',
  );

export const useDeleteAnnouncement = () =>
  useAnnouncementMutation(
    (announcementId: string) => helpdeskApi.announcements.remove(announcementId),
    'Announcement deleted',
  );
