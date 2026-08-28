/**
 * Helpdesk and announcement types, mirroring the API schemas.
 *
 * `MyTicketComment` has no `internal` field — the same omission the server
 * makes, for the same reason. An agent's working note is not part of what the
 * requester sees, and a type that cannot carry the flag cannot render it.
 *
 * `TicketStatus` transitions are the server's to decide. A ticket's detail
 * response carries `allowed_transitions`, so the status control offers exactly
 * what the backend will accept and the client holds no copy of the table.
 */

export type TicketStatus =
  'open' | 'in_progress' | 'waiting_on_employee' | 'resolved' | 'closed' | 'cancelled' | 'reopened';

export type TicketPriority = 'low' | 'medium' | 'high' | 'urgent';
export type TicketQueue = 'hr' | 'it' | 'admin' | 'finance' | 'facilities';

export type TicketEvent =
  | 'raised'
  | 'assigned'
  | 'status_changed'
  | 'commented'
  | 'priority_changed'
  | 'category_changed'
  | 'resolved'
  | 'reopened'
  | 'closed';

export interface TicketCategory {
  id: string;
  name: string;
  code: string;
  description: string | null;
  queue: TicketQueue;
  sla_hours: number | null;
  default_assignee_id: string | null;
  status: 'active' | 'inactive';
}

export interface EmployeeSummary {
  id: string;
  employee_code: string;
  full_name: string;
}

export interface TicketComment {
  id: string;
  author_id: string | null;
  body: string;
  internal: boolean;
  attachment_ids: string[];
  created_at: string;
}

export interface TicketHistoryEntry {
  id: string;
  event: TicketEvent;
  previous_value: string | null;
  new_value: string | null;
  notes: string | null;
  created_at: string;
  created_by: string | null;
}

export interface Ticket {
  id: string;
  ticket_code: string;
  subject: string;
  description: string;
  category: TicketCategory;
  queue: TicketQueue;
  raised_by: EmployeeSummary;
  raised_for: EmployeeSummary | null;
  assigned_to_id: string | null;
  status: TicketStatus;
  priority: TicketPriority;
  due_at: string | null;
  is_overdue: boolean;
  first_responded_at: string | null;
  resolved_at: string | null;
  closed_at: string | null;
  resolution: string | null;
  reopen_count: number;
  attachment_ids: string[];
  created_at: string;
  updated_at: string;
}

export interface TicketDetail extends Ticket {
  comments: TicketComment[];
  history: TicketHistoryEntry[];
  /** What the server will accept next. The client holds no transition table. */
  allowed_transitions: TicketStatus[];
}

/** A category as the requester sees it: enough to choose one, nothing about staffing. */
export interface MyTicketCategory {
  id: string;
  name: string;
  description: string | null;
}

/** The requester's view of a message. Deliberately has no `internal` field. */
export interface MyTicketComment {
  id: string;
  body: string;
  attachment_ids: string[];
  created_at: string;
  from_agent: boolean;
}

export interface MyTicket {
  id: string;
  ticket_code: string;
  subject: string;
  category: string;
  status: TicketStatus;
  priority: TicketPriority;
  created_at: string;
  resolved_at: string | null;
  awaiting_me: boolean;
}

export interface MyTicketDetail extends MyTicket {
  description: string;
  resolution: string | null;
  comments: MyTicketComment[];
  can_reply: boolean;
  can_reopen: boolean;
}

export interface QueueCount {
  label: string;
  count: number;
}

export interface HelpdeskDashboard {
  open_tickets: number;
  unassigned: number;
  overdue: number;
  waiting_on_employee: number;
  resolved_today: number;
  reopened: number;
  by_queue: QueueCount[];
  by_category: QueueCount[];
  by_priority: QueueCount[];
  my_queue: number;
}

// -- Announcements -------------------------------------------------------
export type AnnouncementStatus = 'draft' | 'scheduled' | 'published' | 'archived';
export type AnnouncementAudience = 'all' | 'business_unit' | 'team' | 'location';
export type AnnouncementPriority = 'normal' | 'important' | 'urgent';

export interface AcknowledgementRow {
  employee_id: string;
  employee_name: string;
  acknowledged_at: string;
}

export interface Announcement {
  id: string;
  title: string;
  body: string;
  summary: string | null;
  audience: AnnouncementAudience;
  target_ids: string[];
  priority: AnnouncementPriority;
  status: AnnouncementStatus;
  pinned: boolean;
  requires_acknowledgement: boolean;
  publish_at: string | null;
  published_at: string | null;
  expires_at: string | null;
  published_by_id: string | null;
  attachment_ids: string[];
  created_at: string;
  updated_at: string;
  audience_size: number | null;
  acknowledged_count: number;
  is_live: boolean;
}

export interface AnnouncementDetail extends Announcement {
  acknowledgements: AcknowledgementRow[];
}

/** What an employee reads. No author, no audience, no acknowledgement roll. */
export interface MyAnnouncement {
  id: string;
  title: string;
  body: string;
  summary: string | null;
  priority: AnnouncementPriority;
  pinned: boolean;
  published_at: string | null;
  expires_at: string | null;
  attachment_ids: string[];
  requires_acknowledgement: boolean;
  acknowledged: boolean;
}

// -- Request payloads ----------------------------------------------------
export interface TicketRaiseInput {
  category_id: string;
  subject: string;
  description: string;
  priority?: TicketPriority;
  attachment_ids?: string[];
}

export interface TicketCommentInput {
  body: string;
  internal?: boolean;
  attachment_ids?: string[];
}

export interface TicketStatusInput {
  status: TicketStatus;
  note?: string | null;
  resolution?: string | null;
}

export interface AnnouncementInput {
  title: string;
  body: string;
  summary?: string | null;
  audience: AnnouncementAudience;
  target_ids?: string[];
  priority?: AnnouncementPriority;
  pinned?: boolean;
  requires_acknowledgement?: boolean;
  publish_at?: string | null;
  expires_at?: string | null;
}

export interface TicketFilters {
  search?: string;
  status?: TicketStatus;
  priority?: TicketPriority;
  queue?: TicketQueue;
  category_id?: string;
  assigned_to_id?: string;
  employee_id?: string;
  unassigned?: boolean;
  overdue?: boolean;
  open_only?: boolean;
  page?: number;
  page_size?: number;
}

// -- Labels --------------------------------------------------------------
export const TICKET_STATUS_LABELS: Record<TicketStatus, string> = {
  open: 'Open',
  in_progress: 'In progress',
  waiting_on_employee: 'Waiting on you',
  resolved: 'Resolved',
  closed: 'Closed',
  cancelled: 'Cancelled',
  reopened: 'Reopened',
};

export const TICKET_PRIORITY_LABELS: Record<TicketPriority, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  urgent: 'Urgent',
};

export const TICKET_QUEUE_LABELS: Record<TicketQueue, string> = {
  hr: 'HR',
  it: 'IT',
  admin: 'Admin',
  finance: 'Finance',
  facilities: 'Facilities',
};

export const ANNOUNCEMENT_STATUS_LABELS: Record<AnnouncementStatus, string> = {
  draft: 'Draft',
  scheduled: 'Scheduled',
  published: 'Published',
  archived: 'Archived',
};

export const ANNOUNCEMENT_AUDIENCE_LABELS: Record<AnnouncementAudience, string> = {
  all: 'Everybody',
  business_unit: 'Business unit',
  team: 'Team',
  location: 'Location',
};

export const ANNOUNCEMENT_PRIORITY_LABELS: Record<AnnouncementPriority, string> = {
  normal: 'Normal',
  important: 'Important',
  urgent: 'Urgent',
};
