import { api } from '@/lib/api/client';
import { endpoints } from '@/lib/api/endpoints';
import type { Page } from '@/lib/api/types';
import type {
  MasterFormValues,
  MasterListQuery,
  MasterRecord,
  MasterSlug,
} from '@/features/organization/types/organization.types';

/**
 * Transport for the master-data endpoints.
 *
 * Every master exposes the same six operations at the same shapes, so the
 * client is built once and bound to a slug. Adding a master means adding a
 * config entry, not another API module.
 */

/** Drop undefined values so they are not serialised as "undefined" strings. */
function toQueryParams(query: MasterListQuery): Record<string, string> {
  const params: Record<string, string> = {
    page: String(query.page),
    page_size: String(query.page_size),
    sort_by: query.sort_by,
    sort_order: query.sort_order,
    archived: String(query.archived),
  };

  if (query.search) params['search'] = query.search;
  if (query.status) params['status'] = query.status;
  if (query.business_unit_id) params['business_unit_id'] = query.business_unit_id;

  return params;
}

export interface MasterApi {
  list: (query: MasterListQuery) => Promise<Page<MasterRecord>>;
  get: (id: string) => Promise<MasterRecord>;
  create: (values: MasterFormValues) => Promise<MasterRecord>;
  update: (id: string, values: MasterFormValues) => Promise<MasterRecord>;
  archive: (id: string) => Promise<MasterRecord>;
  restore: (id: string) => Promise<MasterRecord>;
}

/** Build the API client for one master. */
export function createMasterApi(slug: MasterSlug): MasterApi {
  const base = `${endpoints.organization.root}/${slug}`;

  return {
    list: (query) => api.get<Page<MasterRecord>>(base, { params: toQueryParams(query) }),
    get: (id) => api.get<MasterRecord>(`${base}/${id}`),
    create: (values) => api.post<MasterRecord>(base, values),
    update: (id, values) => api.patch<MasterRecord>(`${base}/${id}`, values),
    archive: (id) => api.post<MasterRecord>(`${base}/${id}/archive`),
    restore: (id) => api.post<MasterRecord>(`${base}/${id}/restore`),
  };
}

/** The organization profile other modules default to. */
export function getPrimaryOrganization(): Promise<MasterRecord> {
  return api.get<MasterRecord>(endpoints.organization.primaryOrganization);
}
