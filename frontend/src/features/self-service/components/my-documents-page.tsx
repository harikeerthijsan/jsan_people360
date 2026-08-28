'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { Download, Lock, Upload } from 'lucide-react';
import { useSearchParams } from 'next/navigation';
import * as React from 'react';
import { useForm } from 'react-hook-form';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { FileUpload } from '@/components/common/file-upload';
import { FormLayout, FormSection } from '@/components/common/form-layout';
import { Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { SelectField } from '@/components/common/select-field';
import { StatCard } from '@/components/common/stat-card';
import { TextField } from '@/components/common/text-field';
import { TextareaField } from '@/components/common/textarea-field';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Form } from '@/components/ui/form';
import { toast } from '@/components/ui/sonner';
import { selfServiceApi } from '@/features/self-service/api';
import {
  useMyDocumentTypes,
  useMyDocuments,
  useReplaceMyDocument,
  useUploadMyDocument,
} from '@/features/self-service/hooks';
import { myDocumentUploadSchema, type MyDocumentUploadFormValues } from '@/features/self-service/schema';
import type { MyDocument } from '@/features/self-service/types';
import {
  ACCEPTED_EXTENSIONS,
  DOCUMENT_STATUS_LABELS,
  MAX_UPLOAD_MB,
  type DocumentStatus,
} from '@/features/documents/types/document.types';

/**
 * My Documents.
 *
 * One list holding two kinds of thing: what the employee uploaded, and what HR
 * issued to them. They are not separated into tabs, because from the employee's
 * side it is simply "my paperwork" -- what differs is whether the replace action
 * is available, and that is decided by the server and carried on each row as
 * `can_replace`.
 *
 * A rejection shows its reason inline. A rejected document the employee cannot
 * act on would be a dead end.
 */

const STATUS_VARIANT: Record<string, 'success' | 'destructive' | 'warning' | 'outline'> = {
  approved: 'success',
  rejected: 'destructive',
  uploaded: 'warning',
  under_review: 'warning',
};

function validateFile(file: File): { message: string } | null {
  const extension = `.${file.name.split('.').pop()?.toLowerCase() ?? ''}`;
  if (!ACCEPTED_EXTENSIONS.includes(extension)) {
    return { message: `Only ${ACCEPTED_EXTENSIONS.join(', ')} files are accepted.` };
  }
  if (file.size > MAX_UPLOAD_MB * 1024 * 1024) {
    return { message: `The file is larger than the ${String(MAX_UPLOAD_MB)} MB limit.` };
  }
  return null;
}

