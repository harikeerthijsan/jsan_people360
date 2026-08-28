'use client';

import { useMutation, useQueryClient } from '@tanstack/react-query';
import { ArchiveRestore, Pencil, Plus, Power, Trash2 } from 'lucide-react';
import * as React from 'react';
import type { ZodError, ZodType } from 'zod';

import { ActionMenu, type ActionMenuItem } from '@/components/common/action-menu';
import { EmptyState } from '@/components/common/empty-state';
import { ConfirmDialog, Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { StatusBadge } from '@/components/common/status-badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from '@/components/ui/sonner';
import { Textarea } from '@/components/ui/textarea';
import { useDocumentCategories, useDocumentMasters } from '@/features/documents/hooks/use-documents';
import { documentCategorySchema, documentTypeSchema } from '@/features/documents/schemas/document.schemas';
import type { DocumentCategoryRecord, DocumentTypeRecord } from '@/features/documents/types/document.types';
import { useDisclosure } from '@/hooks/use-disclosure';
import { api } from '@/lib/api/client';
import { endpoints } from '@/lib/api/endpoints';
import type { AppError } from '@/lib/errors';
import { queryKeys } from '@/lib/query-client';

/**
 * Administration for the two document masters.
 *
 * Categories and types have the same six endpoints as the nine organization
 * masters, so they get the same lifecycle here: create, edit, deactivate and
 * archive, each with its counterpart. A create-only screen left an operator
 * unable to correct a typo or retire a type they no longer use, with the API
 * fully able to do both.
 *
 * The two masters differ only in their fields, so one editor and one list serve
 * both, driven by the record shape.
 */

type MasterRow = DocumentCategoryRecord | DocumentTypeRecord;

interface Draft {
  name: string;
  code: string;
  description: string;
  status: string;
  // Category only.
  display_order: string;
  // Type only.
  category_id: string;
  requires_expiry: boolean;
  is_sensitive: boolean;
  allowed_extensions: string;
}

const BLANK: Draft = {
  name: '',
  code: '',
  description: '',
  status: 'active',
  display_order: '100',
  category_id: '',
  requires_expiry: false,
  is_sensitive: false,
  allowed_extensions: '',
};

function isType(row: MasterRow): row is DocumentTypeRecord {
  return 'category_id' in row;
}

/** Fill a draft from an existing record, so the editor opens on what is stored. */
function toDraft(row: MasterRow): Draft {
  const base: Draft = {
    ...BLANK,
    name: row.name,
    code: row.code,
    description: row.description ?? '',
    status: row.status,
  };

  if (isType(row)) {
    return {
      ...base,
      category_id: row.category_id,
      requires_expiry: row.requires_expiry,
      is_sensitive: row.is_sensitive,
      allowed_extensions: row.allowed_extensions ?? '',
    };
  }
  return { ...base, display_order: String(row.display_order) };
}

/**
 * The first problem, phrased for a person.
 *
 * A `ZodError`'s own `message` is a JSON dump of every issue, so showing it
 * directly puts `[ { "code": "too_small", … } ]` in front of the user.
 * Validation therefore happens before the mutation, and only the message a
 * human wrote reaches the screen.
 */
function firstIssue(error: ZodError): string {
  return error.issues[0]?.message ?? 'Check the values and try again.';
}

export function DocumentSettingsPage(): React.JSX.Element {
  // The active, live categories a *type* may be assigned to — not the same set
  // the panel below lists, which includes what an administrator must manage.
  const assignable = useDocumentCategories();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Document categories and types"
        description="Configure how files are classified throughout People360."
      />

      <div className="grid gap-6 xl:grid-cols-2">
        <MasterPanel
          title="Categories"
          singular="category"
          kind="categories"
          endpoint={endpoints.documents.categories}
          schema={documentCategorySchema}
        />
        <MasterPanel
          title="Document types"
          singular="document type"
          kind="types"
          endpoint={endpoints.documents.types}
          schema={documentTypeSchema}
          categories={assignable.data?.items ?? []}
        />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
function MasterPanel({
  title,
  singular,
  kind,
  endpoint,
  schema,
  categories,
}: {
  title: string;
  /** Used in button labels and confirmations, so it reads as a sentence. */
  singular: string;
  kind: 'categories' | 'types';
  endpoint: string;
  schema: ZodType;
  categories?: DocumentCategoryRecord[];
}): React.JSX.Element {
  const queryClient = useQueryClient();
  const editor = useDisclosure(false);
  const confirmArchive = useDisclosure(false);
  const [showArchived, setShowArchived] = React.useState(false);

  const listQuery = useDocumentMasters(kind, showArchived);
  const rows = (listQuery.data?.items ?? []) as MasterRow[];
  const isLoading = listQuery.isPending;

  const [draft, setDraft] = React.useState<Draft>(BLANK);
  const [editing, setEditing] = React.useState<MasterRow | null>(null);
  const [pending, setPending] = React.useState<MasterRow | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  // Both masters live under the documents key, so one invalidation refreshes
  // the lists *and* every picker that offers them.
  const refresh = React.useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.documents.root });
  }, [queryClient]);

  const save = useMutation<MasterRow, AppError, { id: string | null; values: unknown }>({
    mutationFn: ({ id, values }) =>
      id === null ? api.post<MasterRow>(endpoint, values) : api.patch<MasterRow>(`${endpoint}/${id}`, values),
    onSuccess: (record, { id }) => {
      refresh();
      editor.close();
      setError(null);
      toast.success(id === null ? `Added ${record.name}` : `Updated ${record.name}`);
    },
    onError: (caught) => setError(caught.message),
  });

  const lifecycle = useMutation<MasterRow, AppError, { row: MasterRow; action: 'archive' | 'restore' }>({
    mutationFn: ({ row, action }) => api.post<MasterRow>(`${endpoint}/${row.id}/${action}`),
    onSuccess: (record, { action }) => {
      refresh();
      confirmArchive.close();
      toast.success(action === 'archive' ? `Archived ${record.name}` : `Restored ${record.name}`);
    },
    onError: (caught, { action }) => {
      confirmArchive.close();
      toast.error(`Could not ${action} this ${singular}`, { description: caught.message });
    },
  });

  const openCreate = () => {
    setEditing(null);
    setDraft({ ...BLANK, category_id: categories?.[0]?.id ?? '' });
    setError(null);
    editor.open();
  };

  const openEdit = (row: MasterRow) => {
    setEditing(row);
    setDraft(toDraft(row));
    setError(null);
    editor.open();
  };

  const submit = () => {
    const parsed = schema.safeParse(draft);
    if (!parsed.success) {
      setError(firstIssue(parsed.error));
      return;
    }
    setError(null);
    save.mutate({ id: editing?.id ?? null, values: parsed.data });
  };

  /** Deactivating is an ordinary edit, so it goes through the same endpoint. */
  const toggleStatus = (row: MasterRow) => {
    const next = row.status === 'active' ? 'inactive' : 'active';
    save.mutate({ id: row.id, values: { status: next } });
  };

  const actionsFor = (row: MasterRow): ActionMenuItem[] =>
    row.deleted_at !== null
      ? [
          {
            id: 'restore',
            label: 'Restore',
            icon: ArchiveRestore,
            onSelect: () => {
              lifecycle.mutate({ row, action: 'restore' });
            },
          },
        ]
      : [
          { id: 'edit', label: 'Edit', icon: Pencil, onSelect: () => openEdit(row) },
          {
            id: 'status',
            label: row.status === 'active' ? 'Deactivate' : 'Activate',
            icon: Power,
            onSelect: () => toggleStatus(row),
          },
          {
            id: 'archive',
            label: 'Archive',
            icon: Trash2,
            destructive: true,
            onSelect: () => {
              setPending(row);
              confirmArchive.open();
            },
          },
        ];

  return (
    <Card>
      <CardHeader className="flex flex-row flex-wrap items-center justify-between gap-3 space-y-0">
        <CardTitle>{title}</CardTitle>
        <div className="flex items-center gap-3">
          <Check
            label="Show archived"
            checked={showArchived}
            onChange={(value) => {
              setShowArchived(value);
            }}
          />
          <Button size="sm" onClick={openCreate} disabled={showArchived}>
            <Plus aria-hidden="true" />
            Add {singular}
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-2">
        {isLoading ? (
          <p className="text-muted-foreground text-sm">Loading…</p>
        ) : rows.length === 0 ? (
          <EmptyState
            title="Nothing configured"
            description={
              showArchived
                ? `No archived ${singular} records.`
                : `The vault cannot file anything until at least one ${singular} exists.`
            }
            action={showArchived ? undefined : { label: `Add ${singular}`, onClick: openCreate }}
          />
        ) : (
          rows.map((row) => (
            <div key={row.id} className="flex items-center justify-between gap-3 rounded-md border p-3">
              <div className="min-w-0">
                <p className="truncate font-medium">{row.name}</p>
                <p className="text-muted-foreground truncate font-mono text-xs">{row.code}</p>
              </div>
              <div className="flex shrink-0 items-center gap-2">
                <StatusBadge status={row.status} archived={row.deleted_at !== null} />
                <ActionMenu items={actionsFor(row)} label={`Actions for ${row.name}`} />
              </div>
            </div>
          ))
        )}
      </CardContent>

      <MasterEditor
        open={editor.isOpen}
        onOpenChange={editor.setOpen}
        title={editing === null ? `Add ${singular}` : `Edit ${editing.name}`}
        singular={singular}
        draft={draft}
        setDraft={setDraft}
        categories={categories}
        error={error}
        onSubmit={submit}
        saving={save.isPending}
      />

      <ConfirmDialog
        open={confirmArchive.isOpen}
        onOpenChange={confirmArchive.setOpen}
        title={`Archive this ${singular}?`}
        description={
          pending
            ? `"${pending.name}" will be hidden and can no longer be chosen. Documents already filed under it keep working, and you can restore it at any time.`
            : ''
        }
        confirmLabel="Archive"
        destructive
        isConfirming={lifecycle.isPending}
        onConfirm={() => {
          if (pending) lifecycle.mutate({ row: pending, action: 'archive' });
        }}
      />
    </Card>
  );
}

