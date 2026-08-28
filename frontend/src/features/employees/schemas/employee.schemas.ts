import { z } from 'zod';

import { optionalIdSchema } from '@/features/organization/schemas/organization.schemas';
import {
  mobileSchema,
  optionalDateSchema,
  optionalEmailSchema,
  optionalUrlSchema,
  personNameSchema,
  birthDateSchema,
  genderSchema,
} from '@/features/users/schemas/user.schemas';

/**
 * Client-side validation for the employee forms.
 *
 * Mirrors the server's Pydantic rules so the user gets immediate feedback. The
 * API validates and normalises every request independently -- this is a
 * convenience, never the enforcement point.
 *
 * The person-level rules (name, mobile, date of birth, gender) are imported
 * from the users feature rather than restated: a name means the same thing
 * whichever form it is typed into, and two copies would drift.
 *
 * Every optional field emits an explicit `null` when cleared. `undefined` is
 * dropped by `JSON.stringify`, which silently turns "clear this field" into
 * "leave it alone".
 */

const collapseWhitespace = (value: string): string => value.replace(/\s+/g, ' ').trim();

const stripSeparators = (value: string): string => value.replace(/[\s-]/g, '');

/** Trim, and turn a blank string into null so a set value can be cleared. */
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

/**
 * An optional identifier: trimmed of the separators people type, upper-cased,
 * and shape-checked. Blank becomes null.
 */
const optionalIdentifierSchema = (pattern: RegExp, message: string) =>
  z
    .string()
    .optional()
    .transform((value) => {
      const cleaned = value ? stripSeparators(value).toUpperCase() : '';
      return cleaned ? cleaned : null;
    })
    .refine((value) => value === null || pattern.test(value), message);

// ---------------------------------------------------------------------------
// Statutory identifiers -- the same shapes the server enforces
// ---------------------------------------------------------------------------
export const aadhaarSchema = optionalIdentifierSchema(
  /^[2-9][0-9]{11}$/,
  'Aadhaar must be 12 digits and cannot start with 0 or 1',
);

export const panSchema = optionalIdentifierSchema(
  /^[A-Z]{5}[0-9]{4}[A-Z]$/,
  'PAN must be 5 letters, 4 digits and a letter, for example ABCDE1234F',
);

export const passportSchema = optionalIdentifierSchema(
  /^[A-Z0-9]{6,20}$/,
  'Passport number must be 6 to 20 letters or digits',
);

export const drivingLicenseSchema = z
  .string()
  .optional()
  .transform((value) => {
    const cleaned = value ? collapseWhitespace(value).toUpperCase() : '';
    return cleaned ? cleaned : null;
  })
  .refine(
    (value) => value === null || /^[A-Z0-9\- ]{6,25}$/.test(value),
    'Driving licence number may contain only letters, digits, spaces and hyphens',
  );

export const uanSchema = optionalIdentifierSchema(/^[0-9]{12}$/, 'UAN must be exactly 12 digits');

export const esiSchema = optionalIdentifierSchema(/^[0-9]{17}$/, 'ESI number must be exactly 17 digits');

export const pfSchema = optionalIdentifierSchema(
  /^[A-Z0-9/-]{5,30}$/,
  'PF number may contain only letters, digits, slashes and hyphens',
);

export const ifscSchema = z
  .string()
  .transform((value) => stripSeparators(value).toUpperCase())
  .pipe(
    z
      .string()
      .regex(
        /^[A-Z]{4}0[A-Z0-9]{6}$/,
        'IFSC must be 4 letters, a zero and 6 alphanumeric characters, for example HDFC0001234',
      ),
  );

export const accountNumberSchema = z
  .string()
  .transform((value) => stripSeparators(value).toUpperCase())
  .pipe(
    z
      .string()
      .min(6, 'Account number must be at least 6 characters')
      .max(34, 'Account number must be at most 34 characters')
      .regex(/^[A-Z0-9]+$/, 'Account number may contain only letters and digits'),
  );

// ---------------------------------------------------------------------------
// Employee fields
// ---------------------------------------------------------------------------
export const officialEmailSchema = z
  .string()
  .trim()
  .min(1, 'Official email is required')
  .email('Enter a valid email address')
  .toLowerCase();

