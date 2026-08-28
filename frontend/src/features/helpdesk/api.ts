import { api, apiClient } from '@/lib/api/client';
import { endpoints } from '@/lib/api/endpoints';
import type { Page } from '@/lib/api/types';

import type {
  Announcement,
  AnnouncementDetail,
  AnnouncementInput,
  HelpdeskDashboard,
  MyAnnouncement,
  MyTicket,
  MyTicketCategory,
  MyTicketDetail,
  Ticket,
  TicketCategory,
  TicketCommentInput,
  TicketDetail,
  TicketFilters,
  TicketRaiseInput,
  TicketStatusInput,
} from './types';

/**
 * Transport for the helpdesk and for announcements.
 *
 * Split into `mine` and `admin` because the server splits them the same way.
 * Nothing under `mine` carries an employee id — the requester and the reader
 * both come from the access token — and the employee ticket endpoints return a
 * model that cannot contain an internal agent note.
 */

const me = endpoints.me.root;
const helpdesk = endpoints.helpdesk.root;
const announcements = endpoints.announcements.root;

export const helpdeskApi = {
  /** The signed-in employee's own requests and notices. */
  mine: {
    tickets: () => api.get<MyTicket[]>(`${me}/helpdesk`),
    categories: () => api.get<MyTicketCategory[]>(`${me}/helpdesk/categories`),
    ticket: (ticketId: string) => api.get<MyTicketDetail>(`${me}/helpdesk/${ticketId}`),
    raise: (payload: TicketRaiseInput) => api.post<MyTicket>(`${me}/helpdesk`, payload),
    reply: (ticketId: string, body: string) =>
      api.post<unknown>(`${me}/helpdesk/${ticketId}/reply`, { body }),
    reopen: (ticketId: string, note?: string) =>
      api.post<MyTicketDetail>(`${me}/helpdesk/${ticketId}/reopen`, null, {
        params: note ? { note } : undefined,
      }),

    announcements: () => api.get<MyAnnouncement[]>(`${me}/announcements`),
    acknowledge: (announcementId: string) =>
      api.post<unknown>(`${me}/announcements/${announcementId}/acknowledge`),
  },

  /** The desk. Each call is permission-guarded on the server. */
  admin: {
    tickets: (filters: TicketFilters = {}) =>
      api.get<Page<Ticket>>(helpdesk, { params: { page: 1, page_size: 20, ...filters } }),
    ticket: (ticketId: string) => api.get<TicketDetail>(`${helpdesk}/${ticketId}`),
    dashboard: () => api.get<HelpdeskDashboard>(`${helpdesk}/dashboard`),
    categories: (includeInactive = false) =>
      api.get<TicketCategory[]>(`${helpdesk}/categories`, {
        params: { include_inactive: includeInactive },
      }),

    comment: (ticketId: string, payload: TicketCommentInput) =>
      api.post<unknown>(`${helpdesk}/${ticketId}/comments`, payload),
    changeStatus: (ticketId: string, payload: TicketStatusInput) =>
      api.post<Ticket>(`${helpdesk}/${ticketId}/status`, payload),
    assign: (ticketId: string, assignedToId: string | null) =>
      api.post<Ticket>(`${helpdesk}/${ticketId}/assign`, { assigned_to_id: assignedToId }),
    reclassify: (ticketId: string, payload: { category_id?: string; priority?: string }) =>
      api.post<Ticket>(`${helpdesk}/${ticketId}/reclassify`, payload),
  },

  /** Announcements: writing, sending and reading the acknowledgements. */
  announcements: {
    list: (params: Record<string, unknown> = {}) =>
      api.get<Page<Announcement>>(announcements, { params: { page: 1, page_size: 20, ...params } }),
    get: (announcementId: string) => api.get<AnnouncementDetail>(`${announcements}/${announcementId}`),
    create: (payload: AnnouncementInput) => api.post<Announcement>(announcements, payload),
    update: (announcementId: string, payload: Partial<AnnouncementInput>) =>
      api.patch<Announcement>(`${announcements}/${announcementId}`, payload),
    publish: (announcementId: string, publishAt?: string | null) =>
      api.post<Announcement>(`${announcements}/${announcementId}/publish`, {
        publish_at: publishAt ?? null,
      }),
    archive: (announcementId: string) => api.post<Announcement>(`${announcements}/${announcementId}/archive`),
    /**
     * Deleting answers 204 with no body at all, so this goes through the raw
     * client. `api.delete` unwraps an envelope and throws when `data` is
     * absent, which would turn a successful delete into a reported failure.
     */
    remove: async (announcementId: string): Promise<void> => {
      await apiClient.delete(`${announcements}/${announcementId}`);
    },
  },
};
