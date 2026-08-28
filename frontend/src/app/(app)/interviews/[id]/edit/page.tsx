import { InterviewEdit } from '@/features/interviews/components';
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  return <InterviewEdit id={(await params).id} />;
}
