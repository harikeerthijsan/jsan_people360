'use client';

import { Clock, LogIn, LogOut } from 'lucide-react';
import * as React from 'react';

import { AttendanceStatusBadge, formatMinutes } from '@/components/common/workforce-widgets';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useCheckIn, useCheckOut, useMyAttendanceToday } from '@/features/self-service/hooks';
import { WORK_MODE_OPTIONS } from '@/features/self-service/types';
import { cn } from '@/lib/utils';

/**
 * Check in, check out, and the day so far.
 *
 * The one control an employee touches every morning, so it is a single card
 * with one obvious button rather than a form. The work mode sits beside it as a
 * segmented choice: it has four values, it is needed on the way in, and putting
 * it behind a dialog would add a click to the most repeated action in the
 * product.
 *
 * Everything the card renders -- including whether each button is available --
 * comes from the server. The client does not decide that checking in twice is
 * refused; it shows the answer the server already gave, so the button and the
 * endpoint cannot disagree.
 */

/** `HH:MM` in the viewer's own timezone. */
function clock(value: string | null): string {
  if (!value) return '—';
  return new Date(value).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

/**
 * Minutes elapsed since check-in, ticking.
 *
 * Anchored to the server's clock rather than the browser's: `elapsed_minutes`
 * is what the server measured at the moment of the response, and the local
 * counter only adds time since then. A browser an hour out of step therefore
 * still shows the right duration.
 */
function useElapsed(startMinutes: number, running: boolean): number {
  const [extra, setExtra] = React.useState(0);
  const since = React.useRef(Date.now());

  React.useEffect(() => {
    since.current = Date.now();
    setExtra(0);
    if (!running) return;

    const timer = setInterval(() => {
      setExtra(Math.floor((Date.now() - since.current) / 60_000));
    }, 30_000);
    return () => {
      clearInterval(timer);
    };
  }, [running, startMinutes]);

  return startMinutes + extra;
}

interface AttendanceCardProps {
  className?: string;
}

export function AttendanceCard({ className }: AttendanceCardProps): React.JSX.Element {
  const today = useMyAttendanceToday();
  const checkIn = useCheckIn();
  const checkOut = useCheckOut();
  const [workMode, setWorkMode] = React.useState<string>('office');

  const data = today.data;
  const running = data?.checked_in === true && data.checked_out === false;
  const elapsed = useElapsed(data?.elapsed_minutes ?? 0, running);

  return (
    <Card className={cn('overflow-hidden', className)}>
      <CardHeader className="flex flex-row items-center justify-between gap-2 pb-2">
        <CardTitle className="text-sm font-medium">Today</CardTitle>
        {data?.status ? <AttendanceStatusBadge status={data.status} /> : null}
      </CardHeader>

      <CardContent className="space-y-4">
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2">
          <div>
            <p className="text-muted-foreground text-xs">Checked in</p>
            <p className="text-lg font-semibold tabular-nums">{clock(data?.record?.check_in_at ?? null)}</p>
          </div>
          <div>
            <p className="text-muted-foreground text-xs">Checked out</p>
            <p className="text-lg font-semibold tabular-nums">{clock(data?.record?.check_out_at ?? null)}</p>
          </div>
          <div>
            <p className="text-muted-foreground text-xs">{running ? 'Working for' : 'Hours today'}</p>
            <p className="flex items-center gap-1.5 text-lg font-semibold tabular-nums">
              {running ? <Clock className="text-primary size-4 animate-pulse" aria-hidden="true" /> : null}
              {running ? formatMinutes(elapsed) : formatMinutes(data?.worked_minutes ?? 0)}
            </p>
          </div>
        </div>

        {data?.can_check_in ? (
          <fieldset className="space-y-2">
            <legend className="text-muted-foreground text-xs">Working from</legend>
            <div className="flex flex-wrap gap-1.5">
              {WORK_MODE_OPTIONS.map((option) => (
                <Button
                  key={option.value}
                  onClick={() => {
                    setWorkMode(option.value);
                  }}
                  size="sm"
                  type="button"
                  variant={workMode === option.value ? 'default' : 'outline'}
                >
                  {option.label}
                </Button>
              ))}
            </div>
          </fieldset>
        ) : null}

        <div className="flex flex-wrap gap-2">
          <Button
            className="flex-1 sm:flex-none"
            disabled={!data?.can_check_in}
            isLoading={checkIn.isPending}
            onClick={() => {
              checkIn.mutate({ work_mode: workMode, notes: null });
            }}
          >
            <LogIn className="size-4" aria-hidden="true" />
            Check in
          </Button>
          <Button
            className="flex-1 sm:flex-none"
            disabled={!data?.can_check_out}
            isLoading={checkOut.isPending}
            onClick={() => {
              checkOut.mutate({ notes: null });
            }}
            variant="outline"
          >
            <LogOut className="size-4" aria-hidden="true" />
            Check out
          </Button>
        </div>

        {data?.checked_out ? (
          <p className="text-muted-foreground text-sm">
            Your day is recorded. A missed entry is fixed with a correction request, not by editing the
            record.
          </p>
        ) : null}
      </CardContent>
    </Card>
  );
}
