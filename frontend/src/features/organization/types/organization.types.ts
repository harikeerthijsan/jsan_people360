/**
 * Domain types for the Organization Management module, mirroring the API.
 *
 * The nine masters share a base shape and differ only in which extra fields
 * they carry. Rather than nine unrelated interfaces plus nine parallel sets of
 * table and form components, they are modelled as one record type whose
 * entity-specific fields are optional.
 *
 * That is an accurate description of the wire format -- a grade genuinely has no
 * `business_unit` -- and it is what lets one set of generic screens drive every
 * master while every field access stays `undefined`-checked by the compiler.
 */

export type RecordStatus = 'active' | 'inactive';

/** URL slug for a master; also its key in the registry and its API path. */
export type MasterSlug =
  'organizations' | 'business-units' | 'teams' | 'designations' | 'locations' | 'employment-types' | 'grades';

/** Compact reference to another master record, embedded in list responses. */
export interface MasterSummary {
  id: string;
  name: string;
  code: string | null;
  status: RecordStatus;
}

/** Compact reference to a user, used for a team's manager. */
export interface UserSummaryRef {
  id: string;
  email: string;
  full_name: string;
  avatar_url: string | null;
}

/** Fields present on every master record. */
export interface MasterRecordBase {
  id: string;
  name: string;
  description: string | null;
  status: RecordStatus;
  created_at: string;
  updated_at: string;
  created_by: string | null;
  updated_by: string | null;
  /** Non-null when the record is archived. */
  deleted_at: string | null;
}

/**
 * A master record of any kind.
 *
 * Entity-specific fields are optional because they are genuinely absent from
 * the other entities' responses.
 */
export interface MasterRecord extends MasterRecordBase {
  /** Present on every master except teams. */
  code?: string;

  // -- Hierarchy parents ---------------------------------------------
  business_unit_id?: string;
  business_unit?: MasterSummary;
  manager_id?: string | null;
  manager?: UserSummaryRef | null;

  // -- Designations and grades ---------------------------------------
  level?: number;

  // -- Locations ------------------------------------------------------
  country?: string;
  state?: string;
  city?: string;
  address?: string;
  timezone?: string;

  // -- Organization profile -------------------------------------------
  legal_name?: string;
  registration_number?: string;
  gst_number?: string | null;
  pan_number?: string | null;
  logo_url?: string | null;
  website?: string | null;
  currency?: string;
  address_line1?: string;
  address_line2?: string | null;
  postal_code?: string | null;
}

/** Query parameters accepted by every master list endpoint. */
export interface MasterListQuery {
  page: number;
  page_size: number;
  search?: string;
  status?: RecordStatus;
  archived: boolean;
  sort_by: string;
  sort_order: 'asc' | 'desc';
  /** Parent filters, supported by the masters that have a parent. */
  business_unit_id?: string;
}

/**
 * Form values for any master.
 *
 * Field names are configuration rather than literals, so the value map is keyed
 * by string. Every form is still validated by its own Zod schema before it is
 * submitted, and again by Pydantic on the server.
 */
export type MasterFormValues = Record<string, unknown>;

/** True when a record has been soft deleted. */
export function isArchived(record: MasterRecordBase): boolean {
  return record.deleted_at !== null;
}
