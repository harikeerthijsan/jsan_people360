'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { ArchiveRestore, ArrowLeft, CheckCircle2, Download, Eye, FileUp, Pencil, Trash2 } from 'lucide-react';
import { useRouter } from 'next/navigation';
import * as React from 'react';
import { useForm, type FieldValues, type Resolver } from 'react-hook-form';

import { DetailSection } from '@/components/common/detail-view';
import { DocumentStatusBadge, ExpiryBadge } from '@/components/common/document-status-badge';
import { ErrorState } from '@/components/common/error-state';
import { FilePreviewModal } from '@/components/common/file-preview';
import { FileUpload } from '@/components/common/file-upload';
import { LoadingState } from '@/components/common/loading-state';
import { ConfirmDialog, Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { SelectField } from '@/components/common/select-field';
import { Tabs, type TabDefinition } from '@/components/common/tabs';
import { TextField } from '@/components/common/text-field';
import { TextareaField } from '@/components/common/textarea-field';
import { Timeline, type TimelineItem } from '@/components/common/timeline';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { Form } from '@/components/ui/form';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Textarea } from '@/components/ui/textarea';
import { VersionTimeline } from '@/features/documents/components/version-timeline';
import {
  useDocument,
  useDocumentAudit,
  useDocumentAction,
  useDocumentCategories,
  useDocumentPreview,
  useDocumentTypes,
  useDocumentVersions,
  useDownloadDocument,
  useReviewDocument,
  useUpdateDocument,
  useUploadVersion,
} from '@/features/documents/hooks/use-documents';
import { editDocumentSchema, validateFile } from '@/features/documents/schemas/document.schemas';
import {
  ACCEPTED_EXTENSIONS,
  DOCUMENT_STATUS_LABELS,
  MAX_UPLOAD_MB,
  OWNER_TYPE_LABELS,
  REVIEWABLE_STATUSES,
  type DocumentRecord,
  type DocumentStatus,
  type DocumentVersionRecord,
} from '@/features/documents/types/document.types';
import { useDisclosure } from '@/hooks/use-disclosure';
import { useUser } from '@/features/users/hooks/use-users';
import { formatDate, formatDateTime } from '@/lib/utils';

const BASE_PATH = '/documents';

const TABS: TabDefinition[] = [
  { id: 'details', label: 'Details' },
  { id: 'versions', label: 'Version history' },
  { id: 'audit', label: 'Audit history' },
];

interface DocumentDetailPageProps {
  documentId: string;
}

