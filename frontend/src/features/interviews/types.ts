export interface Panel {
  id: string;
  employee_id: string;
  designation_id: string | null;
  panel_role: string;
  status: string;
}
export interface Score {
  id: string;
  category: string;
  score: number;
  comments: string | null;
}
export interface Feedback {
  id: string;
  interviewer_id: string;
  scores: Score[];
  overall_comments: string;
  recommendation: string;
  submitted_at: string;
}
export interface InterviewHistory {
  id: string;
  action: string;
  previous_starts_at: string | null;
  previous_ends_at: string | null;
  new_starts_at: string | null;
  new_ends_at: string | null;
  comments: string | null;
  created_at: string;
}
export interface Interview {
  id: string;
  interview_code: string;
  candidate_id: string;
  job_opening_id: string;
  interview_type: string;
  interview_round: string;
  starts_at: string;
  ends_at: string;
  time_zone: string;
  mode: string;
  meeting_link: string | null;
  location: string | null;
  recruiter_notes: string | null;
  status: string;
  overall_score: number | null;
  overall_recommendation: string | null;
  decision: string | null;
  panels: Panel[];
  feedback: Feedback[];
  history: InterviewHistory[];
  attachments: { id: string; document_id: string; attachment_kind: string; created_at: string }[];
  created_at: string;
}
export interface InterviewDashboard {
  todays_interviews: number;
  upcoming_interviews: number;
  completed_interviews: number;
  cancelled_interviews: number;
  pending_feedback: number;
  average_score: number;
  selection_ratio: number;
  completion_rate: number;
  candidate_status: { label: string; count: number }[];
  interviewer_workload: { label: string; count: number }[];
}
