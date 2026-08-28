'use client';

import { Lock } from 'lucide-react';
import * as React from 'react';

import { DetailSection } from '@/components/common/detail-view';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { Timeline, type TimelineItem } from '@/components/common/timeline';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { usePermitted } from '@/components/common/can';
import { useAuth } from '@/components/providers/auth-provider';
import {
  useAssignTicket,
  useChangeTicketStatus,
  useCommentOnTicket,
  useReclassifyTicket,
  useTicket,
  useTicketCategories,
} from '@/features/helpdesk/hooks';
import {
  TICKET_PRIORITY_LABELS,
  TICKET_QUEUE_LABELS,
  TICKET_STATUS_LABELS,
  type TicketPriority,
  type TicketStatus,
} from '@/features/helpdesk/types';

/**
 * One request, from the agent's side.
 *
 * The status control is built from `allowed_transitions` on the response, not
 * from a table in this file. The server owns the transition rules; a copy here
 * would drift, and offering a move the API refuses is worse than not offering
 * it at all.
 *
 * An internal note is the one thing on this screen that must never reach the
 * requester. The checkbox is the only way to write one, the note is rendered
 * with a lock and a distinct background, and the employee's own read model has
 * no field it could arrive in -- three layers, of which only the last is load
 * bearing.
 */

const PRIORITIES: TicketPriority[] = ['low', 'medium', 'high', 'urgent'];

const HISTORY_LABELS: Record<string, string> = {
  raised: 'Raised',
  assigned: 'Assigned',
  status_changed: 'Status changed',
  commented: 'Comment added',
  priority_changed: 'Priority changed',
  category_changed: 'Recategorised',
  resolved: 'Resolved',
  reopened: 'Reopened',
  closed: 'Closed',
};

