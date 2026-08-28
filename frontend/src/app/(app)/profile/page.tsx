'use client';

import * as React from 'react';

import { DetailSection, type DetailItem } from '@/components/common/detail-view';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { ProfileCard } from '@/components/common/profile-card';
import { StatusBadge } from '@/components/common/status-badge';
import { useAuth } from '@/components/providers/auth-provider';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ChangePasswordForm } from '@/features/auth/components/change-password-form';
import { ProfileForm } from '@/features/users/components/profile-form';
import { GENDER_LABELS } from '@/types/user';
import { formatDate, formatDateTime } from '@/lib/utils';

/** Self-service profile and credential management. */
export default function ProfilePage(): React.JSX.Element {
  const { user } = useAuth();

  if (!user) {
    return <LoadingState message="Loading your profile…" />;
  }

  const organization = user.organization;

  const basicInformation: DetailItem[] = [
    { label: 'First name', value: user.first_name },
    { label: 'Last name', value: user.last_name },
    { label: 'Gender', value: user.gender ? GENDER_LABELS[user.gender] : null },
    { label: 'Date of birth', value: user.date_of_birth ? formatDate(user.date_of_birth) : null },
    { label: 'Official email', value: user.email },
    { label: 'Username', value: <span className="font-mono text-xs">{user.username}</span> },
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

  return (
    <div className="space-y-6">
      <PageHeader
        title="My profile"
        description="Your details, and the contact information you can maintain yourself."
      />

      <ProfileCard
        name={user.full_name}
        subtitle={organization.designation?.name ?? user.email}
        photoUrl={user.avatar_url}
        badges={
          <>
            <StatusBadge status={user.status} />
            <Badge variant="outline" className="font-mono">
              {user.user_code}
            </Badge>
            {user.is_superuser ? <Badge>Administrator</Badge> : null}
          </>
        }
        facts={[
          { label: 'Business unit', value: organization.business_unit?.name ?? '—' },
          { label: 'Last sign-in', value: formatDateTime(user.last_login_at) },
        ]}
      />

      <div className="grid gap-6 lg:grid-cols-2">
        <DetailSection title="Basic information" items={basicInformation} />
        <DetailSection title="Organization" items={organizationInformation} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Contact details</CardTitle>
            <CardDescription>The fields you can maintain yourself.</CardDescription>
          </CardHeader>
          <CardContent>
            <ProfileForm />
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Password</CardTitle>
            <CardDescription>Choose a strong password you do not use anywhere else.</CardDescription>
          </CardHeader>
          <CardContent>
            <ChangePasswordForm />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
