/**
 * Domain types for Performance Management.
 *
 * Ratings are integers on a fixed 1-5 scale throughout: self, manager and final
 * all score the same way, so a rating can be compared across stages and cycles
 * without translation.
 */

export type PerformanceCycleStatus = 'draft' | 'active' | 'closed' | 'archived';
export type GoalStatus = 'not_started' | 'in_progress' | 'completed' | 'blocked' | 'cancelled';
export type GoalPriority = 'low' | 'medium' | 'high' | 'critical';
export type ReviewStatus = 'draft' | 'submitted';
export type ReviewStage = 'self' | 'manager';
export type Recommendation = 'promotion' | 'salary_revision' | 'training' | 'pip' | 'none';
export type RecognitionType =
  'star_performer' | 'innovation' | 'team_player' | 'customer_appreciation' | 'leadership';
export type FeedbackCategory = 'appreciation' | 'suggestion' | 'improvement' | 'achievement' | 'recognition';
export type FeedbackVisibility = 'private' | 'manager' | 'public';

export const MIN_RATING = 1;
export const MAX_RATING = 5;
/** An employee's goals may total at most this much of their cycle. */
export const TOTAL_WEIGHTAGE = 100;

export const CYCLE_STATUS_LABELS: Record<PerformanceCycleStatus, string> = {
  draft: 'Draft',
  active: 'Active',
  closed: 'Closed',
  archived: 'Archived',
};

/** Ordered as a goal moves, not alphabetically. */
export const GOAL_STATUSES: readonly GoalStatus[] = [
  'not_started',
  'in_progress',
  'completed',
  'blocked',
  'cancelled',
] as const;

export const GOAL_STATUS_LABELS: Record<GoalStatus, string> = {
  not_started: 'Not started',
  in_progress: 'In progress',
  completed: 'Completed',
  blocked: 'Blocked',
  cancelled: 'Cancelled',
};

export const GOAL_PRIORITIES: readonly GoalPriority[] = ['low', 'medium', 'high', 'critical'] as const;

export const GOAL_PRIORITY_LABELS: Record<GoalPriority, string> = {
  low: 'Low',
  medium: 'Medium',
  high: 'High',
  critical: 'Critical',
};

export const RECOMMENDATION_LABELS: Record<Recommendation, string> = {
  promotion: 'Promotion',
  salary_revision: 'Salary revision',
  training: 'Training',
  pip: 'Performance improvement plan',
  none: 'No recommendation',
};

export const RECOGNITION_TYPES: readonly RecognitionType[] = [
  'star_performer',
  'innovation',
  'team_player',
  'customer_appreciation',
  'leadership',
] as const;

export const RECOGNITION_LABELS: Record<RecognitionType, string> = {
  star_performer: 'Star performer',
  innovation: 'Innovation',
  team_player: 'Team player',
  customer_appreciation: 'Customer appreciation',
  leadership: 'Leadership',
};

export const FEEDBACK_CATEGORIES: readonly FeedbackCategory[] = [
  'appreciation',
  'suggestion',
  'improvement',
  'achievement',
  'recognition',
] as const;

export const FEEDBACK_CATEGORY_LABELS: Record<FeedbackCategory, string> = {
  appreciation: 'Appreciation',
  suggestion: 'Suggestion',
  improvement: 'Improvement',
  achievement: 'Achievement',
  recognition: 'Recognition',
};

export const VISIBILITY_LABELS: Record<FeedbackVisibility, string> = {
  private: 'Private',
  manager: 'Manager',
  public: 'Public',
};

/** What each point on the scale means, so a rating control can say so. */
export const RATING_LABELS: Record<number, string> = {
  1: 'Needs significant improvement',
  2: 'Below expectations',
  3: 'Meets expectations',
  4: 'Exceeds expectations',
  5: 'Outstanding',
};

// ---------------------------------------------------------------------------
// Records
// ---------------------------------------------------------------------------
export interface PerformanceCycle {
  id: string;
  cycle_code: string;
  name: string;
  financial_year: string;
  start_date: string;
  end_date: string;
  self_review_deadline: string;
  manager_review_deadline: string;
  hr_review_deadline: string;
  description: string | null;
  status: PerformanceCycleStatus;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
}

