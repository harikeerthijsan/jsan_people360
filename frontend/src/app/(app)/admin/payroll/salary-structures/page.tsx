import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { SalaryStructuresPage } from '@/features/payroll/components/salary-structures-page';

export default function Page(): React.JSX.Element {
  return (
    <RequirePermission
      anyOf={['payroll:structure_manage', 'payroll:create', 'payroll:update']}
      title="salary structures"
    >
      <SalaryStructuresPage />
    </RequirePermission>
  );
}
