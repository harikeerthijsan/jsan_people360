import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollRunApprovalPage } from '@/features/payroll/components/payroll-run-approval-page';

interface Props {
  params: Promise<{ runId: string }>;
}

export default async function Page({ params }: Props): Promise<React.JSX.Element> {
  const { runId } = await params;
  return (
    <RequirePermission permission="payroll:approval_view" title="payroll approval">
      <PayrollRunApprovalPage runId={runId} />
    </RequirePermission>
  );
}
