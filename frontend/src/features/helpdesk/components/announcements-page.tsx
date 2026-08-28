'use client';

import { Plus } from 'lucide-react';
import * as React from 'react';

import { usePermitted } from '@/components/common/can';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { Pagination } from '@/components/common/pagination';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  useAnnouncement,
  useAnnouncements,
  useArchiveAnnouncement,
  useCreateAnnouncement,
  usePublishAnnouncement,
  useUpdateAnnouncement,
} from '@/features/helpdesk/hooks';
import {
  ANNOUNCEMENT_AUDIENCE_LABELS,
  ANNOUNCEMENT_PRIORITY_LABELS,
  ANNOUNCEMENT_STATUS_LABELS,
  type Announcement,
  type AnnouncementAudience,
  type AnnouncementInput,
  type AnnouncementPriority,
  type AnnouncementStatus,
} from '@/features/helpdesk/types';

/**
 * Announcements, from the sender's side.
 *
 * Writing one and sending it are two acts with two permissions. That split is
 * the point of the module: an HR executive can draft the redundancy notice, and
 * only somebody holding `announcements:publish` decides it goes out. The Send
 * button is therefore gated separately from the composer, and the server
 * enforces the same thing whatever this screen renders.
 *
 * A published announcement can be amended and archived but not unpublished.
 * People have already read it; pretending otherwise would be a lie the audit
 * log would contradict.
 */

const STATUS_TONE: Record<AnnouncementStatus, 'default' | 'secondary' | 'outline'> = {
  draft: 'outline',
  scheduled: 'secondary',
  published: 'default',
  archived: 'secondary',
};

const AUDIENCES: AnnouncementAudience[] = ['all', 'business_unit', 'team', 'location'];
const PRIORITIES: AnnouncementPriority[] = ['normal', 'important', 'urgent'];
const STATUSES: AnnouncementStatus[] = ['draft', 'scheduled', 'published', 'archived'];

const EMPTY: AnnouncementInput = {
  title: '',
  body: '',
  summary: '',
  audience: 'all',
  target_ids: [],
  priority: 'normal',
  pinned: false,
  requires_acknowledgement: false,
};

function Composer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (value: boolean) => void;
}): React.JSX.Element {
  const create = useCreateAnnouncement();
  const [form, setForm] = React.useState<AnnouncementInput>(EMPTY);
  const [targets, setTargets] = React.useState('');

  const set = <K extends keyof AnnouncementInput>(key: K, value: AnnouncementInput[K]): void =>
    setForm((current) => ({ ...current, [key]: value }));

  const ready = form.title.trim().length >= 3 && form.body.trim().length >= 10;

  const submit = (): void => {
    const ids =
      form.audience === 'all'
        ? []
        : targets
            .split(',')
            .map((value) => value.trim())
            .filter((value) => value !== '');

    create.mutate(
      {
        ...form,
        title: form.title.trim(),
        body: form.body.trim(),
        summary: form.summary?.trim() === '' ? null : form.summary,
        target_ids: ids,
      },
      {
        onSuccess: () => {
          setForm(EMPTY);
          setTargets('');
          onOpenChange(false);
        },
      },
    );
  };

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title="Draft an announcement"
      description="This saves a draft. Sending it is a separate step."
      confirmLabel="Save draft"
      onConfirm={submit}
      isConfirming={create.isPending}
      size="lg"
    >
      <div className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="announcement-title">Title *</Label>
          <Input
            id="announcement-title"
            value={form.title}
            onChange={(event) => set('title', event.target.value)}
            maxLength={200}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="announcement-summary">One-line summary</Label>
          <Input
            id="announcement-summary"
            value={form.summary ?? ''}
            onChange={(event) => set('summary', event.target.value)}
            maxLength={300}
            placeholder="Shown under the title on the notice board."
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="announcement-body">Announcement *</Label>
          <Textarea
            id="announcement-body"
            value={form.body}
            onChange={(event) => set('body', event.target.value)}
            rows={8}
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="announcement-audience">Who sees it</Label>
            <select
              id="announcement-audience"
              className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
              value={form.audience}
              onChange={(event) => set('audience', event.target.value as AnnouncementAudience)}
            >
              {AUDIENCES.map((value) => (
                <option key={value} value={value}>
                  {ANNOUNCEMENT_AUDIENCE_LABELS[value]}
                </option>
              ))}
            </select>
          </div>

          <div className="space-y-2">
            <Label htmlFor="announcement-priority">Priority</Label>
            <select
              id="announcement-priority"
              className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
              value={form.priority}
              onChange={(event) => set('priority', event.target.value as AnnouncementPriority)}
            >
              {PRIORITIES.map((value) => (
                <option key={value} value={value}>
                  {ANNOUNCEMENT_PRIORITY_LABELS[value]}
                </option>
              ))}
            </select>
          </div>
        </div>

        {form.audience !== 'all' ? (
          <div className="space-y-2">
            <Label htmlFor="announcement-targets">{ANNOUNCEMENT_AUDIENCE_LABELS[form.audience]} IDs</Label>
            <Input
              id="announcement-targets"
              value={targets}
              onChange={(event) => setTargets(event.target.value)}
              placeholder="Comma-separated IDs"
            />
            <p className="text-muted-foreground text-xs">
              The server matches these against each employee&apos;s own record when it decides who the notice
              reaches.
            </p>
          </div>
        ) : null}

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="announcement-expires">Take it down on</Label>
            <Input
              id="announcement-expires"
              type="datetime-local"
              value={form.expires_at ?? ''}
              onChange={(event) => set('expires_at', event.target.value === '' ? null : event.target.value)}
            />
          </div>
          <div className="space-y-3 pt-6">
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={form.pinned === true}
                onCheckedChange={(checked) => set('pinned', checked === true)}
              />
              Pin to the top
            </label>
            <label className="flex items-center gap-2 text-sm">
              <Checkbox
                checked={form.requires_acknowledgement === true}
                onCheckedChange={(checked) => set('requires_acknowledgement', checked === true)}
              />
              Ask people to confirm they have read it
            </label>
          </div>
        </div>

        {!ready ? <p className="text-muted-foreground text-xs">A title and a body are required.</p> : null}
      </div>
    </Modal>
  );
}