export function TicketDetailPage({ ticketId }: { ticketId: string }): React.JSX.Element {
  const query = useTicket(ticketId);
  const categories = useTicketCategories();
  const { user } = useAuth();
  const comment = useCommentOnTicket();
  const changeStatus = useChangeTicketStatus();
  const assign = useAssignTicket();
  const reclassify = useReclassifyTicket();

  const canUpdate = usePermitted({ permission: 'helpdesk:update' });
  const canAssign = usePermitted({ permission: 'helpdesk:assign' });

  const [body, setBody] = React.useState('');
  const [internal, setInternal] = React.useState(false);
  const [nextStatus, setNextStatus] = React.useState<TicketStatus | ''>('');
  const [resolution, setResolution] = React.useState('');

  const ticket = query.data;

  if (query.isLoading) return <LoadingState message="Loading request…" />;
  if (query.error) return <ErrorState error={query.error} onRetry={() => void query.refetch()} />;
  if (!ticket) return <ErrorState error={new Error('Request not found.')} />;

  const requester = ticket.raised_for ?? ticket.raised_by;
  const needsResolution = nextStatus === 'resolved';

  const submitComment = (): void => {
    const trimmed = body.trim();
    if (trimmed.length === 0) return;
    comment.mutate(
      { ticketId, payload: { body: trimmed, internal } },
      {
        onSuccess: () => {
          setBody('');
          setInternal(false);
        },
      },
    );
  };

  const submitStatus = (): void => {
    if (nextStatus === '') return;
    changeStatus.mutate(
      {
        ticketId,
        payload: {
          status: nextStatus,
          resolution: needsResolution && resolution.trim() !== '' ? resolution.trim() : null,
        },
      },
      {
        onSuccess: () => {
          setNextStatus('');
          setResolution('');
        },
      },
    );
  };

  const historyItems: TimelineItem[] = ticket.history.map((entry) => ({
    id: entry.id,
    title: HISTORY_LABELS[entry.event] ?? entry.event,
    description:
      entry.notes ??
      (entry.previous_value !== null && entry.new_value !== null
        ? `${entry.previous_value} → ${entry.new_value}`
        : (entry.new_value ?? undefined)),
    timestamp: entry.created_at,
  }));

  return (
    <div className="space-y-6">
      <PageHeader
        title={ticket.subject}
        description={`${ticket.ticket_code} · raised by ${requester.full_name} (${requester.employee_code})`}
        actions={
          <div className="flex items-center gap-2">
            <Badge>{TICKET_STATUS_LABELS[ticket.status]}</Badge>
            <Badge variant="outline">{TICKET_PRIORITY_LABELS[ticket.priority]}</Badge>
            {ticket.is_overdue ? <Badge variant="destructive">Overdue</Badge> : null}
          </div>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">What was asked</CardTitle>
            </CardHeader>
            <CardContent>
              <p className="text-sm whitespace-pre-wrap">{ticket.description}</p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">Conversation</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              {ticket.comments.length === 0 ? (
                <p className="text-muted-foreground text-sm">Nothing said yet.</p>
              ) : (
                ticket.comments.map((entry) => (
                  <div
                    key={entry.id}
                    className={
                      entry.internal
                        ? 'border-warning/40 bg-warning-subtle rounded-md border border-dashed p-3'
                        : 'border-border rounded-md border p-3'
                    }
                  >
                    <p className="text-muted-foreground mb-1 flex items-center gap-1.5 text-xs">
                      {entry.internal ? (
                        <>
                          <Lock className="size-3" aria-hidden="true" />
                          <span className="font-medium">Internal note — not visible to the employee</span>
                          <span>·</span>
                        </>
                      ) : null}
                      {new Date(entry.created_at).toLocaleString()}
                    </p>
                    <p className="text-sm whitespace-pre-wrap">{entry.body}</p>
                  </div>
                ))
              )}

              {canUpdate ? (
                <div className="border-border space-y-3 border-t pt-4">
                  <div className="space-y-2">
                    <Label htmlFor="ticket-comment">Add a message</Label>
                    <Textarea
                      id="ticket-comment"
                      value={body}
                      onChange={(event) => setBody(event.target.value)}
                      rows={3}
                      placeholder={
                        internal
                          ? 'A working note for the team. The employee will not see this.'
                          : 'A reply the employee will see.'
                      }
                    />
                  </div>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <label className="flex items-center gap-2 text-sm">
                      <Checkbox
                        checked={internal}
                        onCheckedChange={(checked) => setInternal(checked === true)}
                      />
                      <span className="flex items-center gap-1.5">
                        <Lock className="size-3.5" aria-hidden="true" />
                        Internal note
                      </span>
                    </label>
                    <Button
                      size="sm"
                      onClick={submitComment}
                      disabled={body.trim().length === 0 || comment.isPending}
                    >
                      {internal ? 'Save note' : 'Send reply'}
                    </Button>
                  </div>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="text-base">History</CardTitle>
            </CardHeader>
            <CardContent>
              <Timeline items={historyItems} />
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6">
          <Card>
            <CardContent className="pt-6">
              <DetailSection
                title="Details"
                items={[
                  { label: 'Queue', value: TICKET_QUEUE_LABELS[ticket.queue] },
                  { label: 'Category', value: ticket.category.name },
                  { label: 'Priority', value: TICKET_PRIORITY_LABELS[ticket.priority] },
                  { label: 'Status', value: TICKET_STATUS_LABELS[ticket.status] },
                  {
                    label: 'Due',
                    value: ticket.due_at ? new Date(ticket.due_at).toLocaleString() : 'No response target',
                  },
                  {
                    label: 'First response',
                    value: ticket.first_responded_at
                      ? new Date(ticket.first_responded_at).toLocaleString()
                      : 'Not yet',
                  },
                  {
                    label: 'Resolved',
                    value: ticket.resolved_at ? new Date(ticket.resolved_at).toLocaleString() : '—',
                  },
                  { label: 'Reopened', value: `${String(ticket.reopen_count)} time(s)` },
                ]}
              />
            </CardContent>
          </Card>

          {canAssign ? (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Ownership</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <p className="text-muted-foreground text-sm">
                  {ticket.assigned_to_id === null ? 'Nobody has picked this up.' : 'Someone owns this.'}
                </p>
                <div className="flex flex-wrap gap-2">
                  {/*
                   * `assigned_to_id` points at `users.id`, not at an employee
                   * -- an agent is somebody with a login, and not every agent
                   * has an employee record. So this sends the session's user
                   * id rather than looking up an employee.
                   */}
                  <Button
                    size="sm"
                    onClick={() => assign.mutate({ ticketId, assignedToId: user?.id ?? null })}
                    disabled={assign.isPending || !user}
                  >
                    Assign to me
                  </Button>
                  {ticket.assigned_to_id !== null ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => assign.mutate({ ticketId, assignedToId: null })}
                      disabled={assign.isPending}
                    >
                      Release
                    </Button>
                  ) : null}
                </div>
              </CardContent>
            </Card>
          ) : null}

          {canUpdate ? (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Move it on</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                {ticket.allowed_transitions.length === 0 ? (
                  <p className="text-muted-foreground text-sm">
                    This request is finished. There is nowhere left to move it.
                  </p>
                ) : (
                  <>
                    <div className="space-y-2">
                      <Label htmlFor="ticket-status">New status</Label>
                      <select
                        id="ticket-status"
                        className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                        value={nextStatus}
                        onChange={(event) => setNextStatus(event.target.value as TicketStatus | '')}
                      >
                        <option value="">Choose…</option>
                        {/* Exactly what the server will accept, no more. */}
                        {ticket.allowed_transitions.map((value) => (
                          <option key={value} value={value}>
                            {TICKET_STATUS_LABELS[value]}
                          </option>
                        ))}
                      </select>
                    </div>

                    {needsResolution ? (
                      <div className="space-y-2">
                        <Label htmlFor="ticket-resolution">How was it resolved?</Label>
                        <Textarea
                          id="ticket-resolution"
                          value={resolution}
                          onChange={(event) => setResolution(event.target.value)}
                          rows={3}
                          placeholder="What you did. The employee will see this."
                        />
                      </div>
                    ) : null}

                    <Button
                      size="sm"
                      onClick={submitStatus}
                      disabled={nextStatus === '' || changeStatus.isPending}
                    >
                      Update status
                    </Button>
                  </>
                )}
              </CardContent>
            </Card>
          ) : null}

          {canUpdate ? (
            <Card>
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Reclassify</CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="space-y-2">
                  <Label htmlFor="ticket-recategory">Category</Label>
                  <select
                    id="ticket-recategory"
                    className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                    value={ticket.category.id}
                    onChange={(event) =>
                      reclassify.mutate({ ticketId, payload: { category_id: event.target.value } })
                    }
                    disabled={reclassify.isPending}
                  >
                    {(categories.data ?? []).map((category) => (
                      <option key={category.id} value={category.id}>
                        {category.name}
                      </option>
                    ))}
                  </select>
                  <p className="text-muted-foreground text-xs">
                    Moving a request to another category moves it to that team&apos;s queue.
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="ticket-repriority">Priority</Label>
                  <select
                    id="ticket-repriority"
                    className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                    value={ticket.priority}
                    onChange={(event) =>
                      reclassify.mutate({ ticketId, payload: { priority: event.target.value } })
                    }
                    disabled={reclassify.isPending}
                  >
                    {PRIORITIES.map((value) => (
                      <option key={value} value={value}>
                        {TICKET_PRIORITY_LABELS[value]}
                      </option>
                    ))}
                  </select>
                </div>
              </CardContent>
            </Card>
          ) : null}
        </div>
      </div>
    </div>
  );
}
