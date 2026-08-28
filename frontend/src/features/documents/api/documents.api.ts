import { api, apiClient } from '@/lib/api/client';
import { endpoints } from '@/lib/api/endpoints';
import type { Page } from '@/lib/api/types';
import type {
  DocumentDashboardStats,
  DocumentAuditEntry,
  DocumentListQuery,
  DocumentRecord,
  DocumentVersionRecord,
} from '@/features/documents/types/document.types';

/** Transport for the Document Management endpoints. */

const root = endpoints.documents.root;

/** Only parameters that carry a value are sent; an empty string is a real value to the server. */
function toQueryParams(query: DocumentListQuery): Record<string, string> {
  const params: Record<string, string> = {
    page: String(query.page),
    page_size: String(query.page_size),
    sort_by: query.sort_by,
    sort_order: query.sort_order,
    archived: String(query.archived),
  };

  const optional: (keyof DocumentListQuery)[] = [
    'search',
    'status',
    'category_id',
    'document_type_id',
    'owner_type',
    'owner_id',
    'expiry_state',
    'uploaded_from',
    'uploaded_to',
  ];

  for (const key of optional) {
    const value = query[key];
    if (typeof value === 'string' && value !== '') {
      params[key] = value;
    }
  }

  return params;
}

export interface UploadFields {
  name: string;
  category_id: string;
  document_type_id: string;
  owner_type: string;
  owner_id: string;
  description?: string | null;
  expiry_date?: string | null;
}

/**
 * Build the multipart body.
 *
 * The file goes in as-is; the metadata become form fields rather than a JSON
 * part, because that is the shape FastAPI's `Form(...)` parameters expect. A
 * null is omitted entirely — sending the string "null" would store it.
 */
function toFormData(file: File, fields: Record<string, unknown>): FormData {
  const body = new FormData();
  body.append('file', file);

  for (const [key, value] of Object.entries(fields)) {
    if (value !== null && value !== undefined && value !== '') {
      body.append(key, String(value));
    }
  }

  return body;
}

/** Reports 0–100 as the upload streams. */
export type ProgressHandler = (percent: number) => void;

function uploadConfig(onProgress?: ProgressHandler) {
  return {
    // Let the browser set Content-Type: it has to include the multipart
    // boundary, which we cannot know here.
    headers: { 'Content-Type': undefined },
    onUploadProgress: (event: { loaded: number; total?: number }) => {
      if (!onProgress || !event.total) return;
      onProgress(Math.round((event.loaded / event.total) * 100));
    },
  };
}

export const documentsApi = {
  list: (query: DocumentListQuery): Promise<Page<DocumentRecord>> =>
    api.get<Page<DocumentRecord>>(root, { params: toQueryParams(query) }),

  get: (id: string): Promise<DocumentRecord> => api.get<DocumentRecord>(`${root}/${id}`),

  versions: (id: string): Promise<DocumentVersionRecord[]> =>
    api.get<DocumentVersionRecord[]>(`${root}/${id}/versions`),

  audit: (id: string): Promise<DocumentAuditEntry[]> => api.get<DocumentAuditEntry[]>(`${root}/${id}/audit`),

  dashboard: (): Promise<DocumentDashboardStats> =>
    api.get<DocumentDashboardStats>(endpoints.documents.dashboard),

  upload: (file: File, fields: UploadFields, onProgress?: ProgressHandler): Promise<DocumentRecord> =>
    api.post<DocumentRecord>(root, toFormData(file, { ...fields }), uploadConfig(onProgress)),

  uploadVersion: (
    id: string,
    file: File,
    notes: string | null,
    onProgress?: ProgressHandler,
  ): Promise<DocumentRecord> =>
    api.post<DocumentRecord>(`${root}/${id}/versions`, toFormData(file, { notes }), uploadConfig(onProgress)),

  update: (id: string, values: unknown): Promise<DocumentRecord> =>
    api.patch<DocumentRecord>(`${root}/${id}`, values),

  review: (id: string, values: unknown): Promise<DocumentRecord> =>
    api.post<DocumentRecord>(`${root}/${id}/review`, values),

  archive: (id: string): Promise<DocumentRecord> => api.post<DocumentRecord>(`${root}/${id}/archive`),

  restore: (id: string): Promise<DocumentRecord> => api.post<DocumentRecord>(`${root}/${id}/restore`),

  /**
   * Fetch a version's bytes for display.
   *
   * Goes through the authenticated client rather than pointing an `<img>` or
   * `<iframe>` straight at the URL: the endpoint needs a bearer token, which a
   * browser-initiated request would not carry. The caller is responsible for
   * revoking the object URL.
   */
  previewUrl: async (id: string, versionId?: string): Promise<string> => {
    const response = await apiClient.get<Blob>(`${root}/${id}/preview`, {
      params: versionId ? { version_id: versionId } : undefined,
      responseType: 'blob',
    });
    return URL.createObjectURL(response.data);
  },

  /** Download a version, saving it under the name it was uploaded with. */
  download: async (id: string, filename: string, versionId?: string): Promise<void> => {
    const response = await apiClient.get<Blob>(`${root}/${id}/download`, {
      params: versionId ? { version_id: versionId } : undefined,
      responseType: 'blob',
    });

    const url = URL.createObjectURL(response.data);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  },
};
