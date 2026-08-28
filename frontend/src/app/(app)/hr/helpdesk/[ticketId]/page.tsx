import * as React from 'react';

import { TicketDetailPage } from '@/features/helpdesk/components/ticket-detail-page';

interface Props {
  params: Promise<{ ticketId: string }>;
}

export default async function Page({ params }: Props): Promise<React.JSX.Element> {
  const { ticketId } = await params;
  return <TicketDetailPage ticketId={ticketId} />;
}
