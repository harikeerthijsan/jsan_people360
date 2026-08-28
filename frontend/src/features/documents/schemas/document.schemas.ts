import { z } from 'zod';

import {
  ACCEPTED_EXTENSIONS,
  MAX_UPLOAD_MB,
  type DocumentStatus,
} from '@/features/documents/types/document.types';

/**
 * Client-side validation for the document forms.
 *
 * Mirrors the server's rules so the user gets immediate feedback on a file that
 * is obviously wrong, rather than after a round trip carrying several megabytes.
 *
 * It is a convenience and nothing more. The server re-validates every upload
 * against the file's own content signature — the only check that can tell a PDF
 * from an executable that has been renamed — and this code cannot do that.
 */

const MAX_BYTES = MAX_UPLOAD_MB * 1024 * 1024;

const collapseWhitespace = (value: string): string => value.replace(/\s+/g, ' ').trim();

const optionalTextSchema = (max: number, label = 'Value') =>
  z
    .string()
    .optional()
    .transform((value) => {
      const trimmed = value ? collapseWhitespace(value) : '';
      return trimmed ? trimmed : null;
    })
    .refine(
      (value) => value === null || value.length <= max,
      `${label} must be at most ${String(max)} characters`,
    );

/** Everything after the final dot, lower-cased and including it. */
export function extensionOf(filename: string): string {
  const index = filename.lastIndexOf('.');
  return index === -1 ? '' : filename.slice(index).toLowerCase();
}

export interface FileRejection {
  /** Shown to the user, so it says what to do rather than what happened. */
  message: string;
}

/**
 * Check one file before it is sent.
 *
 * Returns `null` when the file passes. Deliberately not a Zod schema: `File` is
 * a browser type with no useful Zod representation, and the drag-and-drop
 * surface needs to reject a file the moment it lands rather than at submit.
 */
export function validateFile(file: File): FileRejection | null {
  if (file.size === 0) {
    return { message: `${file.name} is empty.` };
  }

  if (file.size > MAX_BYTES) {
    return {
      message: `${file.name} is larger than the ${String(MAX_UPLOAD_MB)} MB limit.`,
    };
  }

  const extension = extensionOf(file.name);
  if (!ACCEPTED_EXTENSIONS.includes(extension)) {
    return {
      message: `${file.name} is not an accepted type. Upload a ${ACCEPTED_EXTENSIONS.join(', ')} file.`,
    };
  }

  return null;
}

// ---------------------------------------------------------------------------
// Form schemas
// ---------------------------------------------------------------------------
export const documentNameSchema = z
  .string()
  .transform(collapseWhitespace)
  .pipe(z.string().min(2, 'Give the document a name').max(200, 'Name must be at most 200 characters'));

export const ownerTypeSchema = z.enum(['employee', 'candidate', 'organization', 'user']);

/** Optional, and cleared with an explicit null so the server can unset it. */
export const optionalDateSchema = z
  .string()
  .optional()
  .transform((value) => {
    const trimmed = value?.trim();
    return trimmed ? trimmed : null;
  });

export const uploadDocumentSchema = z.object({
  name: documentNameSchema,
  category_id: z.string().uuid('Choose a category'),
  document_type_id: z.string().uuid('Choose a document type'),
  owner_type: ownerTypeSchema,
  owner_id: z.string().uuid('Choose who this document belongs to'),
  description: optionalTextSchema(2000, 'Description'),
  expiry_date: optionalDateSchema,
});

/** Metadata only. The file is changed by uploading a new version. */
export const editDocumentSchema = z.object({
  name: documentNameSchema,
  description: optionalTextSchema(2000, 'Description'),
  category_id: z.string().uuid('Choose a category'),
  document_type_id: z.string().uuid('Choose a document type'),
  expiry_date: optionalDateSchema,
});

export const newVersionSchema = z.object({
  notes: optionalTextSchema(1000, 'Notes'),
});

export const reviewDocumentSchema = z.object({
  status: z.enum(['under_review', 'approved', 'rejected']),
  review_notes: optionalTextSchema(2000, 'Notes'),
});

export const documentCategorySchema = z.object({
  name: z
    .string()
    .transform(collapseWhitespace)
    .pipe(z.string().min(2, 'Name is required').max(150, 'Name must be at most 150 characters')),
  code: z
    .string()
    .transform((value) => collapseWhitespace(value).toUpperCase().replace(/ /g, '_'))
    .pipe(
      z
        .string()
        .min(2, 'Code is required')
        .max(50, 'Code must be at most 50 characters')
        .regex(
          /^[A-Z0-9][A-Z0-9_-]*$/,
          'Code must start with a letter or digit and contain only letters, digits, hyphens and underscores',
        ),
    ),
  description: optionalTextSchema(2000, 'Description'),
  display_order: z.coerce.number().int().min(1).max(999),
  status: z.enum(['active', 'inactive']),
});

export const documentTypeSchema = documentCategorySchema.omit({ display_order: true }).extend({
  category_id: z.string().uuid('Choose a category'),
  requires_expiry: z.boolean(),
  is_sensitive: z.boolean(),
  allowed_extensions: z
    .string()
    .optional()
    .transform((value) => {
      const extensions = (value ?? '')
        .split(',')
        .map((item) => item.trim().toLowerCase())
        .filter(Boolean)
        .map((item) => (item.startsWith('.') ? item : `.${item}`));
      return extensions.length > 0 ? [...new Set(extensions)].sort().join(',') : null;
    })
    .refine(
      (value) =>
        value === null ||
        value.split(',').every((item) => ACCEPTED_EXTENSIONS.some((allowed) => allowed === item)),
      `Allowed extensions must be a subset of ${ACCEPTED_EXTENSIONS.join(', ')}`,
    ),
});

export type UploadDocumentValues = z.input<typeof uploadDocumentSchema>;
export type EditDocumentValues = z.input<typeof editDocumentSchema>;
export type NewVersionValues = z.input<typeof newVersionSchema>;
export type ReviewDocumentValues = z.input<typeof reviewDocumentSchema>;
export type DocumentCategoryValues = z.input<typeof documentCategorySchema>;

/** The subset of statuses a reviewer may choose. */
export const REVIEW_STATUS_OPTIONS: { value: DocumentStatus; label: string }[] = [
  { value: 'under_review', label: 'Under review' },
  { value: 'approved', label: 'Approved' },
  { value: 'rejected', label: 'Rejected' },
];
