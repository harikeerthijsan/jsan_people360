import * as React from 'react';

import { MyPayslipPage } from '@/features/payroll/components/my-payslips-page';

interface Props {
  params: Promise<{ payslipId: string }>;
}

export default async function Page({ params }: Props): Promise<React.JSX.Element> {
  const { payslipId } = await params;
  return <MyPayslipPage payslipId={payslipId} />;
}
