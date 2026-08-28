'use client';

import { zodResolver } from '@hookform/resolvers/zod';
import { Lock } from 'lucide-react';
import * as React from 'react';
import { useForm } from 'react-hook-form';

import { DetailSection, type DetailItem } from '@/components/common/detail-view';
import { FormLayout, FormSection } from '@/components/common/form-layout';
import { LoadingState } from '@/components/common/loading-state';
import { ErrorState } from '@/components/common/error-state';
import { PageHeader } from '@/components/common/page-header';
import { SelectField } from '@/components/common/select-field';
import { TextField } from '@/components/common/text-field';
import { UserAvatar } from '@/components/common/user-avatar';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Form } from '@/components/ui/form';
import { useMyProfile, useSetMyAddress, useUpdateMyProfile } from '@/features/self-service/hooks';
import {
  myAddressSchema,
  myProfileSchema,
  type MyAddressFormValues,
  type MyProfileFormValues,
} from '@/features/self-service/schema';
import { ADDRESS_TYPE_OPTIONS } from '@/features/self-service/types';

/**
 * My Profile.
 *
 * Two halves, and the split is the point of the screen. What an employee owns
 * -- how to reach them, and who to call in an emergency -- is a form. What the
 * organization decides -- where they sit, what they are called, when they
 * joined -- is a read-only panel with a padlock on it.
 *
 * The read-only half is shown rather than hidden: people need to see the team
 * they are recorded against in order to notice that it is wrong, and hiding it
 * only moves that discovery to payroll.
 *
 * `editable_fields` comes from the server. The form does not decide what may be
 * changed; it renders the answer.
 */

function value(text: string | null | undefined): React.ReactNode {
  return text ? text : <span className="text-muted-foreground">—</span>;
}

function LockedItem({ label, text }: { label: string; text: string | null | undefined }): DetailItem {
  return { label, value: value(text) };
}

