/** Domain types for role and permission administration. */

export interface Permission {
  id: string;
  code: string;
  module: string;
  action: string;
  permission_group: string;
  label: string;
  description: string | null;
}

export interface ModulePermissions {
  module: string;
  label: string;
  description: string;
  permissions: Permission[];
}

export interface PermissionGroup {
  group: string;
  label: string;
  modules: ModulePermissions[];
}

export interface Role {
  id: string;
  key: string;
  name: string;
  description: string | null;
  /** Shipped with the product: cannot be renamed, deactivated or deleted. */
  is_system: boolean;
  status: 'active' | 'inactive';
  created_at: string;
  permissions: string[];
  /** How many accounts hold it, so deleting one is an informed choice. */
  user_count: number;
}

export interface RoleSummary {
  id: string;
  key: string;
  name: string;
  is_system: boolean;
  status: string;
}

export interface UserRoles {
  user_id: string;
  roles: RoleSummary[];
  permissions: string[];
}

/** Ordered as the role editor renders them, not alphabetically. */
export const ACTION_LABELS: Record<string, string> = {
  view: 'View',
  create: 'Create',
  update: 'Update',
  delete: 'Delete',
  export: 'Export',
  approve: 'Approve',
  apply: 'Apply',
};
