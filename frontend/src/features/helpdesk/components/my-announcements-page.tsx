'use client';

import { CheckCircle2, Megaphone, Pin } from 'lucide-react';
import * as React from 'react';

import { EmptyState } from '@/components/common/empty-state';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useAcknowledgeAnnouncement, useMyAnnouncements } from '@/features/helpdesk/hooks';
import {
  ANNOUNCEMENT_PRIORITY_LABELS,
  type AnnouncementPriority,
  type MyAnnouncement,
} from '@/features/helpdesk/types';

/**
 * The notice board.
 *
 * Read only, apart from acknowledging. The list comes back already filtered to
 * published, in-window notices that reach this employee -- the audience match
 * happens in SQL on the server, so there is no draft here to accidentally
 * render and no audience rule for this component to re-implement.
 *
 * Acknowledging is idempotent on the server, so a double click is not a double
 * acknowledgement, and the button is disabled once it has happened anyway.
 */

const PRIORITY_TONE: Record<AnnouncementPriority, 'secondary' | 'default' | 'destructive'> = {
  normal: 'secondary',
  important: 'default',
  urgent: 'destructive',
};

function AnnouncementCard({ announcement }: { announcement: MyAnnouncement }): React.JSX.Element {
  const acknowledge = useAcknowledgeAnnouncement();
  const needsAck = announcement.requires_acknowledgement && !announcement.acknowledged;

  return (
    <Card className={needsAck ? 'border-primary/50' : undefined}>
      <CardHeader className="pb-3">
        <div className="flex flex-wrap items-start justify-between gap-2">
          <CardTitle className="flex items-center gap-2 text-base">
            {announcement.pinned ? (
              <Pin className="text-primary size-4 shrink-0" aria-label="Pinned" />
            ) : null}
            {announcement.title}
          </CardTitle>
          <div className="flex items-center gap-2">
            {announcement.priority !== 'normal' ? (
              <Badge variant={PRIORITY_TONE[announcement.priority]}>
                {ANNOUNCEMENT_PRIORITY_LABELS[announcement.priority]}
              </Badge>
            ) : null}
            {announcement.published_at ? (
              <span className="text-muted-foreground text-xs">
                {new Date(announcement.published_at).toLocaleDateString()}
              </span>
            ) : null}
          </div>
        </div>
        {announcement.summary ? (
          <p className="text-muted-foreground text-sm">{announcement.summary}</p>
        ) : null}
      </CardHeader>

      <CardContent className="space-y-4">
        <p className="text-sm leading-relaxed whitespace-pre-wrap">{announcement.body}</p>

        {announcement.expires_at ? (
          <p className="text-muted-foreground text-xs">
            Comes down on {new Date(announcement.expires_at).toLocaleDateString()}.
          </p>
        ) : null}

        {announcement.requires_acknowledgement ? (
          announcement.acknowledged ? (
            <p className="text-muted-foreground flex items-center gap-2 text-sm">
              <CheckCircle2 className="size-4" aria-hidden="true" />
              You have acknowledged this.
            </p>
          ) : (
            <div className="flex flex-wrap items-center gap-3">
              <Button
                size="sm"
                onClick={() => acknowledge.mutate(announcement.id)}
                disabled={acknowledge.isPending}
              >
                I have read this
              </Button>
              <span className="text-muted-foreground text-xs">
                This one asks for confirmation that you have seen it.
              </span>
            </div>
          )
        ) : null}
      </CardContent>
    </Card>
  );
}

export function MyAnnouncementsPage(): React.JSX.Element {
  const query = useMyAnnouncements();
  const rows = query.data ?? [];
  const outstanding = rows.filter((row) => row.requires_acknowledgement && !row.acknowledged).length;

  return (
    <div className="space-y-6">
      <PageHeader
        title="Announcements"
        description="Company notices addressed to you. Pinned items stay at the top."
      />

      {outstanding > 0 ? (
        <p className="text-sm">
          <span className="font-medium">
            {outstanding} announcement{outstanding === 1 ? '' : 's'}
          </span>{' '}
          <span className="text-muted-foreground">
            {outstanding === 1 ? 'is' : 'are'} waiting for your acknowledgement.
          </span>
        </p>
      ) : null}

      {query.isLoading ? (
        <LoadingState message="Loading announcements…" />
      ) : query.error ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState
          icon={Megaphone}
          title="Nothing to read"
          description="Company announcements addressed to you will appear here."
        />
      ) : (
        <div className="space-y-4">
          {rows.map((announcement) => (
            <AnnouncementCard key={announcement.id} announcement={announcement} />
          ))}
        </div>
      )}
    </div>
  );
}
