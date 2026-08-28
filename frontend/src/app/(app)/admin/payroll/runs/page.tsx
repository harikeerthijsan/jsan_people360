import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollRunsPage } from '@/features/payroll/components/payroll-runs-page';

export default function Page(): React.JSX.Element {
  return (
    <RequirePermission permission="payroll:runs_view" title="payroll runs">
      <PayrollRunsPage />
    </RequirePermission>
  );
}
