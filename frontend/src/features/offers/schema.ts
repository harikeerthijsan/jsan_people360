import { z } from 'zod';
const uuid = z.string().uuid();
export const offerSchema = z
  .object({
    candidate_id: uuid,
    template_id: uuid.nullable(),
    ctc: z.coerce.number().positive(),
    joining_date: z.string().min(1),
    probation_months: z.coerce.number().int().min(0).max(36),
    notice_period_days: z.coerce.number().int().min(0).max(365),
    reporting_manager_id: uuid.nullable(),
    work_mode: z.enum(['office', 'hybrid', 'remote']),
    shift: z.string().nullable(),
    benefits: z.string().min(1),
    leave_policy_summary: z.string().min(1),
    working_hours: z.string().min(1),
    confidentiality: z.string().min(1),
    nda_required: z.boolean(),
    additional_conditions: z.string().nullable(),
    expiry_date: z.string().min(1),
    salary_components: z
      .array(
        z.object({
          name: z.string().min(1),
          component_type: z.string().min(1),
          annual_amount: z.coerce.number().min(0),
          is_employer_contribution: z.boolean(),
        }),
      )
      .min(3),
    hr_executive_id: uuid,
    hr_manager_id: uuid,
    business_unit_head_id: uuid,
  })
  .refine((x) => new Date(x.joining_date) > new Date(x.expiry_date), {
    message: 'Expiry must be before joining date',
    path: ['expiry_date'],
  })
  .refine(
    (x) => {
      const names = new Set(
        x.salary_components.map((component) => component.name.toLowerCase().replaceAll(' ', '_')),
      );
      return ['basic_salary', 'hra', 'special_allowance'].every((name) => names.has(name));
    },
    { message: 'Basic Salary, HRA, and Special Allowance are mandatory', path: ['salary_components'] },
  )
  .refine((x) => x.salary_components.reduce((n, c) => n + c.annual_amount, 0) === x.ctc, {
    message: 'Salary components must equal CTC',
    path: ['salary_components'],
  });
