import { z } from 'zod';

import { MAX_DAILY_HOURS } from './types';

/**
 * Client-side validation for the workforce forms.
 *
 * Mirrors the server so a mistake is caught before a round trip, and no more:
 * how many leave days are left, whether this week is already submitted, whether
 * the employee is allocated to the project being booked against -- those need
 * to see other rows and can only be enforced by the API, and are.
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

/** `HH:MM` or `HH:MM:SS`, which is what an `<input type="time">` produces. */
const clockTime = z
  .string()
  .regex(/^([01]\d|2[0-3]):[0-5]\d(:[0-5]\d)?$/, 'Use a 24-hour time, such as 09:30');

const decimalString = (label: string, max: number) =>
  z
    .string()
    .min(1, `${label} is required`)
    .regex(/^\d+(\.\d{1,2})?$/, `${label} must be a number`)
    .refine((value) => Number(value) <= max, `${label} must be at most ${String(max)}`);

// ---------------------------------------------------------------------------
// Shifts
// ---------------------------------------------------------------------------
export const shiftSchema = z
  .object({
    name: requiredText('Name', 100, 2),
    code: requiredText('Code', 30, 2),
    shift_type: z.enum(['general', 'morning', 'evening', 'night', 'flexible']),
    start_time: clockTime,
    end_time: clockTime,
    grace_minutes: z.coerce.number().int().min(0).max(240),
    break_minutes: z.coerce.number().int().min(0).max(480),
    weekly_off: z.array(z.coerce.number().int().min(0).max(6)),
    status: z.enum(['active', 'inactive']),
  })
  .superRefine((values, context) => {
    // A night shift legitimately ends before it starts, so equal times are the
    // only impossible case: a shift of zero length.
    if (values.start_time === values.end_time) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_time'],
        message: 'A shift cannot start and end at the same time',
      });
    }
    if (values.weekly_off.length >= 7) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['weekly_off'],
        message: 'A shift must have at least one working day',
      });
    }
    if (new Set(values.weekly_off).size !== values.weekly_off.length) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['weekly_off'],
        message: 'A day cannot be listed twice',
      });
    }
  });

export type ShiftFormValues = z.input<typeof shiftSchema>;

export const shiftAssignSchema = z.object({
  employee_id: id,
  shift_id: id,
  effective_from: isoDate,
});

export type ShiftAssignFormValues = z.input<typeof shiftAssignSchema>;

// ---------------------------------------------------------------------------
// Attendance
// ---------------------------------------------------------------------------
export const checkInSchema = z.object({
  work_mode: z.enum(['office', 'remote', 'hybrid', 'client_site']),
  notes: optionalText(1000, 'Notes'),
});

export type CheckInFormValues = z.input<typeof checkInSchema>;

export const regularizationSchema = z
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

export type RegularizationFormValues = z.input<typeof regularizationSchema>;

export const decisionSchema = z.object({
  approved: z.boolean(),
  notes: optionalText(2000, 'Notes'),
});

export type DecisionFormValues = z.input<typeof decisionSchema>;

// ---------------------------------------------------------------------------
// Leave
// ---------------------------------------------------------------------------
export const leaveTypeSchema = z
  .object({
    name: requiredText('Name', 100, 2),
    code: requiredText('Code', 30, 2),
    description: optionalText(2000, 'Description'),
    annual_allocation: decimalString('Annual allocation', 365),
    carry_forward: z.boolean(),
    max_carry_forward: decimalString('Maximum carry forward', 365),
    allows_negative: z.boolean(),
    is_paid: z.boolean(),
    requires_document: z.boolean(),
    status: z.enum(['active', 'inactive']),
  })
  .superRefine((values, context) => {
    if (!values.carry_forward && Number(values.max_carry_forward) > 0) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['max_carry_forward'],
        message: 'Turn carry forward on before giving it a maximum',
      });
    }
    if (values.carry_forward && Number(values.max_carry_forward) <= 0) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['max_carry_forward'],
        message: 'Carry forward needs a maximum above zero',
      });
    }
  });

export type LeaveTypeFormValues = z.input<typeof leaveTypeSchema>;

export const leaveApplySchema = z
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
    // Rounding a multi-day half-day request would produce a balance nobody
    // could explain, so it is refused rather than interpreted.
    if (values.day_part !== 'full_day' && values.from_date !== values.to_date) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['day_part'],
        message: 'A half day applies to a single date',
      });
    }
  });

export type LeaveApplyFormValues = z.input<typeof leaveApplySchema>;

// ---------------------------------------------------------------------------
// Holidays
// ---------------------------------------------------------------------------
export const holidayCalendarSchema = z
  .object({
    name: requiredText('Name', 150, 2),
    year: z.coerce.number().int().min(2000).max(2100),
    location_id: optionalId,
    description: optionalText(2000, 'Description'),
    holidays: z
      .array(
        z.object({
          name: requiredText('Holiday name', 150, 2),
          holiday_date: isoDate,
          holiday_type: z.enum(['public', 'restricted', 'optional']),
        }),
      )
      .min(1, 'Add at least one holiday'),
  })
  .superRefine((values, context) => {
    const seen = new Set<string>();
    values.holidays.forEach((holiday, index) => {
      if (seen.has(holiday.holiday_date)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['holidays', index, 'holiday_date'],
          message: 'This date is already in the calendar',
        });
      }
      seen.add(holiday.holiday_date);

      if (!holiday.holiday_date.startsWith(String(values.year))) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['holidays', index, 'holiday_date'],
          message: `This date is not in ${String(values.year)}`,
        });
      }
    });
  });

export type HolidayCalendarFormValues = z.input<typeof holidayCalendarSchema>;

// ---------------------------------------------------------------------------
// Timesheets
// ---------------------------------------------------------------------------
export const timesheetSchema = z
  .object({
    week_start_date: isoDate,
    entries: z.array(
      z.object({
        project_id: id,
        work_date: isoDate,
        task: requiredText('Task', 200, 2),
        hours: decimalString('Hours', MAX_DAILY_HOURS),
        billable: z.boolean(),
        comments: optionalText(1000, 'Comments'),
      }),
    ),
  })
  .superRefine((values, context) => {
    const weekStart = new Date(`${values.week_start_date}T00:00:00`);
    if (weekStart.getDay() !== 1) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['week_start_date'],
        message: 'A timesheet week starts on a Monday',
      });
    }

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

export type TimesheetFormValues = z.input<typeof timesheetSchema>;
