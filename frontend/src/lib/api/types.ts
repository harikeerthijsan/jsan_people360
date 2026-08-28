/**
 * Transport-level contract shared with the FastAPI backend.
 *
 * Every endpoint returns the same envelope, so these types are declared once
 * here and reused by every feature module.
 */

/** A single, user-presentable error entry. */
export interface ApiErrorDetail {
  code: string;
  message: string;
  /** Dotted path of the offending field, when the error is field-scoped. */
  field: string | null;
}

/** The standard response envelope. */
export interface ApiResponse<TData> {
  success: boolean;
  message: string;
  data: TData | null;
  errors: ApiErrorDetail[] | null;
}

/** Pagination metadata attached to list responses. */
export interface PageMeta {
  page: number;
  page_size: number;
  total_items: number;
  total_pages: number;
  has_next: boolean;
  has_previous: boolean;
}

/** Envelope payload for paginated collections. */
export interface Page<TItem> {
  items: TItem[];
  meta: PageMeta;
}

/** Payload for endpoints that only acknowledge an action. */
export interface MessageData {
  detail: string;
}