export function DocumentDetailPage({ documentId }: DocumentDetailPageProps): React.JSX.Element {
  const router = useRouter();
  const documentQuery = useDocument(documentId);
  const versionsQuery = useDocumentVersions(documentId);

  const download = useDownloadDocument();
  const archive = useDocumentAction('archive');
  const restore = useDocumentAction('restore');

  const preview = useDisclosure(false);
  const review = useDisclosure(false);
  const edit = useDisclosure(false);
  const newVersion = useDisclosure(false);
  const confirmArchive = useDisclosure(false);

  // Which version the preview is showing. Null means the current one.
  const [previewVersion, setPreviewVersion] = React.useState<DocumentVersionRecord | null>(null);

  const previewState = useDocumentPreview(documentId, previewVersion?.id, preview.isOpen);

  if (documentQuery.isPending) return <LoadingState message="Loading document" />;
  if (documentQuery.error) {
    return (
      <ErrorState
        error={documentQuery.error}
        onRetry={() => {
          void documentQuery.refetch();
        }}
      />
    );
  }

  const document = documentQuery.data;
  const isArchived = document.deleted_at !== null;
  const current = document.current_version;

  const openPreview = (version: DocumentVersionRecord | null) => {
    setPreviewVersion(version);
    preview.open();
  };

  const startDownload = (version: DocumentVersionRecord | null) => {
    const target = version ?? current;
    if (!target) return;
    download.mutate({
      id: document.id,
      filename: target.original_filename,
      versionId: version?.id,
    });
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title={document.name}
        description={document.document_code}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              onClick={() => {
                router.push(BASE_PATH);
              }}
            >
              <ArrowLeft aria-hidden="true" />
              Back
            </Button>

            {current ? (
              <>
                <Button
                  variant="outline"
                  onClick={() => {
                    openPreview(null);
                  }}
                >
                  <Eye aria-hidden="true" />
                  Preview
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    startDownload(null);
                  }}
                  isLoading={download.isPending}
                >
                  <Download aria-hidden="true" />
                  Download
                </Button>
              </>
            ) : null}

            {isArchived ? (
              <Button
                onClick={() => {
                  restore.mutate(document.id);
                }}
                isLoading={restore.isPending}
              >
                <ArchiveRestore aria-hidden="true" />
                Restore
              </Button>
            ) : (
              <>
                <Button variant="outline" onClick={edit.open}>
                  <Pencil aria-hidden="true" />
                  Edit
                </Button>
                <Button variant="outline" onClick={newVersion.open}>
                  <FileUp aria-hidden="true" />
                  New version
                </Button>
                <Button variant="outline" onClick={review.open}>
                  <CheckCircle2 aria-hidden="true" />
                  Review
                </Button>
                <Button variant="destructive" onClick={confirmArchive.open}>
                  <Trash2 aria-hidden="true" />
                  Archive
                </Button>
              </>
            )}
          </div>
        }
      />

      <Card>
        <CardContent className="flex flex-wrap items-center gap-2 p-4">
          <DocumentStatusBadge status={document.status} archived={isArchived} />
          <ExpiryBadge
            state={document.expiry_state}
            detail={document.expiry_date ? formatDate(document.expiry_date) : undefined}
          />
          {document.version_count > 1 ? (
            <Badge variant="secondary">{document.version_count} versions</Badge>
          ) : null}
          {document.owner?.display_name ? (
            <span className="text-muted-foreground ml-auto text-sm">
              {OWNER_TYPE_LABELS[document.owner_type]} · {document.owner.display_name}
            </span>
          ) : null}
        </CardContent>
      </Card>

      <Tabs tabs={TABS} label="Document sections" defaultTabId="details">
        {(tab) =>
          tab === 'versions' ? (
            <VersionsTab
              documentId={documentId}
              currentVersionId={current?.id ?? null}
              versions={versionsQuery.data ?? []}
              isPending={versionsQuery.isPending}
              onPreview={openPreview}
              onDownload={startDownload}
            />
          ) : tab === 'audit' ? (
            <AuditTab documentId={documentId} />
          ) : (
            <DetailsTab document={document} />
          )
        }
      </Tabs>

      <FilePreviewModal
        open={preview.isOpen}
        onOpenChange={(open) => {
          preview.setOpen(open);
          if (!open) setPreviewVersion(null);
        }}
        title={document.name}
        description={
          previewVersion
            ? `Version ${String(previewVersion.version_number)} · ${previewVersion.original_filename}`
            : current?.original_filename
        }
        filename={(previewVersion ?? current)?.original_filename ?? document.name}
        contentType={(previewVersion ?? current)?.content_type ?? ''}
        url={previewState.url}
        isLoading={previewState.isLoading}
        error={previewState.error}
        onDownload={() => {
          startDownload(previewVersion);
        }}
      />

      <EditDialog document={document} open={edit.isOpen} onOpenChange={edit.setOpen} />

      <NewVersionDialog documentId={documentId} open={newVersion.isOpen} onOpenChange={newVersion.setOpen} />

      <ReviewDialog
        documentId={documentId}
        currentStatus={document.status}
        open={review.isOpen}
        onOpenChange={review.setOpen}
      />

      <ConfirmDialog
        open={confirmArchive.isOpen}
        onOpenChange={confirmArchive.setOpen}
        title="Archive this document?"
        description={`"${document.name}" will be hidden from the vault. Every version is kept, nothing is deleted from storage, and you can restore it at any time.`}
        confirmLabel="Archive"
        destructive
        isConfirming={archive.isPending}
        onConfirm={() => {
          archive.mutate(document.id, { onSettled: confirmArchive.close });
        }}
      />
    </div>
  );
}

