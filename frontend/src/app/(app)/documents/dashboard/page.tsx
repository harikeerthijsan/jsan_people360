import type { Metadata } from 'next';
import type * as React from 'react';

import { DocumentDashboardPage } from '@/features/documents/components/document-dashboard-page';

export const metadata: Metadata = {
  title: 'Document dashboard',
  description: 'What the vault is holding, and what needs attention.',
};

export default function DocumentDashboardRoute(): React.JSX.Element {
  return <DocumentDashboardPage />;
}