export interface GoalProgressEntry {
  id: string;
  goal_id: string;
  completion_percentage: number;
  status: GoalStatus;
  comments: string | null;
  evidence_document_id: string | null;
  created_at: string;
  created_by: string | null;
}

export interface GoalRating {
  id: string;
  goal_id: string;
  stage: ReviewStage;
  rating: number;
  comments: string | null;
}

export interface Goal {
  id: string;
  goal_code: string;
  cycle_id: string;
  employee_id: string;
  project_id: string | null;
  assigned_by_id: string | null;
  title: string;
  description: string;
  category: string;
  success_criteria: string;
  /** Sent as a decimal string so no precision is lost in transit. */
  weightage: string;
  start_date: string;
  due_date: string;
  priority: GoalPriority;
  status: GoalStatus;
  completion_percentage: number;
  created_at: string;
  updated_at: string;
  deleted_at: string | null;
  progress_updates: GoalProgressEntry[];
  ratings: GoalRating[];
}

export interface EmployeeRef {
  id: string;
  employee_code: string;
  full_name: string;
}

export interface SelfReview {
  id: string;
  cycle_id: string;
  employee_id: string;
  overall_rating: number | null;
  overall_comments: string | null;
  achievements: string | null;
  challenges: string | null;
  status: ReviewStatus;
  submitted_at: string | null;
}

export interface ManagerReview {
  id: string;
  cycle_id: string;
  employee_id: string;
  reviewer_id: string;
  overall_rating: number | null;
  overall_feedback: string | null;
  strengths: string | null;
  improvement_areas: string | null;
  recommendation: Recommendation;
  status: ReviewStatus;
  submitted_at: string | null;
}

export interface FinalReview {
  id: string;
  cycle_id: string;
  employee_id: string;
  finalised_by_id: string | null;
  final_rating: number;
  comments: string | null;
  self_rating: number | null;
  manager_rating: number | null;
  goal_completion_percentage: number | null;
  finalised_at: string | null;
}

/** Everything the review screens need, in one payload. */
export interface EmployeePerformance {
  employee: EmployeeRef;
  cycle: PerformanceCycle;
  goals: Goal[];
  total_weightage: string;
  goal_completion_percentage: number;
  self_review: SelfReview | null;
  manager_review: ManagerReview | null;
  final_review: FinalReview | null;
}

export interface Recognition {
  id: string;
  employee_id: string;
  awarded_by_id: string | null;
  recognition_type: RecognitionType;
  title: string;
  description: string;
  awarded_on: string;
  created_at: string;
}

export interface Feedback {
  id: string;
  from_employee_id: string;
  to_employee_id: string;
  title: string;
  description: string;
  category: FeedbackCategory;
  visibility: FeedbackVisibility;
  feedback_date: string;
  created_at: string;
}

export interface PerformanceHistoryEntry {
  id: string;
  employee_id: string;
  cycle_id: string | null;
  event_type: string;
  summary: string;
  detail: string | null;
  rating: number | null;
  created_at: string;
}

export interface CountByLabel {
  label: string;
  count: number;
}

export interface RatedEmployee {
  employee: EmployeeRef;
  rating: number;
  cycle_name: string;
}

export interface PerformanceDashboard {
  active_cycles: number;
  goals_assigned: number;
  goals_completed: number;
  goal_completion_percentage: number;
  self_reviews_pending: number;
  manager_reviews_pending: number;
  reviews_pending: number;
  final_ratings: number;
  top_performers: RatedEmployee[];
  low_performance_alerts: RatedEmployee[];
  by_goal_status: CountByLabel[];
  by_priority: CountByLabel[];
}

export interface PerformanceAnalytics {
  goal_completion: CountByLabel[];
  business_unit_performance: CountByLabel[];
  manager_performance: CountByLabel[];
  rating_distribution: CountByLabel[];
  goal_distribution: CountByLabel[];
  performance_trend: CountByLabel[];
}

export type PerformanceReport =
  'goal-completion' | 'performance-summary' | 'employee-ratings' | 'recognitions';

export type ExportFormat = 'csv' | 'xlsx' | 'pdf';
