/**
 * Domain types for the Document Management module.
 *
 * Deliberately generic. The vault is not an employee feature: recruitment will
 * attach résumés to candidates and the organization holds its own registrations,
 * so nothing here names an employee except as one possible owner.
 */

import type { MasterRecord, MasterSummary } from '@/features/organization/types/organization.types';

export type DocumentOwnerType = 'employee' | 'candidate' | 'organization' | 'user';

export type DocumentStatus = 'uploaded' | 'under_review' | 'approved' | 'rejected' | 'expired' | 'archived';

export type ExpiryState = 'none' | 'valid' | 'expiring_soon' | 'expired';

export const OWNER_TYPE_LABELS: Record<DocumentOwnerType, string> = {
  employee: 'Employee',
  candidate: 'Candidate',
  organization: 'Organization',
  user: 'User',
};

/** Ordered as a document moves through review, not alphabetically. */
export const DOCUMENT_STATUSES: readonly DocumentStatus[] = [
  'uploaded',
  'under_review',
  'approved',
  'rejected',
  'expired',
  'archived',
] as const;

/**
 * The statuses a document can actually be found in, and so the only ones worth
 * offering as a filter.
 *
 * `expired` and `archived` are in the type because the API models them, but
 * nothing ever writes them: expiry is *derived* from the date and has its own
 * filter, and archiving is recorded by `deleted_at` and has its own view.
 * Listing them here would give two choices that always return nothing — and
 * "Expired" would be the more misleading of the two, because expired documents
 * genuinely exist, just not under this filter.
 */
export const FILTERABLE_DOCUMENT_STATUSES: readonly DocumentStatus[] = [
  'uploaded',
  'under_review',
  'approved',
  'rejected',
] as const;

export const DOCUMENT_STATUS_LABELS: Record<DocumentStatus, string> = {
  uploaded: 'Uploaded',
  under_review: 'Under review',
  approved: 'Approved',
  rejected: 'Rejected',
  expired: 'Expired',
  archived: 'Archived',
};

export const EXPIRY_STATE_LABELS: Record<ExpiryState, string> = {
  none: 'No expiry',
  valid: 'Valid',
  expiring_soon: 'Expiring soon',
  expired: 'Expired',
};

/** The statuses a review may set. The others are derived or have their own action. */
export const REVIEWABLE_STATUSES: readonly DocumentStatus[] = [
  'under_review',
  'approved',
  'rejected',
] as const;

/**
 * What the vault accepts, mirroring the server's allowlist.
 *
 * Used for the file picker's `accept` attribute and for immediate feedback. The
 * server checks the file's actual content signature regardless — this is a
 * convenience, never the enforcement point.
 */
export const ACCEPTED_EXTENSIONS: readonly string[] = ['.pdf', '.jpg', '.jpeg', '.png'] as const;
export const ACCEPTED_MIME_TYPES: readonly string[] = ['application/pdf', 'image/jpeg', 'image/png'] as const;

/** Matches the platform default; the server is authoritative. */
export const MAX_UPLOAD_MB = 10;

export interface DocumentCategoryRecord extends MasterRecord {
  code: string;
  display_order: number;
}

export interface DocumentTypeRecord extends MasterRecord {
  code: string;
  category_id: string;
  category: MasterSummary | null;
  requires_expiry: boolean;
  is_sensitive: boolean;
  allowed_extensions: string | null;
}

/** One uploaded file. No storage path — the server never returns one. */
export interface DocumentVersionRecord {
  id: string;
  version_number: number;
  original_filename: string;
  content_type: string;
  size_bytes: number;
  size_display: string;
  checksum: string;
  notes: string | null;
  created_at: string;
  created_by: string | null;
}

export interface DocumentAuditEntry {
  id: string;
  action: string;
  outcome: string;
  description: string | null;
  actor_id: string | null;
  actor_email: string | null;
  context: Record<string, unknown> | null;
  created_at: string;
}

/** The owner, resolved to something a person recognises. */
export interface DocumentOwnerRef {
  owner_type: DocumentOwnerType;
  owner_id: string;
  /** Null when the owner no longer exists or cannot be resolved. */
  display_name: string | null;
  reference_code: string | null;
}

export interface DocumentRecord {
  id: string;
  document_code: string;
  name: string;
  description: string | null;

  category_id: string;
  document_type_id: string;
  category: MasterSummary | null;
  document_type: MasterSummary | null;

  owner_type: DocumentOwnerType;
  owner_id: string;
  owner: DocumentOwnerRef | null;

  status: DocumentStatus;
  expiry_date: string | null;
  /** Derived by the server on every read, so it is never stale. */
  expiry_state: ExpiryState;
  review_notes: string | null;
  reviewed_at: string | null;
  reviewed_by: string | null;

  current_version: DocumentVersionRecord | null;
  version_count: number;

  created_at: string;
  updated_at: string;
  created_by: string | null;
  updated_by: string | null;
  /** Non-null when the document has been archived. */
  deleted_at: string | null;
}

export interface CountByLabel {
  label: string;
  count: number;
}

export interface DocumentDashboardStats {
  total_documents: number;
  pending_review: number;
  expiring_soon: number;
  expired: number;
  approved: number;
  rejected: number;
  archived: number;
  total_storage_bytes: number;
  by_category: CountByLabel[];
  by_status: CountByLabel[];
}

/** Query parameters accepted by the document list endpoint. */
export interface DocumentListQuery {
  page: number;
  page_size: number;
  search?: string;
  archived: boolean;
  sort_by: string;
  sort_order: 'asc' | 'desc';

  status?: DocumentStatus;
  category_id?: string;
  document_type_id?: string;
  owner_type?: DocumentOwnerType;
  owner_id?: string;
  expiry_state?: ExpiryState;
  uploaded_from?: string;
  uploaded_to?: string;
}

/** True when the document has been archived. */
export function isArchived(document: Pick<DocumentRecord, 'deleted_at'>): boolean {
  return document.deleted_at !== null;
}

/** Whether the browser can display this content type without downloading it. */
export function isPreviewable(contentType: string): boolean {
  return ACCEPTED_MIME_TYPES.includes(contentType);
}

export function isImage(contentType: string): boolean {
  return contentType.startsWith('image/');
}

export function isPdf(contentType: string): boolean {
  return contentType === 'application/pdf';
}

/** Format a byte count for display. The server sends one too; this is for totals. */
export function formatBytes(bytes: number): string {
  if (bytes === 0) return '0 B';

  const units = ['B', 'KB', 'MB', 'GB'];
  const exponent = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const value = bytes / Math.pow(1024, exponent);

  return `${exponent === 0 ? String(value) : value.toFixed(1)} ${units[exponent] ?? 'B'}`;
}
