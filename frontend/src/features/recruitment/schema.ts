import { z } from 'zod';
const uuid = z.string().uuid('Select a valid record.');
export const candidateSchema = z
  .object({
    job_opening_id: uuid,
    source_id: uuid,
    recruiter_id: uuid.nullable().optional(),
    first_name: z.string().trim().min(1),
    last_name: z.string().trim().min(1),
    email: z.string().email(),
    mobile_number: z.string().regex(/^\+?[0-9 ()-]{7,30}$/),
    linkedin_url: z.string().url().nullable().optional(),
    current_company: z.string().nullable().optional(),
    current_designation: z.string().nullable().optional(),
    experience_years: z.coerce.number().min(0).max(60),
    current_ctc: z.coerce.number().min(0).nullable().optional(),
    expected_ctc: z.coerce.number().min(0).nullable().optional(),
    notice_period_days: z.coerce.number().int().min(0).max(365),
    current_location: z.string().nullable().optional(),
    preferred_location: z.string().nullable().optional(),
    certifications: z.string().nullable().optional(),
    tags: z.string().nullable().optional(),
    skills: z.array(z.string().min(1)).min(1),
    resume_document_id: uuid,
  })
  .refine((x) => x.current_ctc == null || x.expected_ctc == null || x.expected_ctc >= x.current_ctc, {
    message: 'Expected CTC cannot be lower than current CTC',
    path: ['expected_ctc'],
  });
