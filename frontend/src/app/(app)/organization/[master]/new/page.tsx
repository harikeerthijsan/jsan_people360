import { notFound } from 'next/navigation';
import type * as React from 'react';

import { MasterFormPage } from '@/features/organization/components/master-form-page';
import { MASTER_ORDER, getMasterConfig } from '@/features/organization/config/master-registry';

export function generateStaticParams(): { master: string }[] {
  return MASTER_ORDER.map((master) => ({ master }));
}

/** See the note in the list route: unknown masters are a 404, not a render. */
export const dynamicParams = false;

interface PageProps {
  params: Promise<{ master: string }>;
}

/** Create screen. `new` is a static segment, so it wins over `[id]`. */
export default async function MasterCreateRoute({ params }: PageProps): Promise<React.JSX.Element> {
  const { master } = await params;
  const config = getMasterConfig(master);

  if (!config) {
    notFound();
  }

  return <MasterFormPage slug={config.slug} />;
}