/**
 * Required, unlike most dates here. Future dates are allowed within a year:
 * pre-boarding someone before their start date is the normal case, while a date
 * further out is almost always a mistyped year.
 */
export const joiningDateSchema = z
  .string()
  .min(1, 'Joining date is required')
  .refine((value) => !Number.isNaN(new Date(value).getTime()), 'Enter a valid date')
  .refine((value) => new Date(value).getFullYear() >= 1950, 'Check the year')
  .refine((value) => {
    const limit = new Date();
    limit.setFullYear(limit.getFullYear() + 1);
    return new Date(value) <= limit;
  }, 'Joining date cannot be more than a year in the future');

export const employmentStatusSchema = z.enum([
  'probation',
  'confirmed',
  'active',
  'notice_period',
  'resigned',
  'inactive',
]);

export const workModeSchema = z
  .enum(['office', 'remote', 'hybrid'])
  .optional()
  .transform((value) => value ?? null);

export const maritalStatusSchema = z
  .enum(['single', 'married', 'divorced', 'widowed', 'separated'])
  .optional()
  .transform((value) => value ?? null);

export const bloodGroupSchema = z
  .enum(['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-'])
  .optional()
  .transform((value) => value ?? null);

/**
 * CTC as a decimal string. Sent as a string rather than a number so the value
 * survives the round trip without a float turning 1450000.10 into .09999.
 */
export const ctcSchema = z
  .string()
  .optional()
  .transform((value) => {
    const trimmed = value?.replace(/[,\s]/g, '').trim();
    return trimmed ? trimmed : null;
  })
  .refine(
    (value) => value === null || (/^\d+(\.\d{1,2})?$/.test(value) && Number(value) >= 0),
    'Enter an amount, for example 1450000 or 1450000.50',
  );

export const postalCodeSchema = z
  .string()
  .transform((value) => collapseWhitespace(value).toUpperCase())
  .pipe(
    z
      .string()
      .min(2, 'Postal code is required')
      .max(20, 'Postal code must be at most 20 characters')
      .regex(/^[A-Z0-9][A-Z0-9 -]{1,18}$/, 'Enter a valid postal code'),
  );

const requiredPlaceSchema = (label: string) =>
  z
    .string()
    .transform(collapseWhitespace)
    .pipe(z.string().min(1, `${label} is required`).max(100, 'Must be at most 100 characters'));

const requiredTextSchema = (label: string, min = 2, max = 150) =>
  z
    .string()
    .transform(collapseWhitespace)
    .pipe(
      z
        .string()
        .min(min, `${label} is required`)
        .max(max, `Must be at most ${String(max)} characters`),
    );

// ---------------------------------------------------------------------------
// Form schemas
// ---------------------------------------------------------------------------
const personalFields = {
  first_name: personNameSchema,
  last_name: personNameSchema,
  gender: genderSchema,
  date_of_birth: birthDateSchema,
  blood_group: bloodGroupSchema,
  marital_status: maritalStatusSchema,
  nationality: optionalTextSchema(100, 'Nationality'),
  photo_url: optionalUrlSchema,
};

const contactFields = {
  personal_email: optionalEmailSchema,
  mobile_number: mobileSchema,
  alternate_number: mobileSchema,
  emergency_contact_name: optionalTextSchema(150, 'Emergency contact name'),
  emergency_contact_number: mobileSchema,
  emergency_contact_relationship: optionalTextSchema(50, 'Relationship'),
};

const officialFields = {
  official_email: officialEmailSchema,
  official_mobile: mobileSchema,
  extension_number: optionalTextSchema(20, 'Extension'),
  work_mode: workModeSchema,
};

const employmentFields = {
  joining_date: joiningDateSchema,
  employment_type_id: optionalIdSchema,
  business_unit_id: optionalIdSchema,
  team_id: optionalIdSchema,
  designation_id: optionalIdSchema,
  grade_id: optionalIdSchema,
  work_location_id: optionalIdSchema,
  reporting_manager_id: optionalIdSchema,
  user_id: optionalIdSchema,
};

