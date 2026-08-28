'use client';

import { Lock, ShieldCheck } from 'lucide-react';
import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { LoadingState } from '@/components/common/loading-state';
import { Modal } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { usePermitted } from '@/components/common/can';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import {
  useCreateRole,
  useDeleteRole,
  usePermissionCatalogue,
  useRoles,
  useUpdateRole,
} from '@/features/roles/hooks';
import { ACTION_LABELS, type Role } from '@/features/roles/types';

interface DraftState {
  name: string;
  description: string;
  permissions: Set<string>;
}

const BLANK: DraftState = { name: '', description: '', permissions: new Set() };

/**
 * Roles and what they grant.
 *
 * The editor is a matrix rather than a flat checklist: 72 permissions in one
 * column is unreadable, and the question an administrator is actually asking --
 * "what can this role do to employees?" -- is a row, not a scroll.
 */
export function RoleManagementPage(): React.JSX.Element {
  const [editing, setEditing] = React.useState<Role | null>(null);
  const [isOpen, setIsOpen] = React.useState(false);
  const [draft, setDraft] = React.useState<DraftState>(BLANK);
  const [confirmDelete, setConfirmDelete] = React.useState<Role | null>(null);

  const roles = useRoles();
  const catalogue = usePermissionCatalogue();
  const create = useCreateRole();
  const update = useUpdateRole(editing?.id ?? '');
  const remove = useDeleteRole();

  const mayEdit = usePermitted({ permission: 'roles:update' });
  const mayCreate = usePermitted({ permission: 'roles:create' });
  const mayDelete = usePermitted({ permission: 'roles:delete' });

  const open = (role: Role | null): void => {
    setEditing(role);
    setDraft(
      role
        ? {
            name: role.name,
            description: role.description ?? '',
            permissions: new Set(role.permissions),
          }
        : { ...BLANK, permissions: new Set() },
    );
    setIsOpen(true);
  };

  const toggle = (code: string): void => {
    setDraft((current) => {
      const next = new Set(current.permissions);
      if (next.has(code)) next.delete(code);
      else next.add(code);
      return { ...current, permissions: next };
    });
  };

  const toggleModule = (codes: string[], on: boolean): void => {
    setDraft((current) => {
      const next = new Set(current.permissions);
      for (const code of codes) {
        if (on) next.add(code);
        else next.delete(code);
      }
      return { ...current, permissions: next };
    });
  };

  const save = (): void => {
    const permissions = [...draft.permissions];
    if (editing) {
      // Name is omitted for a system role: the API refuses to rename one, and
      // sending it unchanged would still be refused on a strict comparison.
      update.mutate(
        editing.is_system
          ? { description: draft.description || null, permissions }
          : { name: draft.name, description: draft.description || null, permissions },
        {
          onSuccess: () => {
            setIsOpen(false);
            setEditing(null);
          },
        },
      );
    } else {
      create.mutate(
        { name: draft.name, description: draft.description || null, permissions },
        {
          onSuccess: () => {
            setIsOpen(false);
          },
        },
      );
    }
  };

  const columns: DataTableColumn<Role>[] = [
    {
      id: 'name',
      header: 'Role',
      cell: (row) => (
        <div className="space-y-0.5">
          <div className="flex items-center gap-2">
            <span className="font-medium">{row.name}</span>
            {row.is_system ? (
              <Badge variant="outline" className="gap-1">
                <Lock className="size-3" aria-hidden="true" />
                System
              </Badge>
            ) : null}
          </div>
          {row.description ? (
            <p className="text-muted-foreground line-clamp-1 text-sm">{row.description}</p>
          ) : null}
        </div>
      ),
    },
    {
      id: 'permissions',
      header: 'Permissions',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{row.permissions.length}</span>,
    },
    {
      id: 'holders',
      header: 'Held by',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{row.user_count}</span>,
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => (
        <Badge variant={row.status === 'active' ? 'success' : 'outline'}>
          {row.status === 'active' ? 'Active' : 'Inactive'}
        </Badge>
      ),
    },
    {
      id: 'actions',
      header: '',
      align: 'right',
      cell: (row) => (
        <div className="flex justify-end gap-2">
          <Button
            onClick={() => {
              open(row);
            }}
            size="sm"
            variant="outline"
          >
            {mayEdit ? 'Edit' : 'View'}
          </Button>
          {mayDelete && !row.is_system ? (
            <Button
              onClick={() => {
                setConfirmDelete(row);
              }}
              size="sm"
              variant="outline"
            >
              Delete
            </Button>
          ) : null}
        </div>
      ),
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Roles & permissions"
        description="What each role may do. Permissions are the union of every active role a person holds."
        actions={
          mayCreate ? (
            <Button
              onClick={() => {
                open(null);
              }}
            >
              Create role
            </Button>
          ) : undefined
        }
      />

      <DataTable
        columns={columns}
        emptyDescription="No roles are configured."
        emptyTitle="Nothing configured"
        error={roles.error}
        getRowId={(row) => row.id}
        isLoading={roles.isPending}
        onRetry={() => void roles.refetch()}
        rows={roles.data?.items ?? []}
      />

      <Modal
        onOpenChange={setIsOpen}
        open={isOpen}
        size="xl"
        title={editing ? editing.name : 'Create a role'}
        description={
          editing?.is_system
            ? 'A system role cannot be renamed, but what it grants is your decision.'
            : 'Choose what this role may do. Saving replaces its permissions entirely.'
        }
        footer={
          <>
            <Button
              onClick={() => {
                setIsOpen(false);
              }}
              variant="outline"
            >
              {mayEdit ? 'Cancel' : 'Close'}
            </Button>
            {mayEdit ? (
              <Button
                disabled={!draft.name.trim()}
                isLoading={create.isPending || update.isPending}
                onClick={save}
              >
                Save
              </Button>
            ) : null}
          </>
        }
      >
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label htmlFor="role-name">Name</Label>
              <Input
                disabled={!mayEdit || editing?.is_system === true}
                id="role-name"
                onChange={(event) => {
                  setDraft((current) => ({ ...current, name: event.target.value }));
                }}
                value={draft.name}
              />
              {editing?.is_system ? (
                <p className="text-muted-foreground text-sm">
                  System roles are reconciled on every deployment, so a rename would come back.
                </p>
              ) : null}
            </div>
            <div className="space-y-1.5">
              <Label htmlFor="role-description">Description</Label>
              <Textarea
                disabled={!mayEdit}
                id="role-description"
                onChange={(event) => {
                  setDraft((current) => ({ ...current, description: event.target.value }));
                }}
                rows={2}
                value={draft.description}
              />
            </div>
          </div>

          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-medium">Permissions</h3>
              <span className="text-muted-foreground text-sm tabular-nums">
                {draft.permissions.size} selected
              </span>
            </div>

            {catalogue.isPending ? (
              <LoadingState />
            ) : (
              <div className="max-h-[26rem] space-y-4 overflow-y-auto pr-1">
                {(catalogue.data ?? []).map((group) => (
                  <Card key={group.group}>
                    <CardHeader className="pb-3">
                      <CardTitle className="text-sm">{group.label}</CardTitle>
                    </CardHeader>
                    <CardContent className="space-y-3">
                      {group.modules.map((module) => {
                        const codes = module.permissions.map((item) => item.code);
                        const all = codes.every((code) => draft.permissions.has(code));
                        const some = !all && codes.some((code) => draft.permissions.has(code));

                        return (
                          <div className="space-y-1.5" key={module.module}>
                            <div className="flex items-center gap-2">
                              <Checkbox
                                aria-label={`All ${module.label} permissions`}
                                checked={all ? true : some ? 'indeterminate' : false}
                                disabled={!mayEdit}
                                id={`module-${module.module}`}
                                onCheckedChange={(value) => {
                                  toggleModule(codes, value === true);
                                }}
                              />
                              <Label className="font-medium" htmlFor={`module-${module.module}`}>
                                {module.label}
                              </Label>
                            </div>
                            <div className="flex flex-wrap gap-x-5 gap-y-2 pl-6">
                              {module.permissions.map((permission) => (
                                <div className="flex items-center gap-2" key={permission.code}>
                                  <Checkbox
                                    checked={draft.permissions.has(permission.code)}
                                    disabled={!mayEdit}
                                    id={permission.code}
                                    onCheckedChange={() => {
                                      toggle(permission.code);
                                    }}
                                  />
                                  <Label className="font-normal" htmlFor={permission.code}>
                                    {ACTION_LABELS[permission.action] ?? permission.action}
                                  </Label>
                                </div>
                              ))}
                            </div>
                          </div>
                        );
                      })}
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </div>
        </div>
      </Modal>

      <Modal
        confirmLabel="Delete role"
        confirmVariant="destructive"
        description={
          confirmDelete
            ? confirmDelete.user_count > 0
              ? `${String(confirmDelete.user_count)} account(s) still hold this role. Revoke it from them first.`
              : 'This cannot be undone.'
            : undefined
        }
        isConfirming={remove.isPending}
        onConfirm={() => {
          if (confirmDelete) {
            remove.mutate(confirmDelete.id, {
              onSuccess: () => {
                setConfirmDelete(null);
              },
            });
          }
        }}
        onOpenChange={(open) => {
          if (!open) setConfirmDelete(null);
        }}
        open={confirmDelete !== null}
        size="sm"
        title={`Delete ${confirmDelete?.name ?? 'role'}?`}
      />
    </div>
  );
}

/** Shown on the role screen's empty state and in docs examples. */
export const ROLE_SCREEN_ICON = ShieldCheck;
