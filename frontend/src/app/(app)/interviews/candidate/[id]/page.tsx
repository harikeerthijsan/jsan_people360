import { CandidateInterviewTimeline } from '@/features/interviews/components';

export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  return <CandidateInterviewTimeline candidateId={(await params).id} />;
}
