export interface Stage {
  id: string;
  name: string;
  sequence: number;
  category: string;
}
export interface Source {
  id: string;
  name: string;
}
export interface Opening {
  id: string;
  job_code: string;
  requisition_id: string;
  recruiter_id: string | null;
  status: string;
  closing_date: string | null;
  published_at: string | null;
  closed_at: string | null;
  created_at: string;
}
export interface Candidate {
  id: string;
  candidate_code: string;
  job_opening_id: string;
  source_id: string;
  stage_id: string;
  recruiter_id: string | null;
  first_name: string;
  last_name: string;
  email: string;
  mobile_number: string;
  linkedin_url: string | null;
  current_company: string | null;
  current_designation: string | null;
  experience_years: string;
  current_ctc: string | null;
  expected_ctc: string | null;
  notice_period_days: number;
  current_location: string | null;
  preferred_location: string | null;
  certifications: string | null;
  tags: string | null;
  applied_at: string;
  stage: Stage;
  source: Source;
  skills: { id: string; name: string; proficiency: string | null }[];
  documents: { id: string; document_id: string; document_kind: string; created_at: string }[];
  stage_history: {
    id: string;
    from_stage_id: string | null;
    to_stage_id: string;
    comments: string | null;
    created_at: string;
  }[];
  notes: {
    id: string;
    body: string;
    mentions: string | null;
    is_internal: boolean;
    created_at: string;
    created_by: string | null;
  }[];
}
export interface Dashboard {
  open_jobs: number;
  total_applicants: number;
  offers_released: number;
  offers_accepted: number;
  offers_declined: number;
  joining_pending: number;
  by_stage: { label: string; count: number }[];
  recruiter_workload: { label: string; count: number }[];
  hiring_trend: { label: string; count: number }[];
  average_time_to_hire_days: number;
  average_time_to_fill_days: number;
}
export interface TalentPool {
  id: string;
  name: string;
  description: string | null;
  created_at: string;
}