// ---------------------------------------------------------------------------
function MasterEditor({
  open,
  onOpenChange,
  title,
  singular,
  draft,
  setDraft,
  categories,
  error,
  onSubmit,
  saving,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  singular: string;
  draft: Draft;
  setDraft: React.Dispatch<React.SetStateAction<Draft>>;
  categories?: DocumentCategoryRecord[];
  error: string | null;
  onSubmit: () => void;
  saving: boolean;
}): React.JSX.Element {
  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => {
    setDraft((current) => ({ ...current, [key]: value }));
  };

  const forType = categories !== undefined;

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title={title}
      description={`How a ${singular} appears wherever documents are classified.`}
      size="md"
      confirmLabel="Save"
      onConfirm={onSubmit}
      isConfirming={saving}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <TextInput label="Name" value={draft.name} onChange={(value) => set('name', value)} />
        <TextInput label="Code" value={draft.code} onChange={(value) => set('code', value)} />

        {forType ? (
          <>
            <div className="space-y-1.5">
              <Label htmlFor="editor-category">Category</Label>
              <select
                id="editor-category"
                className="border-input bg-background h-10 w-full rounded-md border px-3 text-sm"
                value={draft.category_id}
                onChange={(event) => set('category_id', event.target.value)}
              >
                <option value="">Choose category</option>
                {categories.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                  </option>
                ))}
              </select>
            </div>
            <TextInput
              label="Allowed extensions"
              value={draft.allowed_extensions}
              placeholder=".pdf,.jpg"
              optional
              onChange={(value) => set('allowed_extensions', value)}
            />
          </>
        ) : (
          <TextInput
            label="Display order"
            type="number"
            value={draft.display_order}
            onChange={(value) => set('display_order', value)}
          />
        )}

        <TextArea
          label="Description"
          value={draft.description}
          onChange={(value) => set('description', value)}
        />

        {forType ? (
          <>
            <Check
              label="Expiry date required"
              checked={draft.requires_expiry}
              onChange={(value) => set('requires_expiry', value)}
            />
            <Check
              label="Sensitive document"
              checked={draft.is_sensitive}
              onChange={(value) => set('is_sensitive', value)}
            />
          </>
        ) : null}

        {error ? (
          <p role="alert" className="text-destructive text-sm sm:col-span-2">
            {error}
          </p>
        ) : null}
      </div>
    </Modal>
  );
}

function TextInput({
  label,
  value,
  onChange,
  type = 'text',
  placeholder,
  optional = false,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
  placeholder?: string;
  optional?: boolean;
}): React.JSX.Element {
  const id = React.useId();
  return (
    <div className="space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input
        id={id}
        type={type}
        value={value}
        placeholder={placeholder}
        required={!optional}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  );
}

function TextArea({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}): React.JSX.Element {
  const id = React.useId();
  return (
    <div className="space-y-1.5 sm:col-span-2">
      <Label htmlFor={id}>{label}</Label>
      <Textarea id={id} value={value} onChange={(event) => onChange(event.target.value)} />
    </div>
  );
}

function Check({
  label,
  checked,
  onChange,
}: {
  label: string;
  checked: boolean;
  onChange: (value: boolean) => void;
}): React.JSX.Element {
  const id = React.useId();
  return (
    <div className="flex items-center gap-2">
      <Checkbox id={id} checked={checked} onCheckedChange={(value) => onChange(value === true)} />
      <Label htmlFor={id}>{label}</Label>
    </div>
  );
}
