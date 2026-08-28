'use client';

import * as React from 'react';

import { PageHeader } from '@/components/common/page-header';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { toast } from '@/components/ui/sonner';
import { assetApi } from '@/features/assets/api';
import { ASSET_REPORTS, type AssetReportId } from '@/features/assets/types';
import { apiClient } from '@/lib/api/client';

/**
 * Asset reports.
 *
 * Each export is a normal authenticated request rather than a plain link: the
 * API needs the bearer token, and an `<a href>` would not carry it. The blob is
 * handed to the browser once the response arrives, so a 403 surfaces as a toast
 * instead of a downloaded file containing an error page.
 *
 * Which reports a caller may run is the server's decision -- `assets:export` --
 * and a refusal is shown rather than predicted here.
 */

export function AssetReportsPage(): React.JSX.Element {
  const [busy, setBusy] = React.useState<string | null>(null);

  const download = async (report: AssetReportId, fmt: 'csv' | 'xlsx'): Promise<void> => {
    setBusy(`${report}-${fmt}`);
    try {
      const response = await apiClient.get(assetApi.admin.reportUrl(report, fmt), {
        responseType: 'blob',
      });
      const url = URL.createObjectURL(response.data as Blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = `assets-${report}.${fmt}`;
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('That report could not be exported. You may not have permission to run it.');
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Asset reports"
        description="Exports run against the live register and respect your permissions."
      />

      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {ASSET_REPORTS.map((report) => (
          <Card key={report.id}>
            <CardHeader>
              <CardTitle className="text-base">{report.label}</CardTitle>
            </CardHeader>
            <CardContent className="flex gap-2">
              <Button
                size="sm"
                variant="outline"
                disabled={busy !== null}
                onClick={() => void download(report.id, 'csv')}
              >
                {busy === `${report.id}-csv` ? 'Exporting…' : 'CSV'}
              </Button>
              <Button
                size="sm"
                variant="outline"
                disabled={busy !== null}
                onClick={() => void download(report.id, 'xlsx')}
              >
                {busy === `${report.id}-xlsx` ? 'Exporting…' : 'Excel'}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
