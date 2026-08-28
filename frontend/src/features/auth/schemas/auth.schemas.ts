import { z } from 'zod';

/**
 * Client-side validation rules.
 *
 * These mirror the backend's Pydantic rules so the user gets instant feedback,
 * but they are a convenience, never the enforcement point -- the API validates
 * every request independently.
 */

const PASSWORD_MIN_LENGTH = 10;
const PASSWORD_MAX_LENGTH = 72; // bcrypt truncates beyond 72 bytes.

/**
 * Order matters: trim *before* validating.
 *
 * Users routinely paste an address with a trailing space, and validating first
 * would reject a perfectly good email. `.trim()` and `.toLowerCase()` are Zod
 * string transforms, so the schema's input and output types both stay `string`.
 */
export const emailSchema = z
  .string()
  .trim()
  .min(1, 'Email address is required')
  .email('Enter a valid email address')
  .toLowerCase();

/** Matches the backend policy: length plus four character classes. */
export const strongPasswordSchema = z
  .string()
  .min(PASSWORD_MIN_LENGTH, `Password must be at least ${String(PASSWORD_MIN_LENGTH)} characters`)
  .max(PASSWORD_MAX_LENGTH, `Password must be at most ${String(PASSWORD_MAX_LENGTH)} characters`)
  .regex(/[a-z]/, 'Password must contain a lowercase letter')
  .regex(/[A-Z]/, 'Password must contain an uppercase letter')
  .regex(/\d/, 'Password must contain a digit')
  .regex(/[^A-Za-z0-9]/, 'Password must contain a special character');

export const loginSchema = z.object({
  email: emailSchema,
  // Deliberately not `strongPasswordSchema`: an existing password predating a
  // policy change must still be usable to sign in.
  password: z.string().min(1, 'Password is required').max(128, 'Password is too long'),
  // The default is supplied by the form's `defaultValues` rather than
  // `z.boolean().default(false)`. A Zod default makes the schema's input and
  // output types diverge, which React Hook Form's resolver cannot reconcile.
  remember_me: z.boolean(),
});

export const forgotPasswordSchema = z.object({
  email: emailSchema,
});

export const resetPasswordSchema = z
  .object({
    token: z.string().min(1, 'The reset link is missing its token'),
    new_password: strongPasswordSchema,
    confirm_password: z.string().min(1, 'Confirm your new password'),
  })
  .refine((values) => values.new_password === values.confirm_password, {
    message: 'Passwords do not match',
    path: ['confirm_password'],
  });

export const changePasswordSchema = z
  .object({
    current_password: z.string().min(1, 'Your current password is required'),
    new_password: strongPasswordSchema,
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

export const profileSchema = z.object({
  full_name: z
    .string()
    .min(2, 'Enter your full name')
    .max(255, 'Name is too long')
    .transform((value) => value.replace(/\s+/g, ' ').trim()),
  job_title: z.string().max(150, 'Job title is too long').optional(),
  phone_number: z.string().max(32, 'Phone number is too long').optional(),
});

export type LoginFormValues = z.infer<typeof loginSchema>;
/** What is sent to the API. Identical to the form values by design. */
export type LoginPayload = LoginFormValues;
export type ForgotPasswordFormValues = z.infer<typeof forgotPasswordSchema>;
export type ResetPasswordFormValues = z.infer<typeof resetPasswordSchema>;
export type ChangePasswordFormValues = z.infer<typeof changePasswordSchema>;
export type ProfileFormValues = z.input<typeof profileSchema>;
