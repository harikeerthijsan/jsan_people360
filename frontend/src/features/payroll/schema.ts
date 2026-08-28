import { z } from 'zod';

/**
 * Form validation for the payroll screens.
 *
 * Money is validated as an exact decimal *string* — up to twelve integer
 * digits and two decimal places, matching what the columns hold — because
 * parsing salaries into floats is how ₹5,00,000.10 becomes ₹5,00,000.0999.
 * The backend revalidates everything; this exists so a typo is caught before
 * the request leaves the browser.
 */

export const moneyString = z
  .string()
  .regex(/^\d{1,12}(\.\d{1,2})?$/, 'Enter a non-negative amount with up to two decimals');

const positiveMoneyString = moneyString.refine((value) => Number(value) > 0, {
  message: 'Must be greater than zero',
});

export const currencyCode = z
  .string()
  .regex(/^[A-Z]{3}$/, 'Use a three-letter ISO currency code, e.g. INR');

export const componentFormSchema = z
  .object({
    name: z.string().min(2, 'Name the component').max(120),
    code: z
      .string()
      .min(2, 'Give it a short code')
      .max(30)
      .regex(/^[A-Za-z0-9_-]+$/, 'Letters, digits, dashes and underscores only'),
    component_type: z.enum(['earning', 'deduction']),
    calculation_type: z.enum(['fixed', 'percentage']),
    value: moneyString,
    percentage_basis: z.enum(['basic', 'gross']).nullable(),
    description: z.string().max(4000).nullable(),
    // Pay behaviour flags (Phase 2): stored now, read by a later calculation.
    proration_allowed: z.boolean(),
    attendance_impact: z.boolean(),
    leave_impact: z.boolean(),
    overtime_eligible: z.boolean(),
    is_taxable: z.boolean(),
  })
  .superRefine((data, context) => {
    if (data.calculation_type === 'percentage') {
      if (data.percentage_basis === null) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['percentage_basis'],
          message: 'A percentage needs a base — of Basic or of Gross',
        });
      }
      if (Number(data.value) > 100) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ['value'],
          message: 'A percentage cannot exceed 100',
        });
      }
    }
  });

export type ComponentFormValues = z.infer<typeof componentFormSchema>;

export const structureFormSchema = z
  .object({
    name: z.string().min(2, 'Name the structure').max(120),
    description: z.string().max(4000).nullable(),
    pay_frequency: z.enum(['monthly', 'weekly', 'biweekly']),
    currency: currencyCode,
    effective_from: z.string().nullable(),
    effective_to: z.string().nullable(),
    component_ids: z.array(z.string().uuid()).min(1, 'Pick at least one component'),
  })
  .superRefine((data, context) => {
    if (data.effective_from && data.effective_to && data.effective_to < data.effective_from) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['effective_to'],
        message: 'The end date cannot be before the start date',
      });
    }
  });

export type StructureFormValues = z.infer<typeof structureFormSchema>;

const compensationCore = z.object({
  salary_structure_id: z.string().uuid('Choose a salary structure'),
  currency: currencyCode,
  annual_ctc: positiveMoneyString,
  annual_gross: moneyString,
  monthly_gross: moneyString,
  basic_salary: moneyString,
  effective_from: z.string().min(1, 'Pick the effective date'),
  components: z
    .array(z.object({ component_id: z.string().uuid(), value: moneyString }))
    .min(1, 'The structure must supply at least one component'),
});

export const assignmentFormSchema = compensationCore.extend({
  reason: z.string().max(4000).nullable(),
});

export type AssignmentFormValues = z.infer<typeof assignmentFormSchema>;

export const revisionFormSchema = compensationCore.extend({
  // Mandatory here and optional on assignment: a change to somebody's pay is
  // a decision with a why, and the history's Reason column must never be
  // blank for one.
  reason: z.string().min(3, 'Say why the salary is changing').max(4000),
});

export type RevisionFormValues = z.infer<typeof revisionFormSchema>;

// ---------------------------------------------------------------------------
// Phase 2 — configuration and pay rules
// ---------------------------------------------------------------------------
const dayOfMonth = (max: number) => z.number().int().min(1).max(max);

