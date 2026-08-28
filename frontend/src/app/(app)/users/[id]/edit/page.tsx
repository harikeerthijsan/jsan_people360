import type * as React from 'react';

import { UserEditPage } from '@/features/users/components/user-form-page';

interface PageProps {
  params: Promise<{ id: string }>;
}

export default async function EditUserRoute({ params }: PageProps): Promise<React.JSX.Element> {
  const { id } = await params;
  return <UserEditPage userId={id} />;
}
