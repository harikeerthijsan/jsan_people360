import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollEmployeeSettingsPage } from '@/features/payroll/components/payroll-employee-settings-page';

export default function Page(): React.JSX.Element {
  return (
    <RequirePermission
      permission="payroll:employee_settings_view"
      title="employee payroll settings"
    >
      <PayrollEmployeeSettingsPage />
    </RequirePermission>
  );
}