export function MyDocumentsPage(): React.JSX.Element {
  const searchParams = useSearchParams();
  const [isUploading, setIsUploading] = React.useState(searchParams.get('upload') === '1');
  const [replacing, setReplacing] = React.useState<MyDocument | null>(null);
  const [file, setFile] = React.useState<File | null>(null);
  const [replacementFile, setReplacementFile] = React.useState<File | null>(null);

  const documents = useMyDocuments();
  const types = useMyDocumentTypes();
  const upload = useUploadMyDocument();
  const replace = useReplaceMyDocument();

  const form = useForm<MyDocumentUploadFormValues>({
    resolver: zodResolver(myDocumentUploadSchema),
    defaultValues: { name: '', document_type_id: '', description: '', expiry_date: '' },
  });

  const selectedTypeId = form.watch('document_type_id');
  const selectedType = (types.data ?? []).find((type) => type.id === selectedTypeId);

  const submitUpload = form.handleSubmit((values) => {
    if (!file) {
      toast.error('Choose a file first');
      return;
    }
    const chosen = (types.data ?? []).find((type) => type.id === values.document_type_id);
    if (!chosen) {
      toast.error('Choose a document type');
      return;
    }

    const body = new FormData();
    body.append('file', file);
    body.append('name', values.name);
    // The category comes from the chosen type rather than being picked
    // separately: a type belongs to exactly one category, and asking for both
    // invites a mismatch the server would have to reject.
    body.append('category_id', chosen.category_id);
    body.append('document_type_id', chosen.id);
    if (values.description) body.append('description', values.description);
    if (values.expiry_date) body.append('expiry_date', values.expiry_date);

    upload.mutate(body, {
      onSuccess: () => {
        setIsUploading(false);
        setFile(null);
        form.reset();
      },
    });
  });

  const submitReplacement = (): void => {
    if (!replacing || !replacementFile) {
      toast.error('Choose a file first');
      return;
    }
    const body = new FormData();
    body.append('file', replacementFile);
    body.append('notes', 'Replacement uploaded by the employee');

    replace.mutate(
      { id: replacing.id, form: body },
      {
        onSuccess: () => {
          setReplacing(null);
          setReplacementFile(null);
        },
      },
    );
  };

  const download = (document: MyDocument): void => {
    const filename = document.current_version?.original_filename ?? `${document.document_code}.pdf`;
    void selfServiceApi.downloadDocument(document.id, filename).catch(() => {
      toast.error('Could not download this document');
    });
  };

  const columns: DataTableColumn<MyDocument>[] = [
    {
      id: 'name',
      header: 'Document',
      cell: (row) => (
        <div className="min-w-0">
          <p className="truncate font-medium">{row.name}</p>
          <p className="text-muted-foreground truncate text-xs">
            {row.document_code}
            {row.can_replace ? '' : ' · issued by HR'}
          </p>
        </div>
      ),
    },
    { id: 'type', header: 'Type', cell: (row) => row.document_type?.name ?? '—' },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <div className="space-y-1">
          <Badge variant={STATUS_VARIANT[row.status] ?? 'outline'}>
            {DOCUMENT_STATUS_LABELS[row.status as DocumentStatus] ?? row.status}
          </Badge>
          {row.status === 'rejected' && row.review_notes ? (
            <p className="text-destructive max-w-64 text-xs">{row.review_notes}</p>
          ) : null}
        </div>
      ),
    },
    {
      id: 'expiry',
      header: 'Expires',
      cell: (row) => <span className="tabular-nums">{row.expiry_date ?? '—'}</span>,
    },
    {
      id: 'versions',
      header: 'Versions',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{row.version_count}</span>,
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) => (
        <div className="flex justify-end gap-1.5">
          <Button
            aria-label={`Download ${row.name}`}
            onClick={() => {
              download(row);
            }}
            size="sm"
            variant="outline"
          >
            <Download className="size-4" aria-hidden="true" />
          </Button>
          {row.can_replace ? (
            <Button
              onClick={() => {
                setReplacing(row);
              }}
              size="sm"
              variant="outline"
            >
              Replace
            </Button>
          ) : (
            <Button aria-label="Issued by HR; read only" disabled size="sm" variant="ghost">
              <Lock className="size-4" aria-hidden="true" />
            </Button>
          )}
        </div>
      ),
    },
  ];

  const rows = documents.data?.items ?? [];
  const counts = {
    total: documents.data?.meta.total_items ?? 0,
    pending: rows.filter((row) => row.status === 'uploaded' || row.status === 'under_review').length,
    approved: rows.filter((row) => row.status === 'approved').length,
    rejected: rows.filter((row) => row.status === 'rejected').length,
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Documents"
        description="What you have uploaded, and what HR has issued to you."
        actions={
          <Button
            onClick={() => {
              setIsUploading(true);
            }}
          >
            <Upload className="size-4" aria-hidden="true" />
            Upload a document
          </Button>
        }
      />

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard label="All documents" value={counts.total} />
        <StatCard hint="on this page" label="Awaiting review" value={counts.pending} />
        <StatCard hint="on this page" label="Approved" value={counts.approved} />
        <StatCard hint="upload a replacement" label="Rejected" value={counts.rejected} />
      </div>

      <DataTable
        columns={columns}
        emptyDescription="Upload an identity, education, employment or bank document to get started."
        emptyTitle="Nothing filed yet"
        error={documents.error}
        getRowId={(row) => row.id}
        isLoading={documents.isPending}
        onRetry={() => void documents.refetch()}
        rows={rows}
      />

      <Modal
        description="It is filed against you and sent to HR for review."
        onOpenChange={setIsUploading}
        open={isUploading}
        size="lg"
        title="Upload a document"
        footer={
          <>
            <Button
              onClick={() => {
                setIsUploading(false);
              }}
              variant="outline"
            >
              Cancel
            </Button>
            <Button isLoading={upload.isPending} onClick={() => void submitUpload()}>
              Upload
            </Button>
          </>
        }
      >
        <Form {...form}>
          <FormLayout onSubmit={(event) => void submitUpload(event)}>
            <FormSection title="The document">
              <TextField control={form.control} label="Name" name="name" required />
              <SelectField
                control={form.control}
                isLoading={types.isPending}
                label="Type"
                name="document_type_id"
                options={(types.data ?? []).map((type) => ({
                  value: type.id,
                  label: type.name,
                  hint: type.category_name,
                }))}
                required
              />
              <TextField
                control={form.control}
                description={
                  selectedType?.requires_expiry ? 'Required for this type.' : 'Optional for this type.'
                }
                label="Expires on"
                name="expiry_date"
                type="date"
              />
              <div />
              <TextareaField
                className="sm:col-span-2"
                control={form.control}
                label="Description"
                name="description"
                rows={2}
              />
            </FormSection>

            <FileUpload
              accept={ACCEPTED_EXTENSIONS.join(',')}
              hint={`PDF, JPG or PNG, up to ${String(MAX_UPLOAD_MB)} MB`}
              isUploading={upload.isPending}
              onSelect={setFile}
              validate={validateFile}
            />
          </FormLayout>
        </Form>
      </Modal>

      <Modal
        description={
          replacing?.review_notes
            ? `Rejected: ${replacing.review_notes}`
            : 'The previous version is kept and stays downloadable.'
        }
        onOpenChange={(open) => {
          if (!open) {
            setReplacing(null);
            setReplacementFile(null);
          }
        }}
        open={replacing !== null}
        title={`Replace ${replacing?.name ?? 'document'}`}
        footer={
          <>
            <Button
              onClick={() => {
                setReplacing(null);
              }}
              variant="outline"
            >
              Cancel
            </Button>
            <Button isLoading={replace.isPending} onClick={submitReplacement}>
              Upload replacement
            </Button>
          </>
        }
      >
        <FileUpload
          accept={ACCEPTED_EXTENSIONS.join(',')}
          hint={`PDF, JPG or PNG, up to ${String(MAX_UPLOAD_MB)} MB`}
          isUploading={replace.isPending}
          onSelect={setReplacementFile}
          validate={validateFile}
        />
      </Modal>
    </div>
  );
}
