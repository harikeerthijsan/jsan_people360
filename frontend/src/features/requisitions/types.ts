export type RequisitionStatus =
  'draft' | 'pending_approval' | 'approved' | 'rejected' | 'open' | 'on_hold' | 'closed' | 'cancelled';
export interface Approval {
  id: string;
  sequence: number;
  role_name: string;
  approver_id: string;
  status: string;
  comments: string | null;
  acted_at: string | null;
}
export interface History {
  id: string;
  action: string;
  from_status: string | null;
  to_status: string;
  comments: string | null;
  created_at: string;
  created_by: string | null;
}
export interface Requisition {
  id: string;
  requisition_code: string;
  job_title: string;
  hiring_type: string;
  request_type: string;
  status: RequisitionStatus;
  priority: string;
  business_unit_id: string;
  team_id: string | null;
  location_id: string;
  designation_id: string;
  grade_id: string | null;
  employment_type_id: string;
  openings: number;
  experience_min: number;
  experience_max: number | null;
  education: string | null;
  skills: string[];
  certifications: string[];
  salary_from: string | null;
  salary_to: string | null;
  budget_approved: boolean;
  hiring_manager_id: string;
  second_approver_id: string;
  hr_approver_id: string;
  recruiter_id: string | null;
  target_joining_date: string;
  responsibilities: string;
  requirements: string;
  benefits: string | null;
  working_model: string;
  business_justification: string;
  current_approval_sequence: number | null;
  approvals: Approval[];
  attachments: { id: string; document_id: string; attachment_type: string; created_at: string }[];
  history: History[];
  created_at: string;
  updated_at: string;
  created_by: string | null;
  deleted_at: string | null;
}
export interface Dashboard {
  total_open: number;
  pending_approvals: number;
  approved: number;
  closed: number;
  expired: number;
  upcoming_targets: number;
  by_business_unit: { label: string; count: number }[];
  hiring_trend: { label: string; count: number }[];
}
