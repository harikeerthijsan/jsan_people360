import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollRunDetailPage } from '@/features/payroll/components/payroll-run-detail-page';

interface Props {
  params: Promise<{ runId: string }>;
}

export default async function Page({ params }: Props): Promise<React.JSX.Element> {
  const { runId } = await params;
  return (
    <RequirePermission permission="payroll:runs_view" title="payroll runs">
      <PayrollRunDetailPage runId={runId} />
    </RequirePermission>
  );
}
