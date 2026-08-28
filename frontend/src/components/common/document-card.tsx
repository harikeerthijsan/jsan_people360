import { FileImage, FileText, Paperclip } from 'lucide-react';
import Link from 'next/link';
import * as React from 'react';

import { DocumentStatusBadge, ExpiryBadge } from '@/components/common/document-status-badge';
import { Card, CardContent } from '@/components/ui/card';
import type { DocumentRecord } from '@/features/documents/types/document.types';
import { cn, formatDate } from '@/lib/utils';

/**
 * A document as a compact card.
 *
 * For where a table row would be too dense to scan: an employee's document
 * panel, a candidate's application, the "needs attention" list on a dashboard.
 */

function iconFor(contentType: string | undefined): React.ReactNode {
  if (contentType?.startsWith('image/')) {
    return <FileImage className="size-5" aria-hidden="true" />;
  }
  if (contentType === 'application/pdf') {
    return <FileText className="size-5" aria-hidden="true" />;
  }
  return <Paperclip className="size-5" aria-hidden="true" />;
}

interface DocumentCardProps {
  document: DocumentRecord;
  /** Wraps the card in a link to the document when set. */
  href?: string;
  /** Rendered at the end of the card — an action menu, a remove button. */
  actions?: React.ReactNode;
  className?: string;
}

export function DocumentCard({ document, href, actions, className }: DocumentCardProps): React.JSX.Element {
  const version = document.current_version;
  const isArchived = document.deleted_at !== null;

  const body = (
    <CardContent className="flex items-start gap-3 p-4">
      <span className="text-muted-foreground mt-0.5 shrink-0">{iconFor(version?.content_type)}</span>

      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="truncate font-medium">{document.name}</p>
          <DocumentStatusBadge status={document.status} archived={isArchived} />
          <ExpiryBadge
            state={document.expiry_state}
            detail={document.expiry_date ? formatDate(document.expiry_date) : undefined}
          />
        </div>

        <p className="text-muted-foreground truncate text-xs">
          <span className="font-mono">{document.document_code}</span>
          {document.document_type ? <> · {document.document_type.name}</> : null}
          {/* Version 1 is the norm, so saying so on every card would be noise;
              anything above it is worth flagging. */}
          {document.version_count > 1 ? <> · v{document.version_count}</> : null}
        </p>

        {version ? (
          <p className="text-muted-foreground truncate text-xs">
            {version.original_filename} · {version.size_display}
          </p>
        ) : null}
      </div>

      {actions !== undefined ? <div className="shrink-0">{actions}</div> : null}
    </CardContent>
  );

  if (href === undefined) {
    return <Card className={className}>{body}</Card>;
  }

  return (
    <Card className={cn('hover:border-primary/50 focus-within:border-primary transition-colors', className)}>
      <Link href={href} className="block rounded-[inherit] outline-none">
        {body}
      </Link>
    </Card>
  );
}
