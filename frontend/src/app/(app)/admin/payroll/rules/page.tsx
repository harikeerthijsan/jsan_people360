import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollRulesPage } from '@/features/payroll/components/payroll-rules-page';

export default function Page(): React.JSX.Element {
  return (
    <RequirePermission anyOf={['payroll:config_view', 'payroll:rule_manage']} title="payroll rules">
      <PayrollRulesPage />
    </RequirePermission>
  );
}
