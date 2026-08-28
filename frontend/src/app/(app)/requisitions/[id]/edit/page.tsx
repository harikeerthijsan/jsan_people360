'use client';
import { useParams } from 'next/navigation';
import { LoadingState } from '@/components/common/loading-state';
import { ErrorState } from '@/components/common/error-state';
import { RequisitionForm } from '@/features/requisitions/components';
import { useRequisition } from '@/features/requisitions/hooks';
export default function Page() {
  const { id } = useParams<{ id: string }>();
  const q = useRequisition(id);
  if (q.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} />;
  return <RequisitionForm record={q.data} />;
}
