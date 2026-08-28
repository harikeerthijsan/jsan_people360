'use client';

import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { useMyHolidays, useMyProfile } from '@/features/self-service/hooks';
import { HOLIDAY_TYPE_LABELS, type MyHoliday } from '@/features/self-service/types';
import { cn } from '@/lib/utils';

/**
 * My Holidays.
 *
 * Only the calendar that applies where this employee works, plus any calendar
 * that applies everywhere. Another office's holidays are not shown at all --
 * not greyed out, not in a second tab. A holiday somebody does not get is not
 * information, it is a source of disappointed plans.
 */

function weekday(iso: string): string {
  return new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { weekday: 'long' });
}

export function MyHolidaysPage(): React.JSX.Element {
  const thisYear = new Date().getFullYear();
  const [year, setYear] = React.useState(thisYear);

  const holidays = useMyHolidays(year);
  const profile = useMyProfile();

  const rows = holidays.data ?? [];
  const upcoming = rows.filter((row) => !row.is_past);

  const columns: DataTableColumn<MyHoliday>[] = [
    {
      id: 'date',
      header: 'Date',
      cell: (row) => (
        <span className={cn('tabular-nums', row.is_past && 'text-muted-foreground')}>{row.holiday_date}</span>
      ),
    },
    { id: 'day', header: 'Day', cell: (row) => weekday(row.holiday_date) },
    {
      id: 'name',
      header: 'Holiday',
      cell: (row) => (
        <span className={cn('font-medium', row.is_past && 'text-muted-foreground')}>{row.name}</span>
      ),
    },
    {
      id: 'type',
      header: 'Type',
      cell: (row) => (
        <Badge variant="outline">{HOLIDAY_TYPE_LABELS[row.holiday_type] ?? row.holiday_type}</Badge>
      ),
    },
    { id: 'calendar', header: 'Calendar', cell: (row) => row.calendar_name },
    {
      id: 'status',
      header: '',
      align: 'right',
      cell: (row) => (row.is_past ? <span className="text-muted-foreground text-xs">Passed</span> : null),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Holidays"
        description={
          profile.data?.organization.work_location
            ? `The calendar for ${profile.data.organization.work_location.name}, plus anything company-wide.`
            : 'Company-wide holidays. Ask HR to record your work location to see local ones.'
        }
        actions={
          <div className="flex items-center gap-2">
            <Button
              onClick={() => {
                setYear((current) => current - 1);
              }}
              size="sm"
              variant="outline"
            >
              ‹
            </Button>
            <span className="min-w-16 text-center text-sm font-medium tabular-nums">{year}</span>
            <Button
              onClick={() => {
                setYear((current) => current + 1);
              }}
              size="sm"
              variant="outline"
            >
              ›
            </Button>
          </div>
        }
      />

      <div className="grid gap-4 sm:grid-cols-3">
        <StatCard label={`Holidays in ${String(year)}`} value={rows.length} />
        <StatCard label="Still to come" value={upcoming.length} />
        <StatCard hint="not charged as leave" label="Next holiday" value={upcoming[0]?.holiday_date ?? '—'} />
      </div>

      <DataTable
        columns={columns}
        emptyDescription={`No holiday calendar is published for ${String(year)}.`}
        emptyTitle="No holidays"
        error={holidays.error}
        getRowId={(row) => row.id}
        isLoading={holidays.isPending}
        onRetry={() => void holidays.refetch()}
        rows={rows}
      />
    </div>
  );
}
