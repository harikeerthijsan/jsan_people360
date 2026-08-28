import { z } from 'zod';

import { optionalIdSchema, statusSchema } from '@/features/organization/schemas/organization.schemas';

/**
 * Client-side validation for the user forms.
 *
 * Mirrors the server's Pydantic rules so the user gets immediate feedback. The
 * API validates and normalises every request independently -- this is a
 * convenience, never the enforcement point.
 */

const collapseWhitespace = (value: string): string => value.replace(/\s+/g, ' ').trim();

/** Matches the server: 8+ characters with four character classes. */
export const PASSWORD_MIN_LENGTH = 8;

export const passwordSchema = z
  .string()
  .min(PASSWORD_MIN_LENGTH, `Password must be at least ${String(PASSWORD_MIN_LENGTH)} characters`)
  .max(72, 'Password must be at most 72 characters')
  .regex(/[a-z]/, 'Password must contain a lowercase letter')
  .regex(/[A-Z]/, 'Password must contain an uppercase letter')
  .regex(/\d/, 'Password must contain a digit')
  .regex(/[^A-Za-z0-9]/, 'Password must contain a special character');

export const personNameSchema = z
  .string()
  .transform(collapseWhitespace)
  .pipe(z.string().min(1, 'Required').max(100, 'Must be at most 100 characters'));

export const usernameSchema = z
  .string()
  .transform((value) => collapseWhitespace(value).toLowerCase().replace(/ /g, '.'))
  .pipe(
    z
      .string()
      .min(3, 'Username must be at least 3 characters')
      .max(50, 'Username must be at most 50 characters')
      .regex(
        /^[a-z0-9][a-z0-9._-]*$/,
        'Username must start with a letter or digit and contain only letters, digits, dots, hyphens and underscores',
      ),
  );

export const officialEmailSchema = z
  .string()
  .trim()
  .min(1, 'Official email is required')
  .email('Enter a valid email address')
  .toLowerCase();

/** Optional, and cleared with an explicit null so the server can unset it. */
export const optionalEmailSchema = z
  .string()
  .optional()
  .transform((value) => {
    const trimmed = value?.trim().toLowerCase();
    return trimmed ? trimmed : null;
  })
  .refine(
    (value) => value === null || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value),
    'Enter a valid email address',
  );

/**
 * Deliberately permissive, matching the server: it accepts the international
 * formats people actually type while rejecting free text.
 */
export const mobileSchema = z
  .string()
  .optional()
  .transform((value) => {
    const trimmed = value?.replace(/\s+/g, ' ').trim();
    return trimmed ? trimmed : null;
  })
  .refine(
    (value) => value === null || /^\+?[0-9][0-9 ()\-]{6,20}$/.test(value),
    'Enter a valid mobile number, for example +91 98765 43210',
  );

export const genderSchema = z
  .enum(['male', 'female', 'other', 'prefer_not_to_say'])
  .optional()
  .transform((value) => value ?? null);

/** An optional date. Blank becomes null so a set value can be cleared. */
export const optionalDateSchema = z
  .string()
  .optional()
  .transform((value) => {
    const trimmed = value?.trim();
    return trimmed ? trimmed : null;
  });

export const birthDateSchema = optionalDateSchema.refine((value) => {
  if (value === null) return true;

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return false;

  const today = new Date();
  if (parsed > today) return false;

  const age = today.getFullYear() - parsed.getFullYear();
  return age >= 14 && age <= 100;
}, 'Enter a realistic date of birth');

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

// ---------------------------------------------------------------------------
// Form schemas
// ---------------------------------------------------------------------------
const identityFields = {
  first_name: personNameSchema,
  last_name: personNameSchema,
  username: usernameSchema,
  email: officialEmailSchema,
  personal_email: optionalEmailSchema,
  phone_number: mobileSchema,
  gender: genderSchema,
  date_of_birth: birthDateSchema,
  avatar_url: optionalUrlSchema,
};

const organizationFields = {
  business_unit_id: optionalIdSchema,
  team_id: optionalIdSchema,
  designation_id: optionalIdSchema,
  grade_id: optionalIdSchema,
  location_id: optionalIdSchema,
  employment_type_id: optionalIdSchema,
  joining_date: optionalDateSchema,
};

export const createUserSchema = z.object({
  ...identityFields,
  ...organizationFields,
  status: statusSchema,
  password: passwordSchema,
  force_password_change: z.boolean(),
});

/**
 * The edit form omits the password entirely.
 *
 * Setting someone else's password is a separate, separately audited action, and
 * the API rejects a password on this endpoint.
 */
export const editUserSchema = z.object({
  ...identityFields,
  ...organizationFields,
  status: statusSchema,
});

/** What a user may change about themselves. */
export const profileSchema = z.object({
  personal_email: optionalEmailSchema,
  phone_number: mobileSchema,
  avatar_url: optionalUrlSchema,
});

export const resetPasswordSchema = z
  .object({
    new_password: passwordSchema,
    confirm_password: z.string().min(1, 'Confirm the new password'),
    force_password_change: z.boolean(),
    revoke_sessions: z.boolean(),
  })
  .refine((values) => values.new_password === values.confirm_password, {
    message: 'Passwords do not match',
    path: ['confirm_password'],
  });

export const changeOwnPasswordSchema = z
  .object({
    current_password: z.string().min(1, 'Your current password is required'),
    new_password: passwordSchema,
    confirm_password: z.string().min(1, 'Confirm your new password'),
  })
  .refine((values) => values.new_password === values.confirm_password, {
    message: 'Passwords do not match',
    path: ['confirm_password'],
  })
  .refine((values) => values.current_password !== values.new_password, {
    message: 'Your new password must be different from the current one',
    path: ['new_password'],
  });

export type CreateUserValues = z.input<typeof createUserSchema>;
export type EditUserValues = z.input<typeof editUserSchema>;
export type ProfileValues = z.input<typeof profileSchema>;
export type ResetPasswordValues = z.input<typeof resetPasswordSchema>;