function AnnouncementDrawer({
  announcementId,
  onClose,
}: {
  announcementId: string;
  onClose: () => void;
}): React.JSX.Element {
  const query = useAnnouncement(announcementId);
  const publish = usePublishAnnouncement();
  const archive = useArchiveAnnouncement();
  const update = useUpdateAnnouncement();
  const canPublish = usePermitted({ permission: 'announcements:publish' });
  const canUpdate = usePermitted({ permission: 'announcements:update' });

  const announcement = query.data;

  return (
    <Modal
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title={announcement?.title ?? 'Announcement'}
      size="lg"
      footer={
        <div className="flex flex-wrap items-center justify-end gap-2">
          {announcement && canUpdate && announcement.status !== 'archived' ? (
            <Button
              variant="outline"
              onClick={() => archive.mutate(announcementId, { onSuccess: onClose })}
              disabled={archive.isPending}
            >
              Archive
            </Button>
          ) : null}
          {announcement && canUpdate && announcement.status === 'published' ? (
            <Button
              variant="outline"
              onClick={() => update.mutate({ announcementId, payload: { pinned: !announcement.pinned } })}
              disabled={update.isPending}
            >
              {announcement.pinned ? 'Unpin' : 'Pin to top'}
            </Button>
          ) : null}
          {announcement && canPublish && announcement.status === 'draft' ? (
            <Button onClick={() => publish.mutate({ announcementId })} disabled={publish.isPending}>
              Send it
            </Button>
          ) : null}
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
        </div>
      }
    >
      {!announcement ? (
        <p className="text-muted-foreground text-sm">Loading…</p>
      ) : (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={STATUS_TONE[announcement.status]}>
              {ANNOUNCEMENT_STATUS_LABELS[announcement.status]}
            </Badge>
            <Badge variant="outline">{ANNOUNCEMENT_AUDIENCE_LABELS[announcement.audience]}</Badge>
            <Badge variant="outline">{ANNOUNCEMENT_PRIORITY_LABELS[announcement.priority]}</Badge>
            {announcement.pinned ? <Badge variant="secondary">Pinned</Badge> : null}
          </div>

          {announcement.summary ? (
            <p className="text-muted-foreground text-sm">{announcement.summary}</p>
          ) : null}
          <p className="text-sm leading-relaxed whitespace-pre-wrap">{announcement.body}</p>

          {announcement.requires_acknowledgement ? (
            <div className="border-border space-y-2 rounded-md border p-3">
              <p className="text-sm font-medium">
                {announcement.acknowledged_count}
                {announcement.audience_size !== null ? ` of ${String(announcement.audience_size)}` : ''}{' '}
                acknowledged
              </p>
              {announcement.acknowledgements.length === 0 ? (
                <p className="text-muted-foreground text-sm">Nobody yet.</p>
              ) : (
                <ul className="text-muted-foreground space-y-1 text-sm">
                  {announcement.acknowledgements.map((row) => (
                    <li key={row.employee_id}>
                      {row.employee_name} · {new Date(row.acknowledged_at).toLocaleString()}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ) : null}

          {announcement.status === 'draft' && !canPublish ? (
            <p className="text-muted-foreground text-xs">
              You can write and amend this, but sending it is somebody else&apos;s decision.
            </p>
          ) : null}
        </div>
      )}
    </Modal>
  );
}

export function AnnouncementsPage(): React.JSX.Element {
  const [status, setStatus] = React.useState<AnnouncementStatus | ''>('');
  const [page, setPage] = React.useState(1);
  const [composing, setComposing] = React.useState(false);
  const [openId, setOpenId] = React.useState<string | null>(null);
  const canCreate = usePermitted({ permission: 'announcements:create' });

  const query = useAnnouncements({ page, page_size: 20, ...(status === '' ? {} : { status }) });
  const rows = query.data?.items ?? [];

  const columns: DataTableColumn<Announcement>[] = [
    {
      id: 'title',
      header: 'Announcement',
      cell: (row) => (
        <div>
          <p className="font-medium">{row.title}</p>
          {row.summary ? <p className="text-muted-foreground text-xs">{row.summary}</p> : null}
        </div>
      ),
    },
    {
      id: 'audience',
      header: 'Audience',
      cell: (row) => (
        <div>
          <p className="text-sm">{ANNOUNCEMENT_AUDIENCE_LABELS[row.audience]}</p>
          {row.audience_size !== null ? (
            <p className="text-muted-foreground text-xs">{row.audience_size} people</p>
          ) : null}
        </div>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <div className="flex items-center gap-2">
          <Badge variant={STATUS_TONE[row.status]}>{ANNOUNCEMENT_STATUS_LABELS[row.status]}</Badge>
          {row.is_live ? <span className="text-muted-foreground text-xs">live</span> : null}
        </div>
      ),
    },
    {
      id: 'priority',
      header: 'Priority',
      cell: (row) => <Badge variant="outline">{ANNOUNCEMENT_PRIORITY_LABELS[row.priority]}</Badge>,
    },
    {
      id: 'ack',
      header: 'Acknowledged',
      align: 'right',
      cell: (row) =>
        row.requires_acknowledgement ? (
          <span className="tabular-nums">
            {row.acknowledged_count}
            {row.audience_size !== null ? ` / ${String(row.audience_size)}` : ''}
          </span>
        ) : (
          <span className="text-muted-foreground text-xs">not asked</span>
        ),
    },
    {
      id: 'published',
      header: 'Sent',
      cell: (row) => (row.published_at ? new Date(row.published_at).toLocaleDateString() : '—'),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Announcements"
        description="Company notices. Drafting one and sending it are separate acts, with separate permissions."
        actions={
          canCreate ? (
            <Button onClick={() => setComposing(true)}>
              <Plus className="mr-2 size-4" aria-hidden="true" />
              New announcement
            </Button>
          ) : null
        }
      />

      <div className="flex flex-wrap items-center gap-3">
        <select
          aria-label="Status"
          className="border-input bg-background h-9 rounded-md border px-3 text-sm"
          value={status}
          onChange={(event) => {
            setStatus(event.target.value as AnnouncementStatus | '');
            setPage(1);
          }}
        >
          <option value="">Any status</option>
          {STATUSES.map((value) => (
            <option key={value} value={value}>
              {ANNOUNCEMENT_STATUS_LABELS[value]}
            </option>
          ))}
        </select>
      </div>

      <DataTable
        rows={rows}
        columns={columns}
        getRowId={(row) => row.id}
        isLoading={query.isLoading}
        error={query.error}
        onRowClick={(row) => setOpenId(row.id)}
        emptyTitle="No announcements"
        emptyDescription="Nothing has been written yet."
        emptyAction={canCreate ? { label: 'New announcement', onClick: () => setComposing(true) } : undefined}
      />

      {query.data ? (
        <Pagination
          meta={query.data.meta}
          onPageChange={setPage}
          itemLabel="announcements"
          disabled={query.isFetching}
        />
      ) : null}

      <Composer open={composing} onOpenChange={setComposing} />
      {openId !== null ? (
        <AnnouncementDrawer announcementId={openId} onClose={() => setOpenId(null)} />
      ) : null}
    </div>
  );
}
