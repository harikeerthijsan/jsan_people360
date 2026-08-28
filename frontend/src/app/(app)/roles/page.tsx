import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { RoleManagementPage } from '@/features/roles/components/role-management-page';

export default function Page(): React.JSX.Element {
  return (
    <RequirePermission permission="roles:view" title="roles and permissions">
      <RoleManagementPage />
    </RequirePermission>
  );
}
