'use client';

import { ArchiveRestore, ArrowLeft, CheckCircle2, KeyRound, MinusCircle, Pencil, Trash2 } from 'lucide-react';
import Link from 'next/link';
import { useRouter, useSearchParams } from 'next/navigation';
import * as React from 'react';

import { DetailSection, type DetailItem } from '@/components/common/detail-view';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { ConfirmDialog } from '@/components/common/modal';
import { PageHeader } from '@/components/common/page-header';
import { ProfileCard } from '@/components/common/profile-card';
import { StatusBadge } from '@/components/common/status-badge';
import { useAuth } from '@/components/providers/auth-provider';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ResetPasswordDialog } from '@/features/users/components/reset-password-dialog';
import { useUser, useUserLifecycleAction } from '@/features/users/hooks/use-users';
import { GENDER_LABELS } from '@/features/users/types/user.types';
import { useDisclosure } from '@/hooks/use-disclosure';
import { formatDate, formatDateTime } from '@/lib/utils';

const BASE_PATH = '/users';

/** The read-only profile page for one user. */
export function UserDetailPage({ userId }: { userId: string }): React.JSX.Element {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { user: currentUser } = useAuth();

  const query = useUser(userId);
  const activate = useUserLifecycleAction('activate');
  const deactivate = useUserLifecycleAction('deactivate');
  const archive = useUserLifecycleAction('archive');
  const restore = useUserLifecycleAction('restore');

  const confirmArchive = useDisclosure(false);
  // Opened directly from the list's "Reset password" action via ?reset=1.
  const resetDialog = useDisclosure(searchParams.get('reset') === '1');

  if (query.isPending) {
    return <LoadingState message="Loading user…" />;
  }

  if (query.isError) {
    return (
      <div className="space-y-6">
        <PageHeader title="User" />
        <ErrorState
          error={query.error}
          onRetry={() => {
            void query.refetch();
          }}
        />
      </div>
    );
  }

  const user = query.data;
  const isArchived = user.deleted_at !== null;
  const isSelf = currentUser?.id === user.id;
  const organization = user.organization;

  const basicInformation: DetailItem[] = [
    { label: 'First name', value: user.first_name },
    { label: 'Last name', value: user.last_name },
    { label: 'Gender', value: user.gender ? GENDER_LABELS[user.gender] : null },
    { label: 'Date of birth', value: user.date_of_birth ? formatDate(user.date_of_birth) : null },
  ];

  const contactInformation: DetailItem[] = [
    { label: 'Official email', value: user.email },
    { label: 'Personal email', value: user.personal_email },
    { label: 'Mobile number', value: user.phone_number },
  ];

  const organizationInformation: DetailItem[] = [
    { label: 'Business unit', value: organization.business_unit?.name ?? null },
    { label: 'Team', value: organization.team?.name ?? null },
    { label: 'Designation', value: organization.designation?.name ?? null },
    { label: 'Grade', value: organization.grade?.name ?? null },
    { label: 'Location', value: organization.location?.name ?? null },
    { label: 'Employment type', value: organization.employment_type?.name ?? null },
    { label: 'Joining date', value: user.joining_date ? formatDate(user.joining_date) : null },
  ];

  const accountAndLogin: DetailItem[] = [
    { label: 'Staff code', value: <span className="font-mono text-xs">{user.user_code}</span> },
    { label: 'Username', value: <span className="font-mono text-xs">{user.username}</span> },
    { label: 'Status', value: <StatusBadge status={user.status} archived={isArchived} /> },
    { label: 'Last sign-in', value: user.last_login_at ? formatDateTime(user.last_login_at) : 'Never' },
    {
      label: 'Password last changed',
      value: user.password_changed_at ? formatDateTime(user.password_changed_at) : null,
    },
    {
      label: 'Must change password',
      value: user.force_password_change ? 'Yes, at next sign-in' : 'No',
    },
  ];

  const recordHistory: DetailItem[] = [
    { label: 'Created', value: formatDateTime(user.created_at) },
    { label: 'Last updated', value: formatDateTime(user.updated_at) },
    ...(isArchived ? [{ label: 'Archived', value: formatDateTime(user.deleted_at) }] : []),
    { label: 'Record ID', value: <span className="font-mono text-xs">{user.id}</span>, wide: true },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title={user.full_name}
        description={organization.designation?.name ?? 'User'}
        actions={
          <>
            <Button variant="outline" asChild>
              <Link href={BASE_PATH}>
                <ArrowLeft aria-hidden="true" />
                Back
              </Link>
            </Button>

            {isArchived ? (
              <Button
                onClick={() => {
                  restore.mutate(user.id);
                }}
                isLoading={restore.isPending}
              >
                <ArchiveRestore aria-hidden="true" />
                Restore
              </Button>
            ) : (
              <>
                <Button variant="outline" asChild>
                  <Link href={`${BASE_PATH}/${user.id}/edit`}>
                    <Pencil aria-hidden="true" />
                    Edit
                  </Link>
                </Button>
                <Button variant="outline" onClick={resetDialog.open}>
                  <KeyRound aria-hidden="true" />
                  Reset password
                </Button>
                {user.is_active ? (
                  <Button
                    variant="outline"
                    disabled={isSelf}
                    isLoading={deactivate.isPending}
                    onClick={() => {
                      deactivate.mutate(user.id);
                    }}
                  >
                    <MinusCircle aria-hidden="true" />
                    Deactivate
                  </Button>
                ) : (
                  <Button
                    variant="outline"
                    isLoading={activate.isPending}
                    onClick={() => {
                      activate.mutate(user.id);
                    }}
                  >
                    <CheckCircle2 aria-hidden="true" />
                    Activate
                  </Button>
                )}
                <Button variant="destructive" disabled={isSelf} onClick={confirmArchive.open}>
                  <Trash2 aria-hidden="true" />
                  Archive
                </Button>
              </>
            )}
          </>
        }
      />

      {isArchived ? (
        <Alert variant="warning">
          <AlertDescription>
            This account is archived. It cannot sign in, and it is hidden from the directory. Records that
            reference it are unaffected.
          </AlertDescription>
        </Alert>
      ) : null}

      {isSelf && !isArchived ? (
        <Alert variant="info">
          <AlertDescription>
            This is your own account, so deactivating and archiving are unavailable — they would lock you out.
            Ask another administrator if you need either.
          </AlertDescription>
        </Alert>
      ) : null}

      <ProfileCard
        name={user.full_name}
        subtitle={user.email}
        photoUrl={user.avatar_url}
        badges={
          <>
            <StatusBadge status={user.status} archived={isArchived} />
            <Badge variant="outline" className="font-mono">
              {user.user_code}
            </Badge>
            {user.is_superuser ? <Badge>Administrator</Badge> : null}
            {user.is_locked ? <Badge variant="destructive">Locked</Badge> : null}
          </>
        }
        facts={[
          { label: 'Business unit', value: organization.business_unit?.name ?? '—' },
          { label: 'Location', value: organization.location?.name ?? '—' },
          { label: 'Joined', value: user.joining_date ? formatDate(user.joining_date) : '—' },
        ]}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <DetailSection title="Basic information" items={basicInformation} />
        <DetailSection title="Contact information" items={contactInformation} />
        <DetailSection title="Organization" items={organizationInformation} className="lg:col-span-2" />
        <DetailSection title="Account and sign-in" items={accountAndLogin} />
        <DetailSection title="Record history" items={recordHistory} />
      </div>

      <ResetPasswordDialog user={user} open={resetDialog.isOpen} onOpenChange={resetDialog.setOpen} />

      <ConfirmDialog
        open={confirmArchive.isOpen}
        onOpenChange={confirmArchive.setOpen}
        title="Archive this user?"
        description={`${user.full_name} (${user.user_code}) will lose access immediately and every active session will end. You can restore the account at any time.`}
        confirmLabel="Archive"
        destructive
        isConfirming={archive.isPending}
        onConfirm={() => {
          archive.mutate(user.id, {
            onSuccess: () => {
              router.push(BASE_PATH);
            },
            onSettled: () => {
              confirmArchive.close();
            },
          });
        }}
      />
    </div>
  );
}
