'use client';

import { Download, Eye, FileUp } from 'lucide-react';
import * as React from 'react';

import { Timeline, type TimelineItem } from '@/components/common/timeline';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import type { DocumentVersionRecord } from '@/features/documents/types/document.types';
import { formatDateTime } from '@/lib/utils';

/**
 * A document's version history.
 *
 * Built on the shared `Timeline`, which already knows about rails, markers and
 * ordered lists. What is specific here is that every entry stays actionable:
 * an older version is not an archive note, it is a file someone may still need
 * to open, so each row keeps its own preview and download.
 */

interface VersionTimelineProps {
  versions: DocumentVersionRecord[];
  /** The version currently in force, marked so the reader can see it at a glance. */
  currentVersionId: string | null;
  onPreview: (version: DocumentVersionRecord) => void;
  onDownload: (version: DocumentVersionRecord) => void;
  className?: string;
}

export function VersionTimeline({
  versions,
  currentVersionId,
  onPreview,
  onDownload,
  className,
}: VersionTimelineProps): React.JSX.Element {
  const items: TimelineItem[] = versions.map((version) => {
    const isCurrent = version.id === currentVersionId;

    return {
      id: version.id,
      highlighted: isCurrent,
      icon: <FileUp className="size-3.5" aria-hidden="true" />,
      title: (
        <span className="flex flex-wrap items-center gap-2">
          Version {version.version_number}
          {isCurrent ? <Badge variant="success">Current</Badge> : null}
        </span>
      ),
      timestamp: formatDateTime(version.created_at),
      description: `${version.original_filename} · ${version.size_display}`,
      meta: (
        <div className="space-y-2">
          {version.notes ? <p>{version.notes}</p> : null}
          <div className="flex flex-wrap gap-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => {
                onPreview(version);
              }}
            >
              <Eye aria-hidden="true" />
              Preview
            </Button>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => {
                onDownload(version);
              }}
            >
              <Download aria-hidden="true" />
              Download
            </Button>
          </div>
        </div>
      ),
    };
  });

  return <Timeline items={items} className={className} />;
}
