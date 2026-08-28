import { InterviewDetail } from '@/features/interviews/components';
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  return <InterviewDetail id={(await params).id} />;
}
