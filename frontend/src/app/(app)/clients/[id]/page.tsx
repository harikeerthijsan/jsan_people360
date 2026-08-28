import { ClientDetails } from '@/features/projects/components';
export default async function Page({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ClientDetails id={id} />;
}
