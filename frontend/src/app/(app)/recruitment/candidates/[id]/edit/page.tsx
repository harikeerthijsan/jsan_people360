import { CandidateEdit } from '@/features/recruitment/components';

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  return <CandidateEdit id={(await params).id} />;
}
