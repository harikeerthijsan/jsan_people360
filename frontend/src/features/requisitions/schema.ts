import { z } from 'zod';
const id = z.string().uuid('Choose a valid record');
const optionalId = z.union([id, z.literal(''), z.null()]).transform((v) => v || null);
export const requisitionSchema = z
  .object({
    job_title: z.string().trim().min(2).max(200),
    hiring_type: z.enum(['new_position', 'replacement', 'contract', 'internship']),
    request_type: z.enum(['new_position', 'replacement', 'contract', 'internship']),
    business_unit_id: id,
    team_id: optionalId,
    location_id: id,
    designation_id: id,
    grade_id: optionalId,
    employment_type_id: id,
    openings: z.coerce.number().int().min(1).max(1000),
    experience_min: z.coerce.number().int().min(0),
    experience_max: z.union([z.coerce.number().int().min(0), z.null()]),
    education: z.string().nullable().optional(),
    skills: z.array(z.string()),
    certifications: z.array(z.string()),
    salary_from: z.union([z.coerce.number().min(0), z.null()]),
    salary_to: z.union([z.coerce.number().min(0), z.null()]),
    budget_approved: z.boolean(),
    hiring_manager_id: id,
    second_approver_id: id,
    hr_approver_id: id,
    recruiter_id: optionalId,
    target_joining_date: z
      .string()
      .refine((v) => new Date(`${v}T00:00:00`) > new Date(), 'Target joining date must be in the future'),
    priority: z.enum(['low', 'medium', 'high', 'critical']),
    responsibilities: z.string().trim().min(10),
    requirements: z.string().trim().min(10),
    benefits: z.string().nullable().optional(),
    working_model: z.enum(['office', 'remote', 'hybrid']),
    business_justification: z.string().trim().min(10),
  })
  .superRefine((v, ctx) => {
    if (v.salary_from !== null && v.salary_to !== null && v.salary_from > v.salary_to)
      ctx.addIssue({
        code: 'custom',
        path: ['salary_to'],
        message: 'Maximum salary must be at least the minimum',
      });
    if (v.experience_max !== null && v.experience_min > v.experience_max)
      ctx.addIssue({
        code: 'custom',
        path: ['experience_max'],
        message: 'Maximum experience must be at least the minimum',
      });
  });
