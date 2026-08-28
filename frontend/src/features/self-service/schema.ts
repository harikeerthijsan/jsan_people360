import { z } from 'zod';

/**
 * Client-side validation for the employee portal.
 *
 * Mirrors the server so a typo is caught before a round trip, and no further:
 * how many leave days are left, whether this week is locked, whether a project
 * allocation covered a given date -- all of those need to see other rows, and
 * are enforced by the API alone.
 *
 * Nothing here validates an employee id, because none of these forms has one.
 */

const requiredText = (label: string, max: number, min = 3) =>
  z
    .string()
    .transform((value) => value.replace(/\s+/g, ' ').trim())
    .pipe(
      z
        .string()
        .min(min, `${label} is required`)
        .max(max, `${label} must be at most ${String(max)} characters`),
    );

const optionalText = (max: number, label = 'Value') =>
  z
    .string()
    .optional()
    .transform((value) => {
      const trimmed = value?.replace(/\s+/g, ' ').trim() ?? '';
      return trimmed ? trimmed : null;
    })
    .refine(
      (value) => value === null || value.length <= max,
      `${label} must be at most ${String(max)} characters`,
    );

const isoDate = z.string().min(1, 'Required');
const id = z.string().uuid('Select an option');

const optionalId = z
  .string()
  .optional()
  .transform((value) => (value ? value : null));

/** An optional phone number: blank means "leave it unset", not "clear it". */
const optionalPhone = (label: string) =>
  z
    .string()
    .optional()
    .transform((value) => value?.trim() ?? '')
    .refine((value) => value === '' || /^[+\d][\d\s()-]{5,}$/.test(value), `${label} is not a valid number`)
    .transform((value) => (value === '' ? null : value));

export const MAX_DAILY_HOURS = 24;

// ---------------------------------------------------------------------------
// Attendance
// ---------------------------------------------------------------------------
export const checkInSchema = z.object({
  work_mode: z.enum(['office', 'remote', 'hybrid', 'client_site']),
  notes: optionalText(1000, 'Notes'),
});

export type CheckInFormValues = z.input<typeof checkInSchema>;

export const checkOutSchema = z.object({
  notes: optionalText(1000, 'Notes'),
});

export type CheckOutFormValues = z.input<typeof checkOutSchema>;

export const myRegularizationSchema = z
  .object({
    attendance_date: isoDate,
    requested_check_in_at: z.string().optional(),
    requested_check_out_at: z.string().optional(),
    reason: requiredText('Reason', 2000, 5),
    supporting_document_id: optionalId,
  })
  .superRefine((values, context) => {
    if (!values.requested_check_in_at && !values.requested_check_out_at) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['requested_check_in_at'],
        message: 'Give the check-in time, the check-out time, or both',
      });
    }
    if (
      values.requested_check_in_at &&
      values.requested_check_out_at &&
      values.requested_check_out_at <= values.requested_check_in_at
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['requested_check_out_at'],
        message: 'Check-out must be after check-in',
      });
    }
  });

export type MyRegularizationFormValues = z.input<typeof myRegularizationSchema>;

// ---------------------------------------------------------------------------
// Leave
// ---------------------------------------------------------------------------
export const myLeaveApplySchema = z
  .object({
    leave_type_id: id,
    from_date: isoDate,
    to_date: isoDate,
    day_part: z.enum(['full_day', 'first_half', 'second_half']),
    reason: requiredText('Reason', 2000),
    supporting_document_id: optionalId,
  })
  .superRefine((values, context) => {
    if (values.to_date < values.from_date) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['to_date'],
        message: 'Leave cannot end before it starts',
      });
    }
    if (values.day_part !== 'full_day' && values.from_date !== values.to_date) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['day_part'],
        message: 'A half day applies to a single date',
      });
    }
  });

export type MyLeaveApplyFormValues = z.input<typeof myLeaveApplySchema>;

