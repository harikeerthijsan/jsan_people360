import { z } from 'zod';

/**
 * Client-side validation for the master-data forms.
 *
 * These mirror the backend's Pydantic rules so the user gets immediate
 * feedback, but they are a convenience, never the enforcement point -- the API
 * validates and normalises every request independently.
 */

// ---------------------------------------------------------------------------
// Shared field schemas
// ---------------------------------------------------------------------------

/** Trim and collapse internal whitespace, exactly as the API does. */
const collapseWhitespace = (value: string): string => value.replace(/\s+/g, ' ').trim();

export const masterNameSchema = z
  .string()
  .transform(collapseWhitespace)
  .pipe(
    z.string().min(2, 'Name must be at least 2 characters').max(150, 'Name must be at most 150 characters'),
  );

export const masterCodeSchema = z
  .string()
  .transform((value) => collapseWhitespace(value).toUpperCase().replace(/ /g, '_'))
  .pipe(
    z
      .string()
      .min(2, 'Code must be at least 2 characters')
      .max(50, 'Code must be at most 50 characters')
      .regex(
        /^[A-Z0-9][A-Z0-9_-]*$/,
        'Code must start with a letter or digit and contain only letters, digits, hyphens and underscores',
      ),
  );

/**
 * Optional free text. Blank becomes `null`, deliberately **not** `undefined`.
 *
 * `JSON.stringify` drops `undefined` properties, so an omitted key never reaches
 * the API. The server applies `exclude_unset`, sees no `description`, and leaves
 * the column untouched — meaning a user could never clear a field they had
 * already filled in. Sending an explicit `null` is what makes "clear this" work.
 */
export const optionalTextSchema = (max = 2000) =>
  z
    .string()
    .max(max, `Must be at most ${String(max)} characters`)
    .optional()
    .transform((value) => {
      const trimmed = value?.trim();
      return trimmed ? trimmed : null;
    });

export const statusSchema = z.enum(['active', 'inactive']);

export const requiredIdSchema = (label: string) =>
  z.string().min(1, `${label} is required`).uuid(`${label} is not a valid selection`);

/** An optional reference. Cleared becomes `null` so the server unassigns it. */
export const optionalIdSchema = z
  .string()
  .optional()
  .transform((value) => (value && value.length > 0 ? value : null))
  .refine(
    (value) =>
      value === null || /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value),
    'Not a valid selection',
  );

export const levelSchema = z
  .number({ message: 'Level is required' })
  .int('Level must be a whole number')
  .min(1, 'Level must be at least 1')
  .max(99, 'Level must be at most 99');

export const placeSchema = (label: string) =>
  z
    .string()
    .transform(collapseWhitespace)
    .pipe(z.string().min(1, `${label} is required`).max(100, `${label} is too long`));

export const timezoneSchema = z
  .string()
  .min(1, 'Time zone is required')
  .refine(
    // `SUPPORTED_TIMEZONES` is a readonly tuple of literals, so its `includes`
    // only accepts those literals. Widening to `readonly string[]` lets an
    // arbitrary input be checked against it.
    (value) => (SUPPORTED_TIMEZONES as readonly string[]).includes(value),
    'Select a supported time zone',
  );

export const currencySchema = z
  .string()
  .transform((value) => value.trim().toUpperCase())
  .pipe(z.string().regex(/^[A-Z]{3}$/, 'Use a three-letter ISO 4217 code, for example INR'));

/** Matches the backend's shape check. Neither is verified with the issuer. */
export const gstSchema = z
  .string()
  .optional()
  .transform((value) => {
    const trimmed = value?.trim().toUpperCase();
    return trimmed ? trimmed : null;
  })
  .refine(
    (value) => value === null || /^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z][0-9A-Z]Z[0-9A-Z]$/.test(value),
    'Enter a valid 15-character GSTIN',
  );

export const panSchema = z
  .string()
  .optional()
  .transform((value) => {
    const trimmed = value?.trim().toUpperCase();
    return trimmed ? trimmed : null;
  })
  .refine(
    (value) => value === null || /^[A-Z]{5}[0-9]{4}[A-Z]$/.test(value),
    'Enter a valid PAN, for example ABCDE1234F',
  );

export const optionalUrlSchema = z
  .string()
  .optional()
  .transform((value) => {
    const trimmed = value?.trim();
    return trimmed ? trimmed : null;
  })
  .refine((value) => {
    if (value === null) return true;
    try {
      const parsed = new URL(value);
      return parsed.protocol === 'http:' || parsed.protocol === 'https:';
    } catch {
      return false;
    }
  }, 'Enter a full URL including https://');

/**
 * Time zones offered in the UI.
 *
 * A curated list rather than the full IANA database: a 400-entry dropdown is
 * unusable, and the server validates against the complete set anyway, so a
 * deployment needing another zone can add it here without a backend change.
 */
export const SUPPORTED_TIMEZONES = [
  'Asia/Kolkata',
  'Asia/Dubai',
  'Asia/Singapore',
  'Asia/Tokyo',
  'Australia/Sydney',
  'Europe/London',
  'Europe/Berlin',
  'Europe/Paris',
  'America/New_York',
  'America/Chicago',
  'America/Denver',
  'America/Los_Angeles',
  'America/Sao_Paulo',
  'Africa/Johannesburg',
  'UTC',
] as const;

/** Currencies offered in the UI; the server accepts any ISO 4217 code. */
export const SUPPORTED_CURRENCIES = ['INR', 'USD', 'EUR', 'GBP', 'AED', 'SGD', 'AUD', 'CAD'] as const;

// ---------------------------------------------------------------------------
// Per-master schemas
// ---------------------------------------------------------------------------
const namedMasterFields = {
  name: masterNameSchema,
  description: optionalTextSchema(),
  status: statusSchema,
};

const codedMasterFields = {
  ...namedMasterFields,
  code: masterCodeSchema,
};

export const businessUnitSchema = z.object(codedMasterFields);

export const teamSchema = z.object({
  ...namedMasterFields,
  business_unit_id: requiredIdSchema('Business unit'),
  manager_id: optionalIdSchema,
});

export const designationSchema = z.object({
  ...codedMasterFields,
  business_unit_id: requiredIdSchema('Business unit'),
  level: levelSchema,
});

export const gradeSchema = z.object({
  ...codedMasterFields,
  level: levelSchema,
});

export const locationSchema = z.object({
  ...codedMasterFields,
  country: placeSchema('Country'),
  state: placeSchema('State'),
  city: placeSchema('City'),
  address: z.string().min(5, 'Address must be at least 5 characters').max(1000, 'Address is too long'),
  timezone: timezoneSchema,
});

export const employmentTypeSchema = z.object(codedMasterFields);

export const organizationSchema = z.object({
  ...namedMasterFields,
  legal_name: z
    .string()
    .transform(collapseWhitespace)
    .pipe(z.string().min(2, 'Legal name is required').max(250, 'Legal name is too long')),
  registration_number: z
    .string()
    .transform(collapseWhitespace)
    .pipe(z.string().min(2, 'Registration number is required').max(100, 'Registration number is too long')),
  gst_number: gstSchema,
  pan_number: panSchema,
  website: optionalUrlSchema,
  logo_url: optionalUrlSchema,
  timezone: timezoneSchema,
  currency: currencySchema,
  address_line1: z.string().min(3, 'Address is required').max(255, 'Address is too long'),
  address_line2: optionalTextSchema(255),
  city: placeSchema('City'),
  state: placeSchema('State'),
  country: placeSchema('Country'),
  postal_code: optionalTextSchema(20),
});
