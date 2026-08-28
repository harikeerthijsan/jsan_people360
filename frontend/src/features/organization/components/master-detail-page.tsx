'use client';

import { ArchiveRestore, ArrowLeft, Pencil, Trash2 } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import * as React from 'react';

import { DetailSection, type DetailItem } from '@/components/common/detail-view';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { ConfirmDialog } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { StatusBadge } from '@/components/common/status-badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { MASTER_REGISTRY, type MasterConfig } from '@/features/organization/config/master-registry';
import {
  useArchiveMaster,
  useMasterRecord,
  useRestoreMaster,
} from '@/features/organization/hooks/use-masters';
import type { MasterSlug } from '@/features/organization/types/organization.types';
import { useDisclosure } from '@/hooks/use-disclosure';
import { formatDateTime } from '@/lib/utils';

interface MasterDetailPageProps {
  /** See the note on `MasterListPageProps.slug`. */
  slug: MasterSlug;
  recordId: string;
}

/** The read-only detail screen for every master. */
export function MasterDetailPage({ slug, recordId }: MasterDetailPageProps): React.JSX.Element {
  const config: MasterConfig = MASTER_REGISTRY[slug];
  const router = useRouter();
  const recordQuery = useMasterRecord(config.slug, recordId);
  const archive = useArchiveMaster(config.slug, config.label);
  const restore = useRestoreMaster(config.slug, config.label);
  const confirm = useDisclosure(false);

  const basePath = `/organization/${config.slug}`;

  if (recordQuery.isPending) {
    return <LoadingState message={`Loading ${config.label.toLowerCase()}…`} />;
  }

  if (recordQuery.isError) {
    return (
      <div className="space-y-6">
        <PageHeader title={config.label} />
        <ErrorState
          error={recordQuery.error}
          onRetry={() => {
            void recordQuery.refetch();
          }}
        />
      </div>
    );
  }

  const record = recordQuery.data;
  const isArchived = record.deleted_at !== null;

  const identityItems: DetailItem[] = [
    { label: 'Name', value: record.name },
    ...(record.code === undefined ? [] : [{ label: 'Code', value: record.code }]),
    { label: 'Status', value: <StatusBadge status={record.status} archived={isArchived} /> },
    ...config.detailItems(record),
    { label: 'Description', value: record.description, wide: true },
  ];

  const auditItems: DetailItem[] = [
    { label: 'Created', value: formatDateTime(record.created_at) },
    { label: 'Last updated', value: formatDateTime(record.updated_at) },
    ...(isArchived ? [{ label: 'Archived', value: formatDateTime(record.deleted_at) }] : []),
    { label: 'Record ID', value: <span className="font-mono text-xs">{record.id}</span>, wide: true },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={record.name}
        description={config.label}
        actions={
          <>
            <Button variant="outline" asChild>
              <Link href={basePath}>
                <ArrowLeft aria-hidden="true" />
                Back
              </Link>
            </Button>

            {isArchived ? (
              <Button
                onClick={() => {
                  restore.mutate(record.id);
                }}
                isLoading={restore.isPending}
              >
                <ArchiveRestore aria-hidden="true" />
                Restore
              </Button>
            ) : (
              <>
                <Button variant="outline" asChild>
                  <Link href={`${basePath}/${record.id}/edit`}>
                    <Pencil aria-hidden="true" />
                    Edit
                  </Link>
                </Button>
                <Button variant="destructive" onClick={confirm.open}>
                  <Trash2 aria-hidden="true" />
                  Archive
                </Button>
              </>
            )}
          </>
        }
      />

      {isArchived ? (
        <Alert variant="warning">
          <AlertDescription>
            This {config.label.toLowerCase()} is archived. It is hidden from new selections, and records that
            already reference it are unaffected.
          </AlertDescription>
        </Alert>
      ) : null}

      <div className="grid gap-6 lg:grid-cols-3">
        <DetailSection title="Details" items={identityItems} className="lg:col-span-2" />
        <DetailSection title="Record history" items={auditItems} />
      </div>

      <ConfirmDialog
        open={confirm.isOpen}
        onOpenChange={confirm.setOpen}
        title={`Archive this ${config.label.toLowerCase()}?`}
        description={`"${record.name}" will be hidden from new selections. Existing records that reference it keep working, and you can restore it at any time.`}
        confirmLabel="Archive"
        destructive
        isConfirming={archive.isPending}
        onConfirm={() => {
          archive.mutate(record.id, {
            onSuccess: () => {
              confirm.close();
              router.push(basePath);
            },
            onSettled: () => {
              confirm.close();
            },
          });
        }}
      />
    </div>
  );
}
