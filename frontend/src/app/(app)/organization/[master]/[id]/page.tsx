import { notFound } from 'next/navigation';
import type * as React from 'react';

import { MasterDetailPage } from '@/features/organization/components/master-detail-page';
import { getMasterConfig } from '@/features/organization/config/master-registry';

interface PageProps {
  params: Promise<{ master: string; id: string }>;
}

export default async function MasterDetailRoute({ params }: PageProps): Promise<React.JSX.Element> {
  const { master, id } = await params;
  const config = getMasterConfig(master);

  if (!config) {
    notFound();
  }

  return <MasterDetailPage slug={config.slug} recordId={id} />;
}