// ---------------------------------------------------------------------------
function DetailsTab({ document }: { document: DocumentRecord }): React.JSX.Element {
  const version = document.current_version;

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <DetailSection
        title="Document"
        items={[
          {
            label: 'Document ID',
            value: <span className="font-mono text-xs">{document.document_code}</span>,
          },
          { label: 'Name', value: document.name },
          { label: 'Category', value: document.category?.name },
          { label: 'Type', value: document.document_type?.name },
          { label: 'Status', value: DOCUMENT_STATUS_LABELS[document.status] },
          {
            label: 'Expiry date',
            value: document.expiry_date ? formatDate(document.expiry_date) : null,
          },
          { label: 'Description', value: document.description, wide: true },
        ]}
      />

      <DetailSection
        title="Current file"
        items={
          version
            ? [
                { label: 'File name', value: version.original_filename },
                { label: 'Size', value: version.size_display },
                { label: 'Type', value: version.content_type },
                { label: 'Version', value: `v${String(version.version_number)}` },
                { label: 'Uploaded', value: formatDateTime(version.created_at) },
                {
                  label: 'Checksum',
                  // Truncated: the whole hash is 64 characters and nobody reads
                  // it, but the first few confirm two files are the same.
                  value: (
                    <span className="font-mono text-xs" title={version.checksum}>
                      {version.checksum.slice(0, 16)}…
                    </span>
                  ),
                  wide: true,
                },
              ]
            : [{ label: 'File', value: null }]
        }
      />

      <DetailSection
        title="Owner"
        items={[
          { label: 'Owner type', value: OWNER_TYPE_LABELS[document.owner_type] },
          { label: 'Belongs to', value: document.owner?.display_name },
          { label: 'Reference', value: document.owner?.reference_code },
        ]}
      />

      <DetailSection
        title="Review and record"
        items={[
          { label: 'Status', value: DOCUMENT_STATUS_LABELS[document.status] },
          {
            label: 'Reviewed',
            value: document.reviewed_at ? formatDateTime(document.reviewed_at) : null,
          },
          { label: 'Review notes', value: document.review_notes, wide: true },
          { label: 'Uploaded by', value: <UploadedBy userId={document.created_by} /> },
          { label: 'Uploaded', value: formatDateTime(document.created_at) },
          { label: 'Last updated', value: formatDateTime(document.updated_at) },
        ]}
      />
    </div>
  );
}

function UploadedBy({ userId }: { userId: string | null }): React.JSX.Element {
  const user = useUser(userId ?? undefined);
  if (!userId) return <span>System</span>;
  if (user.isPending) return <span>Loading…</span>;
  return <span>{user.data?.full_name ?? user.data?.email ?? userId}</span>;
}

function AuditTab({ documentId }: { documentId: string }): React.JSX.Element {
  const audit = useDocumentAudit(documentId);
  if (audit.isPending) return <LoadingState message="Loading audit history" />;
  if (audit.error)
    return (
      <ErrorState
        error={audit.error}
        onRetry={() => {
          void audit.refetch();
        }}
      />
    );
  if (audit.data.length === 0)
    return (
      <Card>
        <CardContent className="text-muted-foreground p-6 text-sm">
          Nothing recorded against this document yet.
        </CardContent>
      </Card>
    );
  const items: TimelineItem[] = audit.data.map((entry) => ({
    id: entry.id,
    title: <span className="font-mono text-xs">{entry.action}</span>,
    timestamp: formatDateTime(entry.created_at),
    description: entry.description,
    meta: entry.actor_email ? <p>By {entry.actor_email}</p> : null,
    highlighted: entry.action === 'document.downloaded',
  }));
  return (
    <Card>
      <CardContent className="p-6">
        <Timeline items={items} />
      </CardContent>
    </Card>
  );
}

