import { RequisitionDetail } from '@/features/requisitions/components';
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  return <RequisitionDetail id={(await params).id} />;
}
