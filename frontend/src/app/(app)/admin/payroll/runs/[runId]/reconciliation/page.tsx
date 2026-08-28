import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollRunReconciliationPage } from '@/features/payroll/components/payroll-run-reconciliation-page';

interface Props {
  params: Promise<{ runId: string }>;
}

export default async function Page({ params }: Props): Promise<React.JSX.Element> {
  const { runId } = await params;
  return (
    <RequirePermission permission="payroll:review_view" title="payroll reconciliation">
      <PayrollRunReconciliationPage runId={runId} />
    </RequirePermission>
  );
}
