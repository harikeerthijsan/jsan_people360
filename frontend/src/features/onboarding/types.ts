export interface OnboardingDocument {
  id: string;
  name: string;
  status: string;
  review_notes: string | null;
}
export interface PolicyAcknowledgement {
  id: string;
  policy_code: string;
  acknowledged_at: string;
}
export interface OnboardingTask {
  id: string;
  category: string;
  title: string;
  owner_id: string;
  due_date: string;
  status: string;
  comments: string | null;
  completed_at: string | null;
}
export interface OnboardingCase {
  id: string;
  profile_id: string;
  employee_id: string;
  status: string;
  progress_percent: number;
  started_at: string | null;
  completed_at: string | null;
  tasks: OnboardingTask[];
}
export interface PreboardingProfile {
  id: string;
  candidate_id: string;
  offer_id: string;
  user_id: string | null;
  joining_date: string;
  joining_confirmed: boolean;
  first_name: string;
  last_name: string;
  date_of_birth: string | null;
  gender: string | null;
  blood_group: string | null;
  marital_status: string | null;
  nationality: string | null;
  personal_email: string;
  mobile_number: string;
  emergency_contact: Record<string, string>;
  addresses: Array<Record<string, string>>;
  bank_details: Record<string, string>;
  aadhaar_number: string | null;
  pan_number: string | null;
  status: string;
  information_approved: boolean;
  employee_id: string | null;
}
export interface PortalData {
  profile: PreboardingProfile;
  documents: OnboardingDocument[];
  acknowledgements: PolicyAcknowledgement[];
  required_documents: string[];
  required_policies: string[];
  progress_percent: number;
  case_id: string | null;
}
export interface OnboardingDashboardData {
  awaiting_preboarding: number;
  pending_documents: number;
  pending_hr_tasks: number;
  pending_it_tasks: number;
  pending_manager_tasks: number;
  joining_this_week: number;
  delayed_joining: number;
  completed_onboarding: number;
}
export interface WelcomeData {
  employee_id: string;
  employee_code: string;
  name: string;
  joining_date: string;
  reporting_manager: string | null;
  team: string | null;
  office_location: string | null;
  tasks: OnboardingTask[];
}
