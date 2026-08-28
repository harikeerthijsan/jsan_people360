import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollSettingsPage } from '@/features/payroll/components/payroll-settings-page';

export default function Page(): React.JSX.Element {
  return (
    <RequirePermission anyOf={['payroll:config_view', 'payroll:config_manage']} title="payroll settings">
      <PayrollSettingsPage />
    </RequirePermission>
  );
}
