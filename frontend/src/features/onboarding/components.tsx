'use client';
import { zodResolver } from '@hookform/resolvers/zod';
import Link from 'next/link';
import * as React from 'react';
import { useForm, type FieldPath } from 'react-hook-form';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from '@/components/ui/sonner';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { onboardingApi } from './api';
import {
  useOnboardingCase,
  useOnboardingDashboard,
  useOnboardingMutation,
  usePortal,
  useWelcome,
} from './hooks';
import { profileSchema, type ProfileFormValues } from './schema';
import type { OnboardingDocument, OnboardingTask, PortalData, WelcomeData } from './types';

const human = (value: string) => value.replaceAll('_', ' ').replace(/^./, (x) => x.toUpperCase());
export function ProgressTracker({ value }: { value: number }) {
  return (
    <div aria-label={`Onboarding progress ${String(value)}%`} className="space-y-2">
      <div className="flex justify-between text-sm">
        <span>Progress</span>
        <b>{value}%</b>
      </div>
      <div className="bg-muted h-3 overflow-hidden rounded-full">
        <div className="bg-primary h-full transition-all" style={{ width: `${String(value)}%` }} />
      </div>
    </div>
  );
}
export function Stepper({ steps, current }: { steps: string[]; current: number }) {
  return (
    <ol className="grid gap-2 md:grid-cols-4">
      {steps.map((step, index) => (
        <li
          className={`rounded-md border p-3 text-sm ${index <= current ? 'border-primary bg-primary/5' : ''}`}
          key={step}
        >
          {index + 1}. {step}
        </li>
      ))}
    </ol>
  );
}
export function OnboardingDashboard() {
  const query = useOnboardingDashboard();
  const [exporting, setExporting] = React.useState(false);
  const download = async (): Promise<void> => {
    setExporting(true);
    try {
      await onboardingApi.exportReport('csv');
    } catch {
      toast.error('The export could not be prepared.');
    } finally {
      setExporting(false);
    }
  };
  if (query.isPending) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} />;
  return (
    <div className="space-y-6">
      <PageHeader
        title="Preboarding & Onboarding"
        description="Candidate readiness, joining schedules and cross-functional onboarding work."
        actions={
          <div className="flex gap-2">
            <Button variant="outline" isLoading={exporting} onClick={() => void download()}>
              CSV report
            </Button>
            <Button asChild>
              <Link href="/onboarding/start">Start preboarding</Link>
            </Button>
          </div>
        }
      />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {Object.entries(query.data).map(([key, value]) => (
          <StatCard key={key} label={human(key)} value={Number(value)} />
        ))}
      </div>
    </div>
  );
}
export function StartPreboarding() {
  const [offerId, setOfferId] = React.useState('');
  const [userId, setUserId] = React.useState('');
  const mutation = useOnboardingMutation((data: { offer_id: string; user_id: string }) =>
    onboardingApi.start(data),
  );
  return (
    <div className="space-y-6">
      <PageHeader
        title="Start Preboarding"
        description="Create a secure portal for a candidate with an accepted offer."
      />
      <Card>
        <CardContent className="grid gap-4 p-6">
          <Field label="Accepted offer ID">
            <Input value={offerId} onChange={(e) => setOfferId(e.target.value)} />
          </Field>
          <Field label="Candidate user ID">
            <Input value={userId} onChange={(e) => setUserId(e.target.value)} />
          </Field>
          <Button
            isLoading={mutation.isPending}
            onClick={() => mutation.mutate({ offer_id: offerId, user_id: userId })}
          >
            Create candidate portal
          </Button>
          {mutation.data ? (
            <Button asChild variant="outline">
              <Link href={`/onboarding/portal/${mutation.data.profile.id}`}>Open portal</Link>
            </Button>
          ) : null}
        </CardContent>
      </Card>
    </div>
  );
}
export function CandidatePortal({ id }: { id: string }) {
  const query = usePortal(id);
  if (query.isPending) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} />;
  return <PortalContent data={query.data} />;
}
function PortalContent({ data }: { data: PortalData }) {
  const mutation = useOnboardingMutation((values: ProfileFormValues) =>
    onboardingApi.update(data.profile.id, values),
  );
  const p = data.profile;
  const form = useForm<ProfileFormValues>({
    resolver: zodResolver(profileSchema),
    defaultValues: {
      joining_date: p.joining_date,
      joining_confirmed: p.joining_confirmed,
      first_name: p.first_name,
      last_name: p.last_name,
      date_of_birth: p.date_of_birth ?? '',
      gender: (p.gender ?? 'prefer_not_to_say') as ProfileFormValues['gender'],
      blood_group: (p.blood_group ?? 'O+') as ProfileFormValues['blood_group'],
      marital_status: (p.marital_status ?? 'single') as ProfileFormValues['marital_status'],
      nationality: p.nationality ?? '',
      personal_email: p.personal_email,
      mobile_number: p.mobile_number,
      emergency_contact: {
        name: p.emergency_contact.name ?? '',
        relationship: p.emergency_contact.relationship ?? '',
        phone_number: p.emergency_contact.phone_number ?? '',
        email: p.emergency_contact.email ?? null,
      },
      addresses: ['current', 'permanent'].map((kind) => {
        const a = p.addresses.find((x) => x.address_type === kind);
        return {
          address_type: kind as 'current' | 'permanent',
          address_line1: a?.address_line1 ?? '',
          address_line2: a?.address_line2 ?? null,
          city: a?.city ?? '',
          state: a?.state ?? '',
          country: a?.country ?? '',
          postal_code: a?.postal_code ?? '',
        };
      }),
      bank_details: {
        bank_name: p.bank_details.bank_name ?? '',
        account_holder_name: p.bank_details.account_holder_name ?? '',
        account_number: p.bank_details.account_number ?? '',
        ifsc_code: p.bank_details.ifsc_code ?? '',
        branch_name: p.bank_details.branch_name ?? '',
      },
      aadhaar_number: p.aadhaar_number ?? '',
      pan_number: p.pan_number ?? '',
    },
  });
  return (
    <form className="space-y-6" onSubmit={form.handleSubmit((v) => mutation.mutate(v))}>
      <PageHeader
        title={`Welcome, ${p.first_name}`}
        description="Complete each step before HR approval."
        actions={
          <Button asChild variant="outline">
            <Link href={`/offers/${p.offer_id}`}>View offer</Link>
          </Button>
        }
      />
      <ProgressTracker value={data.progress_percent} />
      <Stepper
        steps={['Personal details', 'Documents', 'Policies', 'HR approval']}
        current={Math.min(3, Math.floor(data.progress_percent / 25))}
      />
      <Card>
        <CardHeader>
          <CardTitle>Personal and joining information</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          {(
            [
              'first_name',
              'last_name',
              'date_of_birth',
              'nationality',
              'personal_email',
              'mobile_number',
              'joining_date',
            ] as const
          ).map((name) => (
            <Field key={name} label={human(name)}>
              <Input type={name.includes('date') ? 'date' : 'text'} {...form.register(name)} />
            </Field>
          ))}
          <SelectField
            label="Gender"
            values={['male', 'female', 'non_binary', 'prefer_not_to_say']}
            register={form.register('gender')}
          />
          <SelectField
            label="Blood group"
            values={['A+', 'A-', 'B+', 'B-', 'AB+', 'AB-', 'O+', 'O-']}
            register={form.register('blood_group')}
          />
          <SelectField
            label="Marital status"
            values={['single', 'married', 'divorced', 'widowed', 'separated']}
            register={form.register('marital_status')}
          />
          <label className="flex items-center gap-2">
            <input type="checkbox" {...form.register('joining_confirmed')} />I confirm my joining date
          </label>
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Emergency contact</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          {(['name', 'relationship', 'phone_number', 'email'] as const).map((name) => (
            <Field key={name} label={human(name)}>
              <Input {...form.register(`emergency_contact.${name}`)} />
            </Field>
          ))}
        </CardContent>
      </Card>
      {form.getValues('addresses').map((address, index) => (
        <Card key={address.address_type}>
          <CardHeader>
            <CardTitle>{human(address.address_type)} address</CardTitle>
          </CardHeader>
          <CardContent className="grid gap-4 md:grid-cols-2">
            {(['address_line1', 'address_line2', 'city', 'state', 'country', 'postal_code'] as const).map(
              (name) => (
                <Field key={name} label={human(name)}>
                  <Input {...form.register(addressPath(index, name))} />
                </Field>
              ),
            )}
          </CardContent>
        </Card>
      ))}
      <Card>
        <CardHeader>
          <CardTitle>Bank and identity information</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-2">
          {(['bank_name', 'account_holder_name', 'account_number', 'ifsc_code', 'branch_name'] as const).map(
            (name) => (
              <Field key={name} label={human(name)}>
                <Input
                  type={name === 'account_number' ? 'password' : 'text'}
                  {...form.register(`bank_details.${name}`)}
                />
              </Field>
            ),
          )}
          <Field label="Aadhaar number">
            <Input type="password" {...form.register('aadhaar_number')} />
          </Field>
          <Field label="PAN">
            <Input {...form.register('pan_number')} />
          </Field>
        </CardContent>
      </Card>
      <Button type="submit" isLoading={mutation.isPending}>
        Save candidate information
      </Button>
      {Object.keys(form.formState.errors).length ? (
        <p className="text-destructive text-sm">
          Correct the highlighted personal, address, bank, Aadhaar or PAN information.
        </p>
      ) : null}
      <DocumentSection data={data} />
      <PolicySection data={data} />
    </form>
  );
}
function DocumentSection({ data }: { data: PortalData }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Required documents</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <Button asChild>
          <Link href={`/documents/upload?owner_type=candidate&owner_id=${data.profile.candidate_id}`}>
            Upload in Document Vault
          </Link>
        </Button>
        {data.required_documents.map((name) => {
          const document = data.documents.find((x) => x.name.toLowerCase() === name);
          return (
            <div className="flex items-center justify-between border-b py-2" key={name}>
              <span>{human(name)}</span>
              <Badge>{human(document?.status ?? 'pending')}</Badge>
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
function PolicySection({ data }: { data: PortalData }) {
  const mutation = useOnboardingMutation(
    (value: { policy_code: string; policy_name: string; accepted: true }) =>
      onboardingApi.acknowledge(data.profile.id, value),
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle>Policy acknowledgement</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {data.required_policies.map((code) => {
          const done = data.acknowledgements.some((x) => x.policy_code === code);
          return (
            <div className="flex items-center justify-between border-b py-2" key={code}>
              <span>{human(code)}</span>
              {done ? (
                <Badge>Accepted</Badge>
              ) : (
                <Button
                  type="button"
                  variant="outline"
                  onClick={() =>
                    mutation.mutate({ policy_code: code, policy_name: human(code), accepted: true })
                  }
                >
                  Read and accept
                </Button>
              )}
            </div>
          );
        })}
      </CardContent>
    </Card>
  );
}
export function DocumentReviewCard({
  profileId,
  document,
}: {
  profileId: string;
  document: OnboardingDocument;
}) {
  const mutation = useOnboardingMutation(
    (value: { status: 'approved' | 'rejected'; comments: string | null }) =>
      onboardingApi.reviewDocument(profileId, document.id, value),
  );
  return (
    <Card>
      <CardContent className="flex items-center gap-3 p-4">
        <div className="flex-1">
          <b>{document.name}</b>
          <p className="text-muted-foreground text-sm">{human(document.status)}</p>
        </div>
        <Button variant="outline" onClick={() => mutation.mutate({ status: 'approved', comments: null })}>
          Approve
        </Button>
        <Button
          variant="destructive"
          onClick={() => {
            // A rejection needs a reason; Escape or an empty answer aborts.
            const comments = window.prompt('Re-upload reason')?.trim();
            if (comments) mutation.mutate({ status: 'rejected', comments });
          }}
        >
          Reject
        </Button>
      </CardContent>
    </Card>
  );
}
export function HRReview({ id }: { id: string }) {
  const query = usePortal(id);
  const approve = useOnboardingMutation(() => onboardingApi.approve(id));
  const [userId, setUserId] = React.useState('');
  const [email, setEmail] = React.useState('');
  const convert = useOnboardingMutation((data: { user_id: string; official_email: string }) =>
    onboardingApi.convert(id, data),
  );
  if (query.isPending) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} />;
  return (
    <div className="space-y-6">
      <PageHeader
        title={`HR Review — ${query.data.profile.first_name} ${query.data.profile.last_name}`}
        description="Review candidate data, documents and policies before employee conversion."
      />
      <ProgressTracker value={query.data.progress_percent} />
      {query.data.documents.map((document) => (
        <DocumentReviewCard key={document.id} profileId={id} document={document} />
      ))}
      <Card>
        <CardContent className="grid gap-4 p-6">
          <Button onClick={() => approve.mutate(undefined)}>Approve mandatory information</Button>
          <Field label="Existing user ID">
            <Input value={userId} onChange={(e) => setUserId(e.target.value)} />
          </Field>
          <Field label="Official email">
            <Input value={email} onChange={(e) => setEmail(e.target.value)} />
          </Field>
          <Button
            disabled={!query.data.profile.information_approved}
            onClick={() => convert.mutate({ user_id: userId, official_email: email })}
          >
            Convert to employee
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
export function TaskChecklist({ tasks }: { tasks: OnboardingTask[] }) {
  const mutation = useOnboardingMutation((input: { id: string; status: string; comments: string | null }) =>
    onboardingApi.updateTask(input.id, { status: input.status, comments: input.comments }),
  );
  return (
    <div className="space-y-3">
      {tasks.map((task) => (
        <Card key={task.id}>
          <CardContent className="flex items-center gap-3 p-4">
            <div className="flex-1">
              <b>{task.title}</b>
              <p className="text-muted-foreground text-sm">
                {human(task.category)} · due {task.due_date}
              </p>
            </div>
            <select
              className="bg-background h-10 rounded-md border px-2"
              value={task.status}
              onChange={(e) =>
                mutation.mutate({ id: task.id, status: e.target.value, comments: task.comments })
              }
            >
              {['not_started', 'in_progress', 'blocked', 'completed'].map((x) => (
                <option key={x} value={x}>
                  {human(x)}
                </option>
              ))}
            </select>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
type DraftTask = { category: string; title: string; owner_id: string; due_date: string };
export function CaseSetup({ profileId }: { profileId: string }) {
  const [tasks, setTasks] = React.useState<DraftTask[]>([
    { category: 'hr', title: '', owner_id: '', due_date: '' },
  ]);
  const mutation = useOnboardingMutation((value: { tasks: DraftTask[] }) =>
    onboardingApi.createCase(profileId, value),
  );
  const change = (index: number, field: keyof DraftTask, value: string) =>
    setTasks((current) =>
      current.map((task, taskIndex) => (taskIndex === index ? { ...task, [field]: value } : task)),
    );
  return (
    <div className="space-y-6">
      <PageHeader
        title="Configure Onboarding Checklist"
        description="Assign each HR, IT, Administration and Manager task to an owner and due date."
      />
      {tasks.map((task, index) => (
        <Card key={String(index)}>
          <CardContent className="grid gap-3 p-4 md:grid-cols-4">
            <select
              className="bg-background h-10 rounded-md border px-3"
              value={task.category}
              onChange={(event) => change(index, 'category', event.target.value)}
            >
              {['hr', 'it', 'administration', 'manager'].map((category) => (
                <option key={category} value={category}>
                  {human(category)}
                </option>
              ))}
            </select>
            <Input
              placeholder="Task title"
              value={task.title}
              onChange={(event) => change(index, 'title', event.target.value)}
            />
            <Input
              placeholder="Owner user ID"
              value={task.owner_id}
              onChange={(event) => change(index, 'owner_id', event.target.value)}
            />
            <Input
              type="date"
              value={task.due_date}
              onChange={(event) => change(index, 'due_date', event.target.value)}
            />
          </CardContent>
        </Card>
      ))}
      <div className="flex gap-2">
        <Button
          variant="outline"
          onClick={() =>
            setTasks((current) => [...current, { category: 'hr', title: '', owner_id: '', due_date: '' }])
          }
        >
          Add task
        </Button>
        <Button isLoading={mutation.isPending} onClick={() => mutation.mutate({ tasks })}>
          Start onboarding
        </Button>
      </div>
      {mutation.data ? (
        <Button asChild variant="outline">
          <Link href={`/onboarding/tasks/${mutation.data.id}`}>Open checklist</Link>
        </Button>
      ) : null}
    </div>
  );
}
export function TaskManagement({ caseId }: { caseId: string }) {
  const query = useOnboardingCase(caseId);
  if (query.isPending) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} />;
  return (
    <div className="space-y-6">
      <PageHeader title="Onboarding Tasks" description={`${String(query.data.progress_percent)}% complete`} />
      <TaskChecklist tasks={query.data.tasks} />
    </div>
  );
}
export function WelcomeCard({ data }: { data: WelcomeData }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Welcome to JSAN People360, {data.name}!</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-2 md:grid-cols-2">
        <p>Employee ID: {data.employee_code}</p>
        <p>Joining date: {data.joining_date}</p>
        <p>Manager: {data.reporting_manager ?? 'To be assigned'}</p>
        <p>Team: {data.team ?? 'To be assigned'}</p>
        <p>Team: {data.team ?? 'To be assigned'}</p>
        <p>Location: {data.office_location ?? 'To be assigned'}</p>
      </CardContent>
    </Card>
  );
}
export function WelcomeScreen({ caseId }: { caseId: string }) {
  const query = useWelcome(caseId);
  if (query.isPending) return <LoadingState />;
  if (query.error) return <ErrorState error={query.error} />;
  return (
    <div className="space-y-6">
      <PageHeader title="Employee Welcome" description="Everything needed for a confident first day." />
      <WelcomeCard data={query.data} />
      <TaskChecklist tasks={query.data.tasks} />
    </div>
  );
}
function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="space-y-1">
      <Label>{label}</Label>
      {children}
    </div>
  );
}
function SelectField({
  label,
  values,
  register,
}: {
  label: string;
  values: string[];
  register: React.SelectHTMLAttributes<HTMLSelectElement>;
}) {
  return (
    <Field label={label}>
      <select className="bg-background h-10 w-full rounded-md border px-3" {...register}>
        {values.map((x) => (
          <option key={x} value={x}>
            {human(x)}
          </option>
        ))}
      </select>
    </Field>
  );
}
const addressPath = (index: number, name: string) =>
  `addresses.${String(index)}.${name}` as FieldPath<ProfileFormValues>;
