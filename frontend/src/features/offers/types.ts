export interface Offer {
  id: string;
  offer_code: string;
  candidate_id: string;
  job_opening_id: string;
  template_id: string | null;
  status: string;
  ctc: string;
  joining_date: string;
  probation_months: number;
  notice_period_days: number;
  reporting_manager_id: string | null;
  work_mode: string;
  shift: string | null;
  benefits: string;
  leave_policy_summary: string;
  working_hours: string;
  confidentiality: string;
  nda_required: boolean;
  additional_conditions: string | null;
  release_date: string | null;
  expiry_date: string;
  accepted_at: string | null;
  declined_at: string | null;
  decline_reason: string | null;
  clarification_request: string | null;
  withdrawn_at: string | null;
  withdrawal_reason: string | null;
  current_version: number;
  salary_components: {
    id: string;
    name: string;
    component_type: string;
    annual_amount: string;
    is_employer_contribution: boolean;
  }[];
  versions: { id: string; version_number: number; pdf_document_id: string | null; created_at: string }[];
  approvals: {
    id: string;
    sequence: number;
    role_name: string;
    approver_id: string;
    status: string;
    comments: string | null;
    acted_at: string | null;
  }[];
  history: {
    id: string;
    action: string;
    from_status: string | null;
    to_status: string;
    comments: string | null;
    created_at: string;
  }[];
  created_at: string;
}
export interface OfferDashboard {
  total: number;
  draft: number;
  pending_approval: number;
  approved: number;
  released: number;
  accepted: number;
  declined: number;
  expired: number;
  joining_pending: number;
  acceptance_rate: number;
  offer_to_join_ratio: number;
}
export interface OfferTemplate {
  id: string;
  name: string;
  body: string;
  is_active: boolean;
  created_at: string;
}
