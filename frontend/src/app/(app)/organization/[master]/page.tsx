import { notFound } from 'next/navigation';
import { Suspense } from 'react';
import type * as React from 'react';

import { LoadingState } from '@/components/common/loading-state';
import { MasterListPage } from '@/features/organization/components/master-list-page';
import { MASTER_ORDER, getMasterConfig } from '@/features/organization/config/master-registry';

/**
 * One dynamic route serves every master list.
 *
 * The seven masters differ only by configuration, so seven near-identical page
 * files would be duplication with extra steps. `generateStaticParams` keeps the
 * real routes enumerable at build time, and an unrecognised slug 404s.
 */
export function generateStaticParams(): { master: string }[] {
  return MASTER_ORDER.map((master) => ({ master }));
}

/**
 * The set of masters is fixed at build time, so anything outside it is a real
 * 404 — not a page to render on demand.
 *
 * This also fixes the status code. Reaching `notFound()` from inside the page
 * body happens after the response has begun streaming, so the 404 document is
 * served with a 200. Rejecting the param before the page runs returns a proper
 * 404, which is what monitoring and crawlers act on.
 */
export const dynamicParams = false;

interface PageProps {
  params: Promise<{ master: string }>;
}

export default async function MasterListRoute({ params }: PageProps): Promise<React.JSX.Element> {
  const { master } = await params;
  const config = getMasterConfig(master);

  if (!config) {
    notFound();
  }

  return (
    // The list reads its state from the query string, which requires a
    // Suspense boundary under the App Router.
    <Suspense fallback={<LoadingState message="Loading…" />}>
      <MasterListPage slug={config.slug} />
    </Suspense>
  );
}