// ---------------------------------------------------------------------------
// Timesheets
// ---------------------------------------------------------------------------
export const myTimesheetSchema = z
  .object({
    week_start_date: isoDate,
    entries: z.array(
      z.object({
        project_id: id,
        work_date: isoDate,
        task: requiredText('Task', 200, 2),
        hours: z
          .string()
          .min(1, 'Hours are required')
          .regex(/^\d+(\.\d{1,2})?$/, 'Hours must be a number')
          .refine((value) => Number(value) > 0, 'Hours must be more than zero')
          .refine(
            (value) => Number(value) <= MAX_DAILY_HOURS,
            `Hours must be at most ${String(MAX_DAILY_HOURS)}`,
          ),
        billable: z.boolean(),
        comments: optionalText(1000, 'Comments'),
      }),
    ),
  })
  .superRefine((values, context) => {
    const weekStart = new Date(`${values.week_start_date}T00:00:00`);
    const weekEnd = new Date(weekStart);
    weekEnd.setDate(weekEnd.getDate() + 6);
    const lastDay = weekEnd.toISOString().slice(0, 10);

    const hoursPerDay = new Map<string, number>();
    const seen = new Set<string>();

    values.entries.forEach((entry, index) => {
      if (entry.work_date < values.week_start_date || entry.work_date > lastDay) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['entries', index, 'work_date'],
          message: 'This date is outside the week',
        });
      }

      const key = `${entry.work_date}|${entry.project_id}|${entry.task.trim().toLowerCase()}`;
      if (seen.has(key)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['entries', index, 'task'],
          message: 'This task is already booked on that day',
        });
      }
      seen.add(key);

      const running = (hoursPerDay.get(entry.work_date) ?? 0) + Number(entry.hours);
      hoursPerDay.set(entry.work_date, running);
      if (running > MAX_DAILY_HOURS) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['entries', index, 'hours'],
          message: `A day cannot hold more than ${String(MAX_DAILY_HOURS)} hours`,
        });
      }
    });
  });

export type MyTimesheetFormValues = z.input<typeof myTimesheetSchema>;

// ---------------------------------------------------------------------------
// Profile
//
// Exactly the fields `PATCH /me/profile` accepts. Adding one here without
// adding it there produces a 422, which is the right direction to fail in.
// ---------------------------------------------------------------------------
export const myProfileSchema = z.object({
  personal_email: z
    .string()
    .optional()
    .transform((value) => value?.trim() ?? '')
    .refine((value) => value === '' || z.string().email().safeParse(value).success, 'Enter a valid email')
    .transform((value) => (value === '' ? null : value.toLowerCase())),
  mobile_number: optionalPhone('Mobile number'),
  alternate_number: optionalPhone('Alternate number'),
  emergency_contact_name: optionalText(150, 'Emergency contact name'),
  emergency_contact_number: optionalPhone('Emergency contact number'),
  emergency_contact_relationship: optionalText(50, 'Relationship'),
  photo_url: z
    .string()
    .optional()
    .transform((value) => value?.trim() ?? '')
    .refine((value) => value === '' || /^https?:\/\//.test(value), 'Enter a URL starting with http')
    .transform((value) => (value === '' ? null : value)),
});

export type MyProfileFormValues = z.input<typeof myProfileSchema>;

export const myAddressSchema = z.object({
  address_type: z.enum(['current', 'permanent']),
  address_line1: requiredText('Address', 255, 3),
  address_line2: optionalText(255, 'Address line 2'),
  landmark: optionalText(255, 'Landmark'),
  city: requiredText('City', 100, 1),
  state: requiredText('State', 100, 1),
  country: requiredText('Country', 100, 1),
  postal_code: requiredText('Postal code', 20, 2),
});

export type MyAddressFormValues = z.input<typeof myAddressSchema>;

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------
export const myDocumentUploadSchema = z.object({
  name: requiredText('Name', 200, 2),
  document_type_id: id,
  description: optionalText(2000, 'Description'),
  expiry_date: z
    .string()
    .optional()
    .transform((value) => (value ? value : null)),
});

export type MyDocumentUploadFormValues = z.input<typeof myDocumentUploadSchema>;
