import * as React from 'react';

import { RequirePermission } from '@/components/common/can';
import { PayrollRecordPage } from '@/features/payroll/components/payroll-record-page';

interface Props {
  params: Promise<{ runId: string; employeeId: string }>;
}

export default async function Page({ params }: Props): Promise<React.JSX.Element> {
  const { runId, employeeId } = await params;
  return (
    <RequirePermission
      anyOf={['payroll:record_view', 'payroll:team_view']}
      title="calculated payroll records"
    >
      <PayrollRecordPage runId={runId} employeeId={employeeId} />
    </RequirePermission>
  );
}
