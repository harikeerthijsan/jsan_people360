/**
 * Asset management types, mirroring the API schemas.
 *
 * `MyAsset` is a separate type from `Asset`, exactly as it is a separate model
 * on the server: it has no purchase cost, no vendor and no notes, because an
 * employee has no business reading what the company paid for their laptop. A
 * type that never declares the field cannot render it by accident.
 *
 * `AssetStatus` and the transitions between them are the server's to decide.
 * The client never holds a copy of the transition table -- an asset's detail
 * response carries `allowed_transitions`, so a status control offers exactly
 * what the backend would accept.
 */

export type AssetStatus =
  'available' | 'assigned' | 'reserved' | 'under_maintenance' | 'damaged' | 'lost' | 'retired' | 'disposed';

export type AssetCondition = 'new' | 'excellent' | 'good' | 'fair' | 'damaged';
export type MaintenanceStatus = 'scheduled' | 'in_progress' | 'completed' | 'cancelled';
export type MaintenanceType = 'preventive' | 'repair' | 'upgrade' | 'inspection' | 'other';
export type WarrantyState = 'none' | 'active' | 'expiring_soon' | 'expired';

export type AssetEvent =
  | 'created'
  | 'updated'
  | 'assigned'
  | 'returned'
  | 'transferred'
  | 'maintenance_started'
  | 'maintenance_completed'
  | 'damaged'
  | 'lost'
  | 'recovered'
  | 'retired'
  | 'disposed'
  | 'status_changed'
  | 'clearance_waived';

export interface AssetCategory {
  id: string;
  name: string;
  code: string;
  description: string | null;
  returnable: boolean;
  status: 'active' | 'inactive';
}

export interface EmployeeSummary {
  id: string;
  employee_code: string;
  full_name: string;
}

