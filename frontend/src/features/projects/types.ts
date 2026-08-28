export interface Client {
  id: string;
  client_code: string;
  client_name: string;
  company_name: string;
  industry: string;
  contact_person: string;
  email: string;
  phone: string;
  country: string;
  address: string;
  website: string | null;
  status: string;
  created_at: string;
}
export interface Allocation {
  id: string;
  employee_id: string;
  project_id: string;
  member_id: string;
  allocation_percentage: string;
  start_date: string;
  end_date: string | null;
  billable: boolean;
  status: string;
  reason: string | null;
  created_at: string;
}
export interface Member {
  id: string;
  project_id: string;
  employee_id: string;
  role: string;
  reporting_manager_id: string | null;
  joined_at: string;
  left_at: string | null;
}
export interface Project {
  id: string;
  project_code: string;
  project_name: string;
  client_id: string;
  client: Client;
  description: string;
  start_date: string;
  end_date: string | null;
  status: string;
  project_manager_id: string;
  delivery_manager_id: string | null;
  work_location_id: string | null;
  is_billable: boolean;
  technology_stack: string[];
  priority: string;
  members: Member[];
  allocations: Allocation[];
  created_at: string;
}
export interface Dashboard {
  total_clients: number;
  active_projects: number;
  completed_projects: number;
  employees_allocated: number;
  bench_employees: number;
  allocation_utilization_percent: number;
  projects_ending_soon: number;
  allocation_conflicts: number;
  project_headcount: Array<{ project_id: string; project: string; headcount: number }>;
}
export interface BenchEmployee {
  employee_id: string;
  employee_code: string;
  name: string;
  bench_since: string;
  bench_duration_days: number;
  skills: string[];
  team: string | null;
  manager: string | null;
}
export interface ProjectDashboardData {
  project: Project;
  team_members: Allocation[];
  headcount: number;
  utilization_percent: number;
  billable_percent: number;
  upcoming_end_dates: Allocation[];
}
export interface ClientDashboardData {
  client: Client;
  active_projects: number;
  total_employees: number;
  billable_employees: number;
  revenue_available: boolean;
}
