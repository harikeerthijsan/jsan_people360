import * as React from 'react';

import { HomeDashboard } from '@/features/dashboard/components/home-dashboard';

/** The landing screen for authenticated users. */
export default function DashboardPage(): React.JSX.Element {
  return <HomeDashboard />;
}