function VersionsTab({
  currentVersionId,
  versions,
  isPending,
  onPreview,
  onDownload,
}: {
  documentId: string;
  currentVersionId: string | null;
  versions: DocumentVersionRecord[];
  isPending: boolean;
  onPreview: (version: DocumentVersionRecord) => void;
  onDownload: (version: DocumentVersionRecord) => void;
}): React.JSX.Element {
  if (isPending) return <LoadingState message="Loading version history" />;

  if (versions.length === 0) {
    return (
      <Card>
        <CardContent className="text-muted-foreground p-6 text-sm">No versions recorded yet.</CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardContent className="p-6">
        <VersionTimeline
          versions={versions}
          currentVersionId={currentVersionId}
          onPreview={onPreview}
          onDownload={onDownload}
        />
        <p className="text-muted-foreground mt-6 text-xs">
          Uploading a new version never replaces an old one. Every file above remains stored and downloadable.
        </p>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
function NewVersionDialog({
  documentId,
  open,
  onOpenChange,
}: {
  documentId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}): React.JSX.Element {
  const upload = useUploadVersion(documentId);
  const [file, setFile] = React.useState<File | null>(null);
  const [notes, setNotes] = React.useState('');

  const submit = () => {
    if (!file) return;
    upload.mutate(
      { file, notes: notes.trim() || null },
      {
        onSuccess: () => {
          setFile(null);
          setNotes('');
          onOpenChange(false);
        },
      },
    );
  };

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title="Upload a new version"
      description="The current file is kept and stays downloadable. Nothing is overwritten."
      size="md"
      confirmLabel="Upload version"
      onConfirm={submit}
      isConfirming={upload.isPending}
    >
      <div className="space-y-4">
        <FileUpload
          onSelect={setFile}
          validate={validateFile}
          accept={ACCEPTED_EXTENSIONS.join(',')}
          progress={upload.progress}
          isUploading={upload.isPending}
          hint={`Up to ${String(MAX_UPLOAD_MB)} MB`}
        />

        <div className="space-y-1.5">
          <label htmlFor="version-notes" className="text-sm font-medium">
            Why this version?
          </label>
          <Textarea
            id="version-notes"
            rows={2}
            value={notes}
            onChange={(event) => {
              setNotes(event.target.value);
            }}
            placeholder="Renewed, corrected, re-signed…"
            disabled={upload.isPending}
          />
        </div>
      </div>
    </Modal>
  );
}

/**
 * Correct a document's metadata.
 *
 * The file is deliberately not here: it is replaced by uploading a version, and
 * never by editing. What this changes is everything *around* the file — the
 * name it is filed under, where it sits, and when it expires. Without it a typo
 * or a wrong expiry date was permanent, which mattered most for expiry: renewing
 * a passport gave you a new version but no way to move the date.
 */
function EditDialog({
  document,
  open,
  onOpenChange,
}: {
  document: DocumentRecord;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}): React.JSX.Element {
  const update = useUpdateDocument(document.id);

  const form = useForm<FieldValues>({
    resolver: zodResolver(editDocumentSchema) as Resolver<FieldValues>,
    mode: 'onSubmit',
  });

  const categoryId = form.watch('category_id') as string | undefined;
  const categories = useDocumentCategories();
  const types = useDocumentTypes(categoryId || undefined);

  // Reset from the record each time the dialog opens, so cancelling and
  // reopening shows what is stored rather than the abandoned edit.
  React.useEffect(() => {
    if (!open) return;
    form.reset({
      name: document.name,
      description: document.description ?? '',
      category_id: document.category_id,
      document_type_id: document.document_type_id,
      expiry_date: document.expiry_date ?? '',
    });
  }, [document, form, open]);

  React.useEffect(() => {
    if (!update.error) return;
    for (const [field, message] of Object.entries(update.error.fieldErrorMap)) {
      form.setError(field, { type: 'server', message });
    }
  }, [update.error, form]);

  const submit = form.handleSubmit((values) => {
    update.mutate(values, { onSuccess: () => onOpenChange(false) });
  });

  const generalError =
    update.error && Object.keys(update.error.fieldErrorMap).length === 0 ? update.error.message : null;

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title="Edit document"
      description="Changes the details. The file itself is replaced by uploading a new version."
      size="md"
      confirmLabel="Save changes"
      onConfirm={() => void submit()}
      isConfirming={update.isPending}
    >
      <Form {...form}>
        <form
          className="space-y-4"
          onSubmit={(event) => {
            event.preventDefault();
            void submit();
          }}
        >
          {generalError ? (
            <Alert variant="destructive">
              <AlertDescription>{generalError}</AlertDescription>
            </Alert>
          ) : null}

          <TextField control={form.control} name="name" label="Document name" required />

          <div className="grid gap-4 sm:grid-cols-2">
            <SelectField
              control={form.control}
              name="category_id"
              label="Category"
              options={(categories.data?.items ?? []).map((item) => ({
                value: item.id,
                label: item.name,
                hint: item.code,
              }))}
              isLoading={categories.isPending}
              emptyMessage="No active categories"
              required
            />
            <SelectField
              control={form.control}
              name="document_type_id"
              label="Document type"
              options={(types.data?.items ?? []).map((item) => ({
                value: item.id,
                label: item.name,
                hint: item.requires_expiry ? 'Expiry required' : item.code,
              }))}
              isLoading={Boolean(categoryId) && types.isPending}
              emptyMessage="No active types in this category"
              required
            />
          </div>

          <TextField
            control={form.control}
            name="expiry_date"
            label="Expiry date"
            type="date"
            description="Required for some types, such as a passport."
          />
          <TextareaField control={form.control} name="description" label="Description" rows={3} />
        </form>
      </Form>
    </Modal>
  );
}

function ReviewDialog({
  documentId,
  currentStatus,
  open,
  onOpenChange,
}: {
  documentId: string;
  currentStatus: DocumentStatus;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}): React.JSX.Element {
  const review = useReviewDocument(documentId);
  const [status, setStatus] = React.useState<DocumentStatus>('approved');
  const [notes, setNotes] = React.useState('');

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title="Record a review"
      description="Marks the document as under review, approved or rejected."
      size="sm"
      confirmLabel="Record review"
      isConfirming={review.isPending}
      onConfirm={() => {
        review.mutate(
          { status, review_notes: notes.trim() || null },
          {
            onSuccess: () => {
              setNotes('');
              onOpenChange(false);
            },
          },
        );
      }}
    >
      <div className="space-y-4">
        <div className="space-y-1.5">
          <label htmlFor="review-status" className="text-sm font-medium">
            Decision
          </label>
          <Select
            value={status}
            onValueChange={(value) => {
              setStatus(value as DocumentStatus);
            }}
          >
            <SelectTrigger id="review-status">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {REVIEWABLE_STATUSES.map((option) => (
                <SelectItem key={option} value={option} disabled={option === currentStatus}>
                  {DOCUMENT_STATUS_LABELS[option]}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-1.5">
          <label htmlFor="review-notes" className="text-sm font-medium">
            Notes
          </label>
          <Textarea
            id="review-notes"
            rows={3}
            value={notes}
            onChange={(event) => {
              setNotes(event.target.value);
            }}
            placeholder="Verified against the original…"
            disabled={review.isPending}
          />
        </div>
      </div>
    </Modal>
  );
}
