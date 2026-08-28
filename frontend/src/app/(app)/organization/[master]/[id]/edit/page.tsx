import { notFound } from 'next/navigation';
import type * as React from 'react';

import { MasterFormPage } from '@/features/organization/components/master-form-page';
import { getMasterConfig } from '@/features/organization/config/master-registry';

interface PageProps {
  params: Promise<{ master: string; id: string }>;
}

export default async function MasterEditRoute({ params }: PageProps): Promise<React.JSX.Element> {
  const { master, id } = await params;
  const config = getMasterConfig(master);

  if (!config) {
    notFound();
  }

  return <MasterFormPage slug={config.slug} recordId={id} />;
}