const compensationFields = {
  ctc: ctcSchema,
  salary_grade_id: optionalIdSchema,
};

export const addressSchema = z.object({
  address_type: z.enum(['current', 'permanent']),
  address_line1: requiredTextSchema('Address line 1', 3, 255),
  address_line2: optionalTextSchema(255, 'Address line 2'),
  landmark: optionalTextSchema(150, 'Landmark'),
  city: requiredPlaceSchema('City'),
  state: requiredPlaceSchema('State'),
  country: requiredPlaceSchema('Country'),
  postal_code: postalCodeSchema,
});

export const bankDetailSchema = z.object({
  bank_name: requiredTextSchema('Bank name'),
  account_number: accountNumberSchema,
  account_holder_name: optionalTextSchema(150, 'Account holder name'),
  ifsc_code: ifscSchema,
  branch_name: requiredTextSchema('Branch name'),
});

export const identificationSchema = z.object({
  aadhaar_number: aadhaarSchema,
  pan_number: panSchema,
  passport_number: passportSchema,
  passport_expiry: optionalDateSchema,
  driving_license_number: drivingLicenseSchema,
  uan_number: uanSchema,
  pf_number: pfSchema,
  esi_number: esiSchema,
});

export const createEmployeeSchema = z.object({
  ...personalFields,
  ...contactFields,
  ...officialFields,
  ...employmentFields,
  ...compensationFields,
  employment_status: employmentStatusSchema,
  notes: optionalTextSchema(5000, 'Notes'),
});

/**
 * The edit form carries the same fields plus a reason.
 *
 * Changing the team, designation, grade, manager, location or status here
 * writes an employment-history row, so the reason is worth capturing at the
 * point the change is made rather than reconstructing it later.
 */
export const editEmployeeSchema = createEmployeeSchema.extend({
  change_reason: optionalTextSchema(500, 'Reason'),
});

// ---------------------------------------------------------------------------
// Lifecycle action schemas
// ---------------------------------------------------------------------------
const lifecycleBase = {
  effective_date: z.string().min(1, 'Effective date is required'),
  reason: optionalTextSchema(500, 'Reason'),
  notes: optionalTextSchema(5000, 'Notes'),
};

export const confirmEmployeeSchema = z.object(lifecycleBase);

export const transferTeamSchema = z.object({
  ...lifecycleBase,
  team_id: z.string().uuid('Select a team'),
  business_unit_id: optionalIdSchema,
});

export const changeDesignationSchema = z.object({
  ...lifecycleBase,
  designation_id: z.string().uuid('Select a designation'),
  grade_id: optionalIdSchema,
});

export const changeManagerSchema = z.object({
  ...lifecycleBase,
  reporting_manager_id: optionalIdSchema,
});

export const changeStatusSchema = z.object({
  ...lifecycleBase,
  employment_status: employmentStatusSchema,
});

export const promoteEmployeeSchema = z
  .object({
    ...lifecycleBase,
    designation_id: optionalIdSchema,
    grade_id: optionalIdSchema,
    salary_grade_id: optionalIdSchema,
    ctc: ctcSchema,
  })
  .refine(
    (values) => Boolean(values.designation_id ?? values.grade_id ?? values.salary_grade_id ?? values.ctc),
    {
      message: 'A promotion must change at least one of designation, grade, salary grade or CTC',
      path: ['designation_id'],
    },
  );

export type CreateEmployeeValues = z.input<typeof createEmployeeSchema>;
export type EditEmployeeValues = z.input<typeof editEmployeeSchema>;
export type AddressValues = z.input<typeof addressSchema>;
export type BankDetailValues = z.input<typeof bankDetailSchema>;
export type IdentificationValues = z.input<typeof identificationSchema>;
export type ConfirmEmployeeValues = z.input<typeof confirmEmployeeSchema>;
export type TransferTeamValues = z.input<typeof transferTeamSchema>;
export type ChangeDesignationValues = z.input<typeof changeDesignationSchema>;
export type ChangeManagerValues = z.input<typeof changeManagerSchema>;
export type ChangeStatusValues = z.input<typeof changeStatusSchema>;
export type PromoteEmployeeValues = z.input<typeof promoteEmployeeSchema>;
