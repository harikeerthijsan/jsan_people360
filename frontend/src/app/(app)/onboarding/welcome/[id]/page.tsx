import { WelcomeScreen } from '@/features/onboarding/components';
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <WelcomeScreen caseId={id} />;
}
