'use client';

import { MessageSquare, Plus } from 'lucide-react';
import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  useMyTicket,
  useMyTicketCategories,
  useMyTickets,
  useRaiseTicket,
  useReopenTicket,
  useReplyToTicket,
} from '@/features/helpdesk/hooks';
import {
  TICKET_PRIORITY_LABELS,
  TICKET_STATUS_LABELS,
  type MyTicket,
  type TicketPriority,
  type TicketStatus,
} from '@/features/helpdesk/types';

/**
 * My Requests.
 *
 * The employee side of the helpdesk. Everything here is about the caller's own
 * requests, and nothing on this screen names a person: the requester comes from
 * the session, so the raise form has no employee field to fill in wrongly.
 *
 * The thread shows only public messages. That is not this component being
 * careful -- `MyTicketComment` has no `internal` field, so an agent's working
 * note has nowhere to land even if the server sent one.
 *
 * Reply and reopen are offered from `can_reply` and `can_reopen` on the
 * response rather than from a status comparison here. The server owns the
 * transition table; a copy of it in the browser is a copy that goes stale.
 */

const STATUS_TONE: Record<TicketStatus, 'default' | 'secondary' | 'outline' | 'destructive'> = {
  open: 'default',
  in_progress: 'default',
  waiting_on_employee: 'destructive',
  resolved: 'secondary',
  closed: 'secondary',
  cancelled: 'outline',
  reopened: 'default',
};

const PRIORITIES: TicketPriority[] = ['low', 'medium', 'high', 'urgent'];

function RaiseDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (v: boolean) => void }) {
  // The employee-facing list: the desk's categories endpoint is behind
  // `helpdesk:view`, which a requester does not hold and should not need.
  const categories = useMyTicketCategories();
  const raise = useRaiseTicket();
  const [categoryId, setCategoryId] = React.useState('');
  const [subject, setSubject] = React.useState('');
  const [description, setDescription] = React.useState('');
  const [priority, setPriority] = React.useState<TicketPriority>('medium');

  const ready = categoryId !== '' && subject.trim().length >= 3 && description.trim().length >= 10;

  const submit = (): void => {
    raise.mutate(
      { category_id: categoryId, subject: subject.trim(), description: description.trim(), priority },
      {
        onSuccess: () => {
          setCategoryId('');
          setSubject('');
          setDescription('');
          setPriority('medium');
          onOpenChange(false);
        },
      },
    );
  };

  return (
    <Modal
      open={open}
      onOpenChange={onOpenChange}
      title="Raise a request"
      description="Pick the team who can help, then say what you need."
      confirmLabel="Send request"
      onConfirm={submit}
      isConfirming={raise.isPending}
      size="lg"
    >
      <div className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="ticket-category">What is this about? *</Label>
          <select
            id="ticket-category"
            className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
            value={categoryId}
            onChange={(event) => setCategoryId(event.target.value)}
          >
            <option value="">Choose a category</option>
            {(categories.data ?? []).map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </select>
          {/*
           * Categories are read from the server rather than listed here, so an
           * organization that adds a queue does not need a frontend release.
           */}
          <p className="text-muted-foreground text-xs">
            The category decides who picks this up and how quickly they are expected to.
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="ticket-subject">Subject *</Label>
          <Input
            id="ticket-subject"
            value={subject}
            onChange={(event) => setSubject(event.target.value)}
            placeholder="One line — what do you need?"
            maxLength={200}
          />
        </div>

        <div className="space-y-2">
          <Label htmlFor="ticket-priority">How urgent is it?</Label>
          <select
            id="ticket-priority"
            className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
            value={priority}
            onChange={(event) => setPriority(event.target.value as TicketPriority)}
          >
            {PRIORITIES.map((value) => (
              <option key={value} value={value}>
                {TICKET_PRIORITY_LABELS[value]}
              </option>
            ))}
          </select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="ticket-description">Details *</Label>
          <Textarea
            id="ticket-description"
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            rows={6}
            placeholder="What has happened, what you have already tried, and anything the team will need to know."
          />
          <p className="text-muted-foreground text-xs">
            {description.trim().length < 10
              ? 'A little more detail, please.'
              : `${String(description.length)} characters`}
          </p>
        </div>

        {!ready ? (
          <p className="text-muted-foreground text-xs">A category, a subject and some detail are required.</p>
        ) : null}
      </div>
    </Modal>
  );
}

function TicketThread({ ticketId, onClose }: { ticketId: string; onClose: () => void }) {
  const query = useMyTicket(ticketId);
  const reply = useReplyToTicket();
  const reopen = useReopenTicket();
  const [body, setBody] = React.useState('');

  const ticket = query.data;

  const send = (): void => {
    const trimmed = body.trim();
    if (trimmed.length === 0) return;
    reply.mutate({ ticketId, body: trimmed }, { onSuccess: () => setBody('') });
  };

  return (
    <Modal
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title={ticket ? `${ticket.ticket_code} · ${ticket.subject}` : 'Request'}
      size="lg"
      footer={
        <Button variant="outline" onClick={onClose}>
          Close
        </Button>
      }
    >
      {query.isLoading || !ticket ? (
        <p className="text-muted-foreground text-sm">Loading…</p>
      ) : (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant={STATUS_TONE[ticket.status]}>{TICKET_STATUS_LABELS[ticket.status]}</Badge>
            <Badge variant="outline">{TICKET_PRIORITY_LABELS[ticket.priority]}</Badge>
            <span className="text-muted-foreground text-xs">{ticket.category}</span>
          </div>

          <div className="bg-muted/40 rounded-md p-3">
            <p className="text-sm whitespace-pre-wrap">{ticket.description}</p>
          </div>

          <div className="space-y-3">
            <p className="text-muted-foreground text-xs font-medium tracking-wide uppercase">Conversation</p>
            {ticket.comments.length === 0 ? (
              <p className="text-muted-foreground text-sm">Nobody has replied yet.</p>
            ) : (
              ticket.comments.map((comment) => (
                <div
                  key={comment.id}
                  className={
                    comment.from_agent
                      ? 'bg-primary-subtle rounded-md p-3'
                      : 'border-border rounded-md border p-3'
                  }
                >
                  <p className="text-muted-foreground mb-1 text-xs">
                    {comment.from_agent ? 'Support' : 'You'} · {new Date(comment.created_at).toLocaleString()}
                  </p>
                  <p className="text-sm whitespace-pre-wrap">{comment.body}</p>
                </div>
              ))
            )}
          </div>

          {ticket.resolution ? (
            <div className="border-border rounded-md border p-3">
              <p className="text-muted-foreground mb-1 text-xs font-medium tracking-wide uppercase">
                Resolution
              </p>
              <p className="text-sm whitespace-pre-wrap">{ticket.resolution}</p>
            </div>
          ) : null}

          {ticket.can_reply ? (
            <div className="space-y-2">
              <Label htmlFor="ticket-reply">Add a reply</Label>
              <Textarea
                id="ticket-reply"
                value={body}
                onChange={(event) => setBody(event.target.value)}
                rows={3}
                placeholder="Anything else the team needs to know?"
              />
              <Button size="sm" onClick={send} disabled={body.trim().length === 0 || reply.isPending}>
                Send reply
              </Button>
            </div>
          ) : null}

          {ticket.can_reopen ? (
            <div className="border-border flex items-center justify-between gap-3 rounded-md border p-3">
              <p className="text-muted-foreground text-sm">Still not sorted?</p>
              <Button
                size="sm"
                variant="outline"
                onClick={() => reopen.mutate({ ticketId })}
                disabled={reopen.isPending}
              >
                Reopen this request
              </Button>
            </div>
          ) : null}
        </div>
      )}
    </Modal>
  );
}

export function MyHelpdeskPage(): React.JSX.Element {
  const query = useMyTickets();
  const [raising, setRaising] = React.useState(false);
  const [openTicketId, setOpenTicketId] = React.useState<string | null>(null);

  const rows = query.data ?? [];
  const awaiting = rows.filter((row) => row.awaiting_me).length;

  const columns: DataTableColumn<MyTicket>[] = [
    {
      id: 'subject',
      header: 'Request',
      cell: (row) => (
        <div>
          <p className="font-medium">{row.subject}</p>
          <p className="text-muted-foreground text-xs">
            {row.ticket_code} · {row.category}
          </p>
        </div>
      ),
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <div className="flex items-center gap-2">
          <Badge variant={STATUS_TONE[row.status]}>{TICKET_STATUS_LABELS[row.status]}</Badge>
          {row.awaiting_me ? <span className="text-destructive text-xs">needs you</span> : null}
        </div>
      ),
    },
    {
      id: 'priority',
      header: 'Priority',
      cell: (row) => <Badge variant="outline">{TICKET_PRIORITY_LABELS[row.priority]}</Badge>,
    },
    {
      id: 'raised',
      header: 'Raised',
      cell: (row) => new Date(row.created_at).toLocaleDateString(),
    },
    {
      id: 'resolved',
      header: 'Resolved',
      cell: (row) => (row.resolved_at ? new Date(row.resolved_at).toLocaleDateString() : '—'),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="My requests"
        description="Ask HR, IT, Admin, Finance or Facilities for something, and follow it through."
        actions={
          <Button onClick={() => setRaising(true)}>
            <Plus className="mr-2 size-4" aria-hidden="true" />
            Raise a request
          </Button>
        }
      />

      {awaiting > 0 ? (
        <Card className="border-destructive/40">
          <CardHeader className="pb-2">
            <CardTitle className="flex items-center gap-2 text-base">
              <MessageSquare className="size-4" aria-hidden="true" />
              {awaiting} request{awaiting === 1 ? '' : 's'} waiting on you
            </CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-muted-foreground text-sm">
              Someone has asked you a question. Open the request and reply so they can carry on.
            </p>
          </CardContent>
        </Card>
      ) : null}

      <DataTable
        rows={rows}
        columns={columns}
        getRowId={(row) => row.id}
        isLoading={query.isLoading}
        error={query.error}
        onRowClick={(row) => setOpenTicketId(row.id)}
        emptyTitle="No requests"
        emptyDescription="When you need something from HR or IT, raise it here and it will be tracked."
        emptyAction={{ label: 'Raise a request', onClick: () => setRaising(true) }}
      />

      <RaiseDialog open={raising} onOpenChange={setRaising} />
      {openTicketId !== null ? (
        <TicketThread ticketId={openTicketId} onClose={() => setOpenTicketId(null)} />
      ) : null}
    </div>
  );
}
