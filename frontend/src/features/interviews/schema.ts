import { z } from 'zod';
const uuid = z.string().uuid('Enter a valid UUID.');
export const scheduleSchema = z
  .object({
    candidate_id: uuid,
    interview_type: z.enum(['hr', 'technical', 'managerial', 'client', 'final_hr']),
    interview_round: z.string().min(1),
    starts_at: z.string().min(1),
    ends_at: z.string().min(1),
    time_zone: z.string().min(1),
    mode: z.enum(['online', 'offline', 'hybrid']),
    meeting_link: z.string().url().nullable(),
    location: z.string().nullable(),
    recruiter_notes: z.string().nullable(),
    panels: z
      .array(
        z.object({
          employee_id: uuid,
          designation_id: uuid.nullable(),
          panel_role: z.enum(['lead_interviewer', 'panel_member', 'observer']),
        }),
      )
      .min(1),
  })
  .refine((x) => new Date(x.ends_at) > new Date(x.starts_at), {
    message: 'End time must be after start time',
    path: ['ends_at'],
  })
  .refine((x) => (new Date(x.ends_at).getTime() - new Date(x.starts_at).getTime()) / 60000 >= 15, {
    message: 'Interview must last at least 15 minutes',
    path: ['ends_at'],
  })
  .refine((x) => x.panels.filter((p) => p.panel_role === 'lead_interviewer').length === 1, {
    message: 'Exactly one lead interviewer is required',
    path: ['panels'],
  })
  .refine((x) => x.mode !== 'offline' || Boolean(x.location), {
    message: 'Offline interviews require a location',
    path: ['location'],
  });
export type ScheduleValues = z.infer<typeof scheduleSchema>;
export const feedbackSchema = z.object({
  interviewer_id: uuid,
  overall_comments: z.string().min(1),
  recommendation: z.enum(['strong_hire', 'hire', 'hold', 'reject']),
  scores: z
    .array(
      z.object({
        category: z.string(),
        score: z.coerce.number().int().min(1).max(10),
        comments: z.string().nullable(),
      }),
    )
    .length(6),
});
