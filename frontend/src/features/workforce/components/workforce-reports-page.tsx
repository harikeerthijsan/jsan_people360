'use client';

import { Download } from 'lucide-react';
import * as React from 'react';

import { PageHeader } from '@/components/common/page-header';
import { toast } from '@/components/ui/sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { workforceApi } from '@/features/workforce/api';
import { WORKFORCE_REPORT_LABELS, type ExportFormat, type WorkforceReport } from '@/features/workforce/types';

const FORMATS: { value: ExportFormat; label: string }[] = [
  { value: 'csv', label: 'CSV' },
  { value: 'xlsx', label: 'Excel' },
  { value: 'pdf', label: 'PDF' },
];

const BLURBS: Record<WorkforceReport, string> = {
  attendance: 'Every attendance record in the period, with worked, late and overtime minutes.',
  'leave-register': 'Leave taken, by employee and type, with the decision on each request.',
  'leave-balance': 'Entitlement, taken, held and remaining for every employee.',
  timesheet: 'Hours booked per week, split into billable and non-billable.',
  overtime: 'Minutes worked beyond the shift, by employee.',
  shift: 'Who was on which shift, and when the assignment changed.',
};

const monthStart = (): string => {
  const date = new Date();
  return new Date(date.getFullYear(), date.getMonth(), 1).toISOString().slice(0, 10);
};

/**
 * Workforce reports.
 *
 * Every report takes the same window, so it is asked for once at the top rather
 * than six times. The download goes through the authenticated client -- these
 * endpoints need a bearer token, which a plain link would not carry.
 */
export function WorkforceReportsPage(): React.JSX.Element {
  const [fromDate, setFromDate] = React.useState(monthStart);
  const [toDate, setToDate] = React.useState(() => new Date().toISOString().slice(0, 10));
  const [downloading, setDownloading] = React.useState<string | null>(null);

  const download = async (report: WorkforceReport, fmt: ExportFormat): Promise<void> => {
    setDownloading(`${report}-${fmt}`);
    try {
      await workforceApi.exportReport(report, fmt, fromDate, toDate);
    } catch (error) {
      toast.error('Could not export this report', {
        description: error instanceof Error ? error.message : undefined,
      });
    } finally {
      setDownloading(null);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Workforce reports"
        description="Attendance, leave, timesheets and overtime, over a period you choose."
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Period</CardTitle>
          <CardDescription>Applies to every report below.</CardDescription>
        </CardHeader>
        <CardContent className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label htmlFor="report-from">From</Label>
            <Input
              id="report-from"
              onChange={(event) => {
                setFromDate(event.target.value);
              }}
              type="date"
              value={fromDate}
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="report-to">To</Label>
            <Input
              id="report-to"
              onChange={(event) => {
                setToDate(event.target.value);
              }}
              type="date"
              value={toDate}
            />
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        {(Object.keys(WORKFORCE_REPORT_LABELS) as WorkforceReport[]).map((report) => (
          <Card key={report}>
            <CardHeader>
              <CardTitle className="text-base">{WORKFORCE_REPORT_LABELS[report]}</CardTitle>
              <CardDescription>{BLURBS[report]}</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-wrap gap-2">
              {FORMATS.map((format) => (
                <Button
                  isLoading={downloading === `${report}-${format.value}`}
                  key={format.value}
                  onClick={() => void download(report, format.value)}
                  size="sm"
                  variant="outline"
                >
                  <Download className="size-4" aria-hidden="true" />
                  {format.label}
                </Button>
              ))}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
