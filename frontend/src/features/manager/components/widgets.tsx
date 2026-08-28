'use client';

import { Check, X } from 'lucide-react';
import * as React from 'react';

import { Modal } from '@/components/common/modal';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import type { ApprovalDecision, TeamAttendanceStatus, EmployeeSummary } from '@/features/manager/types';
import { TEAM_ATTENDANCE_STATUS_LABELS } from '@/features/manager/types';
import { UserAvatar } from '@/components/common/user-avatar';

/**
 * The manager module's shared pieces.
 *
 * Two of them, and both exist because they are the same on six screens: how a
 * team member is identified in a row, and how a decision is taken. A decision
 * taken differently on the leave screen and the timesheet screen would be a
 * decision a manager has to learn twice.
 */

type BadgeVariant = React.ComponentProps<typeof Badge>['variant'];

const ATTENDANCE_VARIANT: Record<TeamAttendanceStatus, BadgeVariant> = {
  present: 'success',
  absent: 'destructive',
  half_day: 'warning',
  leave: 'secondary',
  holiday: 'outline',
  weekend: 'outline',
};

/**
 * Today's status for one team member.
 *
 * "Not recorded" rather than a blank cell: a person who has not checked in and
 * a person nobody has looked at yet are the same thing on screen, and blank
 * reads as "fine".
 */
export function TeamAttendanceBadge({ status }: { status: TeamAttendanceStatus | null }): React.JSX.Element {
  if (status === null) {
    return <Badge variant="outline">Not recorded</Badge>;
  }
  return <Badge variant={ATTENDANCE_VARIANT[status]}>{TEAM_ATTENDANCE_STATUS_LABELS[status]}</Badge>;
}

/** A team member as one cell: photo, name and staff code. */
export function TeamMemberCell({
  employee,
  detail,
}: {
  employee: EmployeeSummary;
  detail?: string | null;
}): React.JSX.Element {
  return (
    <div className="flex items-center gap-2.5">
      <UserAvatar name={employee.full_name} photoUrl={employee.photo_url} size="sm" />
      <div className="min-w-0">
        <p className="truncate text-sm font-medium">{employee.full_name}</p>
        <p className="text-muted-foreground truncate text-xs tabular-nums">
          {employee.employee_code}
          {detail ? ` · ${detail}` : ''}
        </p>
      </div>
    </div>
  );
}

interface DecisionButtonsProps {
  /** Called with the manager's answer once the dialog is confirmed. */
  onDecide: (decision: ApprovalDecision) => void;
  isPending?: boolean;
  /** What is being decided, e.g. "leave request". Used in the dialog copy. */
  subject: string;
  /** Wording for the negative outcome; a timesheet is *returned*, not refused. */
  rejectLabel?: string;
  disabled?: boolean;
}

/**
 * Approve / reject, with a comment box on the way through.
 *
 * The comment is optional on an approval and prompted for on a rejection,
 * because a rejection without a reason sends the request straight back with
 * nothing for its author to act on. It is not *required*, though: a manager who
 * has already spoken to the person should not be forced to type it twice.
 */
export function DecisionButtons({
  onDecide,
  isPending = false,
  subject,
  rejectLabel = 'Reject',
  disabled = false,
}: DecisionButtonsProps): React.JSX.Element {
  const [pendingAnswer, setPendingAnswer] = React.useState<boolean | null>(null);
  const [notes, setNotes] = React.useState('');

  const close = (): void => {
    setPendingAnswer(null);
    setNotes('');
  };

  const confirm = (): void => {
    if (pendingAnswer === null) return;
    onDecide({ approved: pendingAnswer, notes: notes.trim() || null });
    close();
  };

  const approving = pendingAnswer === true;

  return (
    <>
      <div className="flex justify-end gap-2">
        <Button
          disabled={disabled}
          onClick={() => {
            setPendingAnswer(true);
          }}
          size="sm"
          variant="outline"
        >
          <Check className="size-3.5" aria-hidden="true" />
          Approve
        </Button>
        <Button
          disabled={disabled}
          onClick={() => {
            setPendingAnswer(false);
          }}
          size="sm"
          variant="outline"
        >
          <X className="size-3.5" aria-hidden="true" />
          {rejectLabel}
        </Button>
      </div>

      <Modal
        description={
          approving
            ? `A comment is optional. It is shown to the person whose ${subject} this is.`
            : `Say why. It is the only thing the person gets back with the ${subject}.`
        }
        onOpenChange={(open) => {
          if (!open) close();
        }}
        open={pendingAnswer !== null}
        title={approving ? `Approve this ${subject}` : `${rejectLabel} this ${subject}`}
        footer={
          <>
            <Button onClick={close} variant="outline">
              Cancel
            </Button>
            <Button isLoading={isPending} onClick={confirm} variant={approving ? 'default' : 'destructive'}>
              {approving ? 'Approve' : rejectLabel}
            </Button>
          </>
        }
      >
        <div className="space-y-2">
          <Label htmlFor="decision-notes">Comment</Label>
          <Textarea
            id="decision-notes"
            onChange={(event) => {
              setNotes(event.target.value);
            }}
            placeholder={approving ? 'Optional' : 'Why this is being returned'}
            rows={4}
            value={notes}
          />
        </div>
      </Modal>
    </>
  );
}

/** Hours and minutes, as people say them. */
export function formatMinutes(minutes: number): string {
  if (minutes <= 0) return '—';
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  if (hours === 0) return `${String(rest)}m`;
  if (rest === 0) return `${String(hours)}h`;
  return `${String(hours)}h ${String(rest)}m`;
}

/** A time-of-day from an ISO timestamp, or an em dash. */
export function formatTime(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
}

/** A date as "Mon 3 Mar", which reads faster in a table than an ISO string. */
export function formatDay(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });
}