export interface Asset {
  id: string;
  asset_code: string;
  asset_tag: string;
  name: string;
  category: AssetCategory;
  asset_type: string | null;
  brand: string | null;
  model: string | null;
  serial_number: string | null;
  purchase_date: string | null;
  purchase_cost: string | null;
  vendor: string | null;
  warranty_start: string | null;
  warranty_end: string | null;
  warranty_provider: string | null;
  warranty_reference: string | null;
  warranty_state: WarrantyState;
  location: string | null;
  condition: AssetCondition;
  status: AssetStatus;
  notes: string | null;
  assigned_to: EmployeeSummary | null;
  assigned_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface AssetHistoryEntry {
  id: string;
  event: AssetEvent;
  employee_id: string | null;
  previous_value: string | null;
  new_value: string | null;
  notes: string | null;
  created_at: string;
  created_by: string | null;
}

export interface AssetAssignment {
  id: string;
  asset_id: string;
  employee: EmployeeSummary | null;
  assigned_date: string;
  expected_return_date: string | null;
  condition_at_assignment: AssetCondition;
  assigned_by_id: string | null;
  notes: string | null;
  returned_at: string | null;
}

export interface Maintenance {
  id: string;
  asset_id: string;
  maintenance_type: MaintenanceType;
  start_date: string;
  end_date: string | null;
  vendor: string | null;
  cost: string | null;
  description: string | null;
  status: MaintenanceStatus;
  notes: string | null;
}

export interface AssetDetail extends Asset {
  current_assignment: AssetAssignment | null;
  history: AssetHistoryEntry[];
  maintenance: Maintenance[];
  /** What the server will accept next. The client holds no transition table. */
  allowed_transitions: AssetStatus[];
}

/** The employee's own view. Deliberately carries no cost, vendor or notes. */
export interface MyAsset {
  id: string;
  asset_code: string;
  asset_tag: string;
  name: string;
  category: string;
  brand: string | null;
  model: string | null;
  serial_number: string | null;
  assigned_date: string;
  expected_return_date: string | null;
  condition_at_assignment: AssetCondition;
  status: AssetStatus;
}

export interface TeamAssetRow {
  assignment_id: string;
  asset_id: string;
  employee: EmployeeSummary;
  asset_code: string;
  asset_tag: string;
  name: string;
  category: string;
  status: AssetStatus;
  condition: AssetCondition;
  assigned_date: string;
  expected_return_date: string | null;
}

export interface EmployeeAssetClearanceRow {
  asset_id: string;
  asset_code: string;
  asset_tag: string;
  name: string;
  category: string;
  assigned_date: string;
  condition: AssetCondition;
  returnable: boolean;
  clearance_status: string;
}

export interface CountByLabel {
  label: string;
  count: number;
}

export interface AssetDashboard {
  total: number;
  available: number;
  assigned: number;
  reserved: number;
  under_maintenance: number;
  damaged: number;
  lost: number;
  retired: number;
  disposed: number;
  by_category: CountByLabel[];
  by_location: CountByLabel[];
  by_status: CountByLabel[];
  warranty_expiring_soon: number;
  warranty_expired: number;
  maintenance_due: number;
  recent_assignments: AssetHistoryEntry[];
  recent_returns: AssetHistoryEntry[];
  recent_transfers: AssetHistoryEntry[];
}

// -- Request payloads ----------------------------------------------------
export interface AssetCreateInput {
  name: string;
  category_id: string;
  asset_tag: string;
  condition: AssetCondition;
  status?: AssetStatus;
  asset_type?: string | null;
  brand?: string | null;
  model?: string | null;
  serial_number?: string | null;
  purchase_date?: string | null;
  purchase_cost?: string | null;
  vendor?: string | null;
  warranty_start?: string | null;
  warranty_end?: string | null;
  warranty_provider?: string | null;
  warranty_reference?: string | null;
  location?: string | null;
  notes?: string | null;
}

export type AssetUpdateInput = Partial<Omit<AssetCreateInput, 'condition' | 'status'>>;

export interface AssignInput {
  employee_id: string;
  assigned_date: string;
  condition_at_assignment: AssetCondition;
  expected_return_date?: string | null;
  notes?: string | null;
}

export interface ReturnInput {
  return_date: string;
  condition_at_return: AssetCondition;
  damage_details?: string | null;
  missing_accessories?: string | null;
  notes?: string | null;
  resulting_status?: AssetStatus | null;
}

export interface TransferInput {
  to_employee_id: string;
  transfer_date: string;
  condition_at_transfer: AssetCondition;
  reason?: string | null;
  notes?: string | null;
}

export interface StatusChangeInput {
  status: AssetStatus;
  reason: string;
  condition?: AssetCondition | null;
}

export interface MaintenanceCreateInput {
  asset_id: string;
  maintenance_type: MaintenanceType;
  start_date: string;
  end_date?: string | null;
  vendor?: string | null;
  cost?: string | null;
  description?: string | null;
  notes?: string | null;
  start_now?: boolean;
}

export interface MaintenanceUpdateInput {
  status: MaintenanceStatus;
  end_date?: string | null;
  cost?: string | null;
  vendor?: string | null;
  notes?: string | null;
  resulting_condition?: AssetCondition | null;
  resulting_status?: AssetStatus | null;
}

export interface AssetFilters {
  search?: string;
  category_id?: string;
  status?: AssetStatus;
  condition?: AssetCondition;
  location?: string;
  vendor?: string;
  assigned?: boolean;
  warranty_expiring?: boolean;
  page?: number;
  page_size?: number;
}

// -- Labels --------------------------------------------------------------
export const ASSET_STATUS_LABELS: Record<AssetStatus, string> = {
  available: 'Available',
  assigned: 'Assigned',
  reserved: 'Reserved',
  under_maintenance: 'Under maintenance',
  damaged: 'Damaged',
  lost: 'Lost',
  retired: 'Retired',
  disposed: 'Disposed',
};

export const ASSET_CONDITION_LABELS: Record<AssetCondition, string> = {
  new: 'New',
  excellent: 'Excellent',
  good: 'Good',
  fair: 'Fair',
  damaged: 'Damaged',
};

export const MAINTENANCE_STATUS_LABELS: Record<MaintenanceStatus, string> = {
  scheduled: 'Scheduled',
  in_progress: 'In progress',
  completed: 'Completed',
  cancelled: 'Cancelled',
};

export const MAINTENANCE_TYPE_LABELS: Record<MaintenanceType, string> = {
  preventive: 'Preventive',
  repair: 'Repair',
  upgrade: 'Upgrade',
  inspection: 'Inspection',
  other: 'Other',
};

export const WARRANTY_STATE_LABELS: Record<WarrantyState, string> = {
  none: 'No warranty',
  active: 'Active',
  expiring_soon: 'Expiring soon',
  expired: 'Expired',
};

export const ASSET_REPORTS = [
  { id: 'inventory', label: 'Complete asset inventory' },
  { id: 'assigned', label: 'Assigned assets' },
  { id: 'available', label: 'Available assets' },
  { id: 'by_employee', label: 'Employee asset report' },
  { id: 'maintenance', label: 'Maintenance report' },
  { id: 'warranty', label: 'Warranty report' },
  { id: 'lost_damaged', label: 'Lost and damaged assets' },
  { id: 'movement', label: 'Asset movement history' },
] as const;

export type AssetReportId = (typeof ASSET_REPORTS)[number]['id'];
