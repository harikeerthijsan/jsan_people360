import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { SalaryComponentsPage } from '@/features/payroll/components/salary-components-page';

export default function Page(): React.JSX.Element {
  return (
    <RequirePermission
      anyOf={[
        'payroll:component_manage',
        'payroll:structure_manage',
        'payroll:create',
        'payroll:update',
      ]}
      title="salary components"
    >
      <SalaryComponentsPage />
    </RequirePermission>
  );
}
