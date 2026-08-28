import * as React from 'react';

import { AssetDetailPage } from '@/features/assets/components/asset-detail-page';

interface Props {
  params: Promise<{ assetId: string }>;
}

export default async function Page({ params }: Props): Promise<React.JSX.Element> {
  const { assetId } = await params;
  return <AssetDetailPage assetId={assetId} />;
}
