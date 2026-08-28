'use client';

import { Lock, Pencil } from 'lucide-react';
import * as React from 'react';

import { usePermitted } from '@/components/common/can';
import { EmptyState } from '@/components/common/empty-state';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from '@/components/ui/sonner';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { api } from '@/lib/api/client';
import type { AppError } from '@/lib/errors';

/**
 * Runtime settings, finally editable.
 *
 * This screen replaced a permanent "editable settings arrive with RBAC" empty
 * state whose stated blocker had shipped five phases earlier. The rules the
 * server enforces are mirrored, not re-implemented: a locked row renders its
 * value with a padlock and no edit control, and the server refuses the edit
 * anyway if a client contrives one.
 *
 * Values are JSON. The editor takes the raw text and parses it, so a boolean
 * stays a boolean and a number a number — stringifying everything is how a
 * setting that reads `30` becomes `"30"` and breaks whoever consumes it.
 */

export interface AppSettingRow {
  id: string;
  key: string;
  value: unknown;
  category: string;
  description: string | null;
  is_public: boolean;
  is_editable: boolean;
  updated_at: string;
}

const settingsKey = ['settings'] as const;

const useSettings = () =>
  useQuery({ queryKey: settingsKey, queryFn: () => api.get<AppSettingRow[]>('/settings') });

const useUpdateSetting = () => {
  const queryClient = useQueryClient();
  return useMutation<AppSettingRow, AppError, { key: string; value: unknown }>({
    mutationFn: ({ key, value }) => api.patch<AppSettingRow>(`/settings/${key}`, { value }),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: settingsKey });
      toast.success('Setting updated');
    },
    onError: (error) => toast.error(error.message),
  });
};

function display(value: unknown): string {
  if (value === null || value === undefined) return '—';
  if (typeof value === 'string') return value;
  return JSON.stringify(value);
}

function Editor({ setting, onClose }: { setting: AppSettingRow; onClose: () => void }): React.JSX.Element {
  const update = useUpdateSetting();
  const [text, setText] = React.useState(() =>
    typeof setting.value === 'string' ? setting.value : JSON.stringify(setting.value ?? null),
  );
  const [problem, setProblem] = React.useState<string | null>(null);

  const submit = (): void => {
    let value: unknown = text;
    // Accept what JSON accepts; a bare word stays a string. This keeps the
    // stored type honest without making operators write quotes by hand.
    if (typeof setting.value !== 'string') {
      try {
        value = JSON.parse(text);
      } catch {
        setProblem(
          'This setting holds a non-text value, so the input must be valid JSON — e.g. 30, true, or ["a","b"].',
        );
        return;
      }
    }
    update.mutate({ key: setting.key, value }, { onSuccess: onClose });
  };

  return (
    <Modal
      open
      onOpenChange={(next) => {
        if (!next) onClose();
      }}
      title={setting.key}
      description={setting.description ?? undefined}
      confirmLabel="Save"
      onConfirm={submit}
      isConfirming={update.isPending}
    >
      <div className="space-y-2">
        <Label htmlFor="setting-value">Value</Label>
        <Input
          id="setting-value"
          value={text}
          onChange={(event) => {
            setText(event.target.value);
            setProblem(null);
          }}
        />
        {problem ? <p className="text-destructive text-xs">{problem}</p> : null}
      </div>
    </Modal>
  );
}

export function SettingsScreen(): React.JSX.Element {
  const query = useSettings();
  const canEdit = usePermitted({ permission: 'settings:update' });
  const [editing, setEditing] = React.useState<AppSettingRow | null>(null);

  const rows = query.data ?? [];
  const categories = [...new Set(rows.map((row) => row.category))].sort();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description="Runtime configuration, editable without a redeploy. Locked rows show values the platform enforces in code."
      />

      {query.isLoading ? (
        <LoadingState message="Loading settings…" />
      ) : query.error ? (
        <ErrorState error={query.error} onRetry={() => void query.refetch()} />
      ) : rows.length === 0 ? (
        <EmptyState
          title="No settings recorded"
          description="Run the seed command to create the baseline configuration."
        />
      ) : (
        categories.map((category) => (
          <Card key={category}>
            <CardHeader className="pb-3">
              <CardTitle className="text-base capitalize">{category}</CardTitle>
            </CardHeader>
            <CardContent>
              <ul className="divide-border divide-y">
                {rows
                  .filter((row) => row.category === category)
                  .map((row) => (
                    <li key={row.id} className="flex items-center justify-between gap-4 py-3">
                      <div className="min-w-0">
                        <p className="text-sm font-medium">{row.key}</p>
                        {row.description ? (
                          <p className="text-muted-foreground text-xs">{row.description}</p>
                        ) : null}
                      </div>
                      <div className="flex shrink-0 items-center gap-3">
                        <Badge variant="outline" className="max-w-56 truncate font-mono">
                          {display(row.value)}
                        </Badge>
                        {row.is_editable ? (
                          canEdit ? (
                            <Button
                              size="sm"
                              variant="ghost"
                              onClick={() => setEditing(row)}
                              aria-label={`Edit ${row.key}`}
                            >
                              <Pencil className="size-4" aria-hidden="true" />
                            </Button>
                          ) : null
                        ) : (
                          <span title="Enforced by the platform; not editable here.">
                            <Lock className="text-muted-foreground size-4" aria-hidden="true" />
                          </span>
                        )}
                      </div>
                    </li>
                  ))}
              </ul>
            </CardContent>
          </Card>
        ))
      )}

      {editing ? <Editor setting={editing} onClose={() => setEditing(null)} /> : null}
    </div>
  );
}