const hoursString = z
  .string()
  .regex(/^\d{1,2}(\.\d{1,2})?$/, 'Enter hours with up to two decimals');

export const payrollConfigFormSchema = z
  .object({
    pay_frequency: z.enum(['monthly', 'weekly', 'biweekly']),
    period_start_day: dayOfMonth(28),
    period_end_day: dayOfMonth(31),
    pay_day: dayOfMonth(31),
    cutoff_day: dayOfMonth(28),
    currency: currencyCode,
    working_days_rule: z.enum(['calendar_days', 'working_days', 'custom_working_days']),
    weekly_off_days: z.array(z.number().int().min(0).max(6)).max(7),
    proration_basis: z.enum(['calendar_days', 'working_days']),
    unpaid_leave_treatment: z.enum(['deduct', 'ignore']),
    unpaid_leave_basis: z.enum(['calendar_days', 'working_days']),
    overtime_enabled: z.boolean(),
    overtime_basis: z.enum(['basic', 'gross']),
    overtime_multiplier: z
      .string()
      .regex(/^\d{1,2}(\.\d{1,2})?$/, 'Enter a multiplier like 1.5')
      .refine((value) => Number(value) > 0, { message: 'The multiplier must be positive' }),
    overtime_min_hours: hoursString,
    overtime_max_hours: hoursString.nullable(),
    overtime_approval_required: z.boolean(),
    standard_daily_hours: hoursString.refine((value) => Number(value) > 0 && Number(value) <= 24, {
      message: 'Standard daily hours must be between 0 and 24',
    }),
    deduct_absence: z.boolean(),
    deduct_late_arrival: z.boolean(),
    deduct_early_exit: z.boolean(),
    require_approved_attendance: z.boolean(),
    rounding_rule: z.enum(['none', 'nearest_whole', 'nearest_half', 'custom']),
    rounding_precision: z
      .string()
      .regex(/^\d{1,4}(\.\d{1,2})?$/, 'Enter a precision like 0.5 or 1')
      .nullable(),
    reason: z.string().min(3, 'Say why the configuration is changing').max(4000),
    effective_from: z.string().min(1, 'Pick the effective date'),
  })
  .superRefine((data, context) => {
    if (new Set(data.weekly_off_days).size !== data.weekly_off_days.length) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['weekly_off_days'],
        message: 'A weekday appears more than once',
      });
    }
    if (data.rounding_rule === 'custom' && data.rounding_precision === null) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['rounding_precision'],
        message: 'Custom rounding needs a precision — 0.01, 1, 10 and so on',
      });
    }
    if (
      data.overtime_max_hours !== null &&
      Number(data.overtime_max_hours) < Number(data.overtime_min_hours)
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['overtime_max_hours'],
        message: 'Maximum overtime hours cannot be below the minimum',
      });
    }
  });

export type PayrollConfigFormValues = z.infer<typeof payrollConfigFormSchema>;

export const periodFormSchema = z
  .object({
    name: z.string().min(2, 'Name the period, e.g. August 2026').max(60),
    start_date: z.string().min(1, 'Pick the start date'),
    end_date: z.string().min(1, 'Pick the end date'),
    pay_date: z.string().min(1, 'Pick the pay date'),
    notes: z.string().max(4000).nullable(),
  })
  .superRefine((data, context) => {
    if (data.end_date < data.start_date) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_date'],
        message: 'The period cannot end before it starts',
      });
    }
    if (data.pay_date < data.start_date) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['pay_date'],
        message: 'The pay date cannot be before the period starts',
      });
    }
  });

export type PeriodFormValues = z.infer<typeof periodFormSchema>;

export const leaveRuleFormSchema = z
  .object({
    leave_type_id: z.string().uuid('Choose a leave type'),
    treatment: z.enum(['paid', 'unpaid']),
    deduction_basis: z.enum(['calendar_days', 'working_days']).nullable(),
    description: z.string().max(4000).nullable(),
  })
  .superRefine((data, context) => {
    if (data.treatment === 'unpaid' && data.deduction_basis === null) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['deduction_basis'],
        message: 'An unpaid rule must say which day basis the deduction uses',
      });
    }
  });

export type LeaveRuleFormValues = z.infer<typeof leaveRuleFormSchema>;
