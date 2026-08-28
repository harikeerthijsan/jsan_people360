import { z } from 'zod';

import { MAX_RATING, MIN_RATING, TOTAL_WEIGHTAGE } from './types';

/**
 * Client-side validation for the performance forms.
 *
 * Mirrors the server so a mistake is caught before a round trip, and no more:
 * the rules that need to see other rows -- has this employee already committed
 * 100% of their weightage, is this cycle still open -- can only be enforced by
 * the API, and are.
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

export const ratingSchema = z.coerce
  .number()
  .int('Ratings are whole numbers')
  .min(MIN_RATING, `Rate between ${String(MIN_RATING)} and ${String(MAX_RATING)}`)
  .max(MAX_RATING, `Rate between ${String(MIN_RATING)} and ${String(MAX_RATING)}`);

// ---------------------------------------------------------------------------
// Cycles
// ---------------------------------------------------------------------------
export const cycleSchema = z
  .object({
    name: requiredText('Name', 150, 2),
    financial_year: requiredText('Financial year', 20, 4),
    start_date: isoDate,
    end_date: isoDate,
    self_review_deadline: isoDate,
    manager_review_deadline: isoDate,
    hr_review_deadline: isoDate,
    description: optionalText(2000, 'Description'),
  })
  .superRefine((values, context) => {
    if (values.end_date <= values.start_date) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['end_date'],
        message: 'The cycle must end after it starts',
      });
    }

    // Reviews run self, then manager, then HR. Anything else describes a
    // process nobody can actually follow.
    const deadlines: [string, string][] = [
      ['self_review_deadline', values.self_review_deadline],
      ['manager_review_deadline', values.manager_review_deadline],
      ['hr_review_deadline', values.hr_review_deadline],
    ];
    deadlines.forEach(([field, value], index) => {
      const previous = deadlines[index - 1];
      if (previous && value < previous[1]) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: [field],
          message: 'Deadlines must run self, then manager, then HR',
        });
      }
      if (value < values.start_date) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: [field],
          message: 'Deadlines cannot fall before the cycle starts',
        });
      }
    });
  });

// ---------------------------------------------------------------------------
// Goals
// ---------------------------------------------------------------------------
export const goalSchema = z
  .object({
    cycle_id: id,
    employee_id: id,
    project_id: z
      .string()
      .optional()
      .transform((value) => (value ? value : null)),
    title: requiredText('Title', 200),
    description: requiredText('Description', 5000),
    category: requiredText('Category', 100, 2),
    success_criteria: requiredText('Success criteria', 5000),
    weightage: z.coerce
      .number()
      .gt(0, 'Weightage must be more than 0')
      .max(TOTAL_WEIGHTAGE, `Weightage cannot exceed ${String(TOTAL_WEIGHTAGE)}%`),
    start_date: isoDate,
    due_date: isoDate,
    priority: z.enum(['low', 'medium', 'high', 'critical']),
  })
  .superRefine((values, context) => {
    if (values.due_date < values.start_date) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['due_date'],
        message: 'A goal cannot be due before it starts',
      });
    }
  });

export const goalProgressSchema = z
  .object({
    completion_percentage: z.coerce.number().int().min(0).max(100),
    status: z.enum(['not_started', 'in_progress', 'completed', 'blocked', 'cancelled']),
    comments: optionalText(2000, 'Comments'),
    evidence_document_id: z
      .string()
      .optional()
      .transform((value) => (value ? value : null)),
  })
  .superRefine((values, context) => {
    // A goal reported complete at 40% is a contradiction the reviewer would
    // have to unpick later.
    if (values.status === 'completed' && values.completion_percentage !== 100) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['completion_percentage'],
        message: 'A completed goal must be at 100%',
      });
    }
    if (values.status === 'not_started' && values.completion_percentage !== 0) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ['completion_percentage'],
        message: 'A goal that has not started must be at 0%',
      });
    }
  });

// ---------------------------------------------------------------------------
// Reviews
// ---------------------------------------------------------------------------
const goalRatingSchema = z.object({
  goal_id: z.string().uuid(),
  rating: ratingSchema,
  comments: optionalText(2000, 'Comments'),
});

export const selfReviewSchema = z.object({
  overall_rating: ratingSchema,
  overall_comments: requiredText('Overall comments', 5000),
  achievements: optionalText(5000, 'Achievements'),
  challenges: optionalText(5000, 'Challenges'),
  goal_ratings: z.array(goalRatingSchema),
});

export const managerReviewSchema = z.object({
  overall_rating: ratingSchema,
  overall_feedback: requiredText('Overall feedback', 5000),
  strengths: optionalText(5000, 'Strengths'),
  improvement_areas: optionalText(5000, 'Improvement areas'),
  recommendation: z.enum(['promotion', 'salary_revision', 'training', 'pip', 'none']),
  goal_ratings: z.array(goalRatingSchema),
});

export const finalReviewSchema = z.object({
  final_rating: ratingSchema,
  comments: optionalText(5000, 'Comments'),
});

// ---------------------------------------------------------------------------
// Recognition and feedback
// ---------------------------------------------------------------------------
export const recognitionSchema = z.object({
  employee_id: id,
  recognition_type: z.enum([
    'star_performer',
    'innovation',
    'team_player',
    'customer_appreciation',
    'leadership',
  ]),
  title: requiredText('Title', 200),
  description: requiredText('Description', 2000),
  awarded_on: isoDate,
});

export const feedbackSchema = z.object({
  to_employee_id: id,
  title: requiredText('Title', 200),
  description: requiredText('Description', 2000),
  category: z.enum(['appreciation', 'suggestion', 'improvement', 'achievement', 'recognition']),
  visibility: z.enum(['private', 'manager', 'public']),
  feedback_date: isoDate,
});

export type CycleValues = z.input<typeof cycleSchema>;
export type GoalValues = z.input<typeof goalSchema>;
export type GoalProgressValues = z.input<typeof goalProgressSchema>;
export type SelfReviewValues = z.input<typeof selfReviewSchema>;
export type ManagerReviewValues = z.input<typeof managerReviewSchema>;
export type FinalReviewValues = z.input<typeof finalReviewSchema>;
export type RecognitionValues = z.input<typeof recognitionSchema>;
export type FeedbackValues = z.input<typeof feedbackSchema>;

/**
 * How much of the 100% budget is still free.
 *
 * Shown next to the weightage field so a manager plans against the remainder
 * rather than discovering the ceiling when the server refuses the save.
 */
export function remainingWeightage(goals: { weightage: string; status: string }[]): number {
  const committed = goals
    .filter((goal) => goal.status !== 'cancelled')
    .reduce((total, goal) => total + Number(goal.weightage), 0);
  return Math.max(0, TOTAL_WEIGHTAGE - committed);
}
