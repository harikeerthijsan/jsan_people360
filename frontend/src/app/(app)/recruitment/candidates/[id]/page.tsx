import { CandidateProfile } from '@/features/recruitment/components';
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  return <CandidateProfile id={(await params).id} />;
}