export function MyProfilePage(): React.JSX.Element {
  const profile = useMyProfile();
  const update = useUpdateMyProfile();
  const setAddress = useSetMyAddress();

  const form = useForm<MyProfileFormValues>({
    resolver: zodResolver(myProfileSchema),
    defaultValues: {
      personal_email: '',
      mobile_number: '',
      alternate_number: '',
      emergency_contact_name: '',
      emergency_contact_number: '',
      emergency_contact_relationship: '',
      photo_url: '',
    },
  });

  const addressForm = useForm<MyAddressFormValues>({
    resolver: zodResolver(myAddressSchema),
    defaultValues: {
      address_type: 'current',
      address_line1: '',
      address_line2: '',
      landmark: '',
      city: '',
      state: '',
      country: '',
      postal_code: '',
    },
  });

  const data = profile.data;

  // Populated once the record arrives, and again if it is refetched. `reset`
  // rather than `defaultValues`, because the form mounts before the fetch
  // resolves and defaults are only read on the first render.
  React.useEffect(() => {
    if (!data) return;
    form.reset({
      personal_email: data.personal_email ?? '',
      mobile_number: data.mobile_number ?? '',
      alternate_number: data.alternate_number ?? '',
      emergency_contact_name: data.emergency_contact_name ?? '',
      emergency_contact_number: data.emergency_contact_number ?? '',
      emergency_contact_relationship: data.emergency_contact_relationship ?? '',
      photo_url: data.photo_url ?? '',
    });

    const current = data.addresses.find((address) => address.address_type === 'current');
    if (current) {
      addressForm.reset({
        address_type: 'current',
        address_line1: current.address_line1,
        address_line2: current.address_line2 ?? '',
        landmark: current.landmark ?? '',
        city: current.city,
        state: current.state,
        country: current.country,
        postal_code: current.postal_code,
      });
    }
  }, [data, form, addressForm]);

  const submit = form.handleSubmit((values) => {
    update.mutate(values);
  });

  const submitAddress = addressForm.handleSubmit((values) => {
    setAddress.mutate(values);
  });

  if (profile.isPending) return <LoadingState message="Loading your profile…" />;
  if (profile.error || !data) {
    return <ErrorState error={profile.error} onRetry={() => void profile.refetch()} />;
  }

  const employment: DetailItem[] = [
    LockedItem({ label: 'Employee ID', text: data.employee_code }),
    LockedItem({ label: 'Official email', text: data.official_email }),
    LockedItem({ label: 'Business unit', text: data.organization.business_unit?.name }),
    LockedItem({ label: 'Team', text: data.organization.team?.name }),
    LockedItem({ label: 'Designation', text: data.organization.designation?.name }),
    LockedItem({ label: 'Grade', text: data.organization.grade?.name }),
    LockedItem({ label: 'Reporting manager', text: data.reporting_manager?.full_name }),
    LockedItem({ label: 'Joining date', text: data.joining_date }),
    LockedItem({ label: 'Employment type', text: data.organization.employment_type?.name }),
    LockedItem({ label: 'Work location', text: data.organization.work_location?.name }),
    LockedItem({ label: 'Employment status', text: data.employment_status }),
    LockedItem({ label: 'Work mode', text: data.work_mode }),
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Profile"
        description="Change how you can be reached. Everything the organization decides is read-only here."
      />

      <Card>
        <CardContent className="flex flex-wrap items-center gap-4 pt-6">
          <UserAvatar name={data.full_name} photoUrl={data.photo_url} size="lg" />
          <div className="min-w-0">
            <p className="truncate text-lg font-semibold">{data.full_name}</p>
            <p className="text-muted-foreground truncate text-sm">
              {data.organization.designation?.name ?? 'No designation'} · {data.employee_code}
            </p>
          </div>
        </CardContent>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Contact details</CardTitle>
            <CardDescription>These are yours to change.</CardDescription>
          </CardHeader>
          <CardContent>
            <Form {...form}>
              <FormLayout onSubmit={(event) => void submit(event)}>
                <FormSection title="How to reach you">
                  <TextField
                    control={form.control}
                    label="Personal email"
                    name="personal_email"
                    type="email"
                  />
                  <TextField control={form.control} label="Mobile number" name="mobile_number" />
                  <TextField control={form.control} label="Alternate number" name="alternate_number" />
                  <TextField
                    control={form.control}
                    description="A link to an image."
                    label="Profile photo URL"
                    name="photo_url"
                  />
                </FormSection>

                <FormSection title="Emergency contact">
                  <TextField control={form.control} label="Name" name="emergency_contact_name" />
                  <TextField control={form.control} label="Number" name="emergency_contact_number" />
                  <TextField
                    control={form.control}
                    label="Relationship"
                    name="emergency_contact_relationship"
                    placeholder="Spouse, parent, sibling…"
                  />
                </FormSection>

                <div className="flex justify-end">
                  <Button isLoading={update.isPending} type="submit">
                    Save changes
                  </Button>
                </div>
              </FormLayout>
            </Form>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Address</CardTitle>
            <CardDescription>Your current or permanent address.</CardDescription>
          </CardHeader>
          <CardContent>
            <Form {...addressForm}>
              <FormLayout onSubmit={(event) => void submitAddress(event)}>
                <FormSection title="Where you live">
                  <SelectField
                    control={addressForm.control}
                    label="Address type"
                    name="address_type"
                    options={ADDRESS_TYPE_OPTIONS.map((option) => ({ ...option }))}
                    required
                  />
                  <div />
                  <TextField
                    className="sm:col-span-2"
                    control={addressForm.control}
                    label="Address line 1"
                    name="address_line1"
                    required
                  />
                  <TextField
                    className="sm:col-span-2"
                    control={addressForm.control}
                    label="Address line 2"
                    name="address_line2"
                  />
                  <TextField control={addressForm.control} label="Landmark" name="landmark" />
                  <TextField control={addressForm.control} label="City" name="city" required />
                  <TextField control={addressForm.control} label="State" name="state" required />
                  <TextField control={addressForm.control} label="Country" name="country" required />
                  <TextField control={addressForm.control} label="Postal code" name="postal_code" required />
                </FormSection>

                <div className="flex justify-end">
                  <Button isLoading={setAddress.isPending} type="submit">
                    Save address
                  </Button>
                </div>
              </FormLayout>
            </Form>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-sm">
            <Lock className="size-4" aria-hidden="true" />
            Employment details
          </CardTitle>
          <CardDescription>
            Set by HR. If something here is wrong, ask them to correct it — the portal cannot.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <DetailSection items={employment} title="" />
        </CardContent>
      </Card>
    </div>
  );
}
