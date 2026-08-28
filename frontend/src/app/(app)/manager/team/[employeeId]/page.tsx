import * as React from 'react';

import { TeamMemberPage } from '@/features/manager/components/team-member-page';

/**
 * One team member.
 *
 * `params` is a promise in Next 15, so this stays a server component that
 * awaits it and hands the id to the client component below. The id is not
 * trusted on the way through: the API checks it against the caller's reporting
 * line and answers 403 for anybody else's report.
 */
export default async function Page({
  params,
}: {
  params: Promise<{ employeeId: string }>;
}): Promise<React.JSX.Element> {
  const { employeeId } = await params;
  return <TeamMemberPage employeeId={employeeId} />;
}
