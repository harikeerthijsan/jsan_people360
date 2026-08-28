'use client';
import { zodResolver } from '@hookform/resolvers/zod';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import * as React from 'react';
import { useFieldArray, useForm, type FieldPath } from 'react-hook-form';
import type { z } from 'zod';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { LoadingState } from '@/components/common/loading-state';
import { ErrorState } from '@/components/common/error-state';
import { Timeline } from '@/components/common/timeline';
import { RichTextEditor } from '@/components/common/rich-text-editor';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Textarea } from '@/components/ui/textarea';
import { apiClient } from '@/lib/api/client';
import { offersApi } from './api';
import { useOffer, useOfferDashboard, useOfferMutation, useOffers, useTemplates } from './hooks';
import { offerSchema } from './schema';
import type { Offer } from './types';
export function OfferDashboard() {
  const q = useOfferDashboard();
  if (q.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} />;
  const d = q.data;
  return (
    <div className="space-y-6">
      <PageHeader
        title="Offer Dashboard"
        description="Offer pipeline, candidate responses and joining readiness."
      />
      <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-5">
        {Object.entries(d).map(([k, v]) => (
          <StatCard key={k} label={label(k)} value={typeof v === 'number' ? v : String(v)} />
        ))}
      </div>
    </div>
  );
}
export function OfferList() {
  const [status, setStatus] = React.useState('');
  const q = useOffers({ page: 1, page_size: 100, status: status || undefined });
  return (
    <div className="space-y-6">
      <PageHeader
        title="Offers"
        description="Compensation offers and approval progress."
        actions={
          <Button asChild>
            <Link href="/offers/new">Create offer</Link>
          </Button>
        }
      />
      <select
        className="bg-background h-10 rounded-md border px-3"
        value={status}
        onChange={(e) => setStatus(e.target.value)}
      >
        <option value="">All statuses</option>
        {[
          'draft',
          'pending_approval',
          'approved',
          'released',
          'accepted',
          'declined',
          'expired',
          'withdrawn',
        ].map((x) => (
          <option key={x} value={x}>
            {label(x)}
          </option>
        ))}
      </select>
      {q.isPending ? (
        <LoadingState />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : (
        <div className="grid gap-3">
          {q.data.items.map((x) => (
            <OfferCard key={x.id} offer={x} />
          ))}
        </div>
      )}
    </div>
  );
}
export function OfferCard({ offer: x }: { offer: Offer }) {
  return (
    <Link href={`/offers/${x.id}`}>
      <Card>
        <CardContent className="flex items-center gap-3 p-4">
          <div className="flex-1">
            <b>{x.offer_code}</b>
            <p className="text-muted-foreground text-xs">
              Candidate {x.candidate_id} · CTC {Number(x.ctc).toLocaleString()}
            </p>
          </div>
          <Badge>{label(x.status)}</Badge>
        </CardContent>
      </Card>
    </Link>
  );
}
type FormValues = z.infer<typeof offerSchema>;
export function OfferForm() {
  const router = useRouter();
  const create = useOfferMutation((d: unknown) => offersApi.create(d));
  const form = useForm<FormValues>({
    resolver: zodResolver(offerSchema),
    defaultValues: {
      candidate_id: '',
      template_id: null,
      ctc: 0,
      joining_date: '',
      probation_months: 6,
      notice_period_days: 30,
      reporting_manager_id: null,
      work_mode: 'hybrid',
      shift: null,
      benefits: 'Standard company benefits',
      leave_policy_summary: 'As per company policy',
      working_hours: 'As per company policy',
      confidentiality: 'Standard confidentiality terms apply',
      nda_required: false,
      additional_conditions: null,
      expiry_date: '',
      hr_executive_id: '',
      hr_manager_id: '',
      business_unit_head_id: '',
      salary_components: [
        { name: 'Basic Salary', component_type: 'fixed', annual_amount: 0, is_employer_contribution: false },
        { name: 'HRA', component_type: 'fixed', annual_amount: 0, is_employer_contribution: false },
        {
          name: 'Special Allowance',
          component_type: 'fixed',
          annual_amount: 0,
          is_employer_contribution: false,
        },
      ],
    },
  });
  const fields = useFieldArray({ control: form.control, name: 'salary_components' });
  const submit = form.handleSubmit((v: FormValues) =>
    create.mutate(v, { onSuccess: (x) => router.push(`/offers/${x.id}`) }),
  );
  return (
    <form className="space-y-6" onSubmit={submit}>
      <PageHeader
        title="Create Offer"
        description="Only candidates in the Selected ATS stage are eligible."
      />
      <Card>
        <CardContent className="grid gap-4 p-6 md:grid-cols-2">
          {(
            [
              'candidate_id',
              'ctc',
              'joining_date',
              'expiry_date',
              'probation_months',
              'notice_period_days',
              'reporting_manager_id',
              'hr_executive_id',
              'hr_manager_id',
              'business_unit_head_id',
            ] as FieldPath<FormValues>[]
          ).map((k) => (
            <div key={k}>
              <Label>{label(k)}</Label>
              <Input
                type={
                  k.includes('date')
                    ? 'date'
                    : k.includes('months') || k.includes('days') || k === 'ctc'
                      ? 'number'
                      : 'text'
                }
                {...form.register(k, {
                  setValueAs: (v: unknown) =>
                    ['ctc', 'probation_months', 'notice_period_days'].includes(k)
                      ? Number(v)
                      : typeof v === 'string' && v
                        ? v
                        : null,
                })}
              />
            </div>
          ))}
          <div>
            <Label>Work mode</Label>
            <select
              className="bg-background h-10 w-full rounded-md border px-3"
              {...form.register('work_mode')}
            >
              <option value="office">Office</option>
              <option value="hybrid">Hybrid</option>
              <option value="remote">Remote</option>
            </select>
          </div>
          {(
            [
              'benefits',
              'leave_policy_summary',
              'working_hours',
              'confidentiality',
              'additional_conditions',
            ] as FieldPath<FormValues>[]
          ).map((k) => (
            <div key={k} className="md:col-span-2">
              <Label>{label(k)}</Label>
              <RichTextEditor
                id={`offer-${k}`}
                value={String(form.watch(k as keyof FormValues) || '')}
                onChange={(v) => form.setValue(k as keyof FormValues, v)}
              />
            </div>
          ))}
          <div className="space-y-2 md:col-span-2">
            <div className="flex justify-between">
              <Label>Compensation components</Label>
              <Button
                type="button"
                variant="outline"
                onClick={() =>
                  fields.append({
                    name: '',
                    component_type: 'allowance',
                    annual_amount: 0,
                    is_employer_contribution: false,
                  })
                }
              >
                Add component
              </Button>
            </div>
            {fields.fields.map((f, i) => (
              <div key={f.id} className="grid gap-2 md:grid-cols-[1fr_1fr_1fr_auto]">
                <Input placeholder="Component" {...form.register(fieldPath(i, 'name'))} />
                <Input placeholder="Type" {...form.register(fieldPath(i, 'component_type'))} />
                <Input
                  type="number"
                  placeholder="Annual amount"
                  {...form.register(fieldPath(i, 'annual_amount'), { valueAsNumber: true })}
                />
                <Button type="button" variant="destructive" onClick={() => fields.remove(i)}>
                  Remove
                </Button>
              </div>
            ))}
          </div>
          {Object.keys(form.formState.errors).length ? (
            <p className="text-destructive md:col-span-2">
              Please correct the offer values and ensure components equal CTC.
            </p>
          ) : null}
          {create.error ? <p className="text-destructive md:col-span-2">{create.error.message}</p> : null}
          <Button className="md:col-span-2" type="submit" isLoading={create.isPending}>
            Create offer
          </Button>
        </CardContent>
      </Card>
    </form>
  );
}
export function OfferDetail({ id }: { id: string }) {
  const q = useOffer(id);
  const mutate = useOfferMutation(({ action, comments }: { action: string; comments?: string | null }) =>
    action === 'submit'
      ? offersApi.submit(id)
      : action === 'release'
        ? offersApi.release(id)
        : action === 'accept'
          ? offersApi.action(id, 'accept')
          : action === 'decline' || action === 'clarification'
            ? offersApi.action(id, action, comments ?? undefined)
            : offersApi.approval(id, action, comments ?? null),
  );
  const decideApproval = (action: string) => {
    // Escape means "never mind", not "decide without comments".
    const comments = window.prompt('Comments');
    if (comments === null) return;
    mutate.mutate({ action, comments: comments.trim() || null });
  };
  const respond = (action: 'decline' | 'clarification', question: string) => {
    // A candidate response needs a real message; Escape or an empty answer aborts.
    const comments = window.prompt(question)?.trim();
    if (comments) mutate.mutate({ action, comments });
  };
  if (q.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} />;
  const x = q.data;
  return (
    <div className="space-y-6">
      <PageHeader
        title={x.offer_code}
        description={label(x.status)}
        actions={
          <div className="flex gap-2">
            {x.status === 'draft' ? (
              <Button onClick={() => mutate.mutate({ action: 'submit' })}>Submit</Button>
            ) : null}
            {x.status === 'pending_approval'
              ? ['approve', 'reject', 'send_back'].map((a) => (
                  <Button key={a} variant="outline" onClick={() => decideApproval(a)}>
                    {label(a)}
                  </Button>
                ))
              : null}
            {x.status === 'approved' ? (
              <Button onClick={() => mutate.mutate({ action: 'release' })}>Release</Button>
            ) : null}
            <Button variant="outline" onClick={() => void downloadPdf(id)}>
              Download PDF
            </Button>
          </div>
        }
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <SalaryBreakdown offer={x} />
        <Card>
          <CardHeader>
            <CardTitle>Employment details</CardTitle>
          </CardHeader>
          <CardContent>
            <p>Joining: {x.joining_date}</p>
            <p>Work mode: {label(x.work_mode)}</p>
            <p>Probation: {x.probation_months} months</p>
            <p>Expiry: {x.expiry_date}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Approval timeline</CardTitle>
          </CardHeader>
          <CardContent>
            {x.approvals.map((a) => (
              <div key={a.id} className="flex justify-between border-b py-2">
                <span>
                  {a.sequence}. {a.role_name}
                </span>
                <Badge>{label(a.status)}</Badge>
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Offer timeline</CardTitle>
          </CardHeader>
          <CardContent>
            <Timeline
              items={x.history.map((h) => ({
                id: h.id,
                title: label(h.action),
                timestamp: h.created_at,
                description: h.comments,
              }))}
            />
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Candidate offer view</CardTitle>
          </CardHeader>
          <CardContent className="flex gap-2">
            {x.status === 'released' ? (
              <>
                <Button onClick={() => mutate.mutate({ action: 'accept' })}>Accept Offer</Button>
                <Button variant="destructive" onClick={() => respond('decline', 'Reason')}>
                  Decline
                </Button>
                <Button variant="outline" onClick={() => respond('clarification', 'Question')}>
                  Request clarification
                </Button>
              </>
            ) : null}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
function SalaryBreakdown({ offer: x }: { offer: Offer }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Compensation</CardTitle>
      </CardHeader>
      <CardContent>
        {x.salary_components.map((c) => (
          <div key={c.id} className="flex justify-between border-b py-2">
            <span>{c.name}</span>
            <span>{Number(c.annual_amount).toLocaleString()}</span>
          </div>
        ))}
        <div className="flex justify-between pt-3 font-bold">
          <span>Annual CTC</span>
          <span>{Number(x.ctc).toLocaleString()}</span>
        </div>
        <p className="text-muted-foreground text-sm">Monthly: {(Number(x.ctc) / 12).toLocaleString()}</p>
      </CardContent>
    </Card>
  );
}
export function TemplateManagement() {
  const q = useTemplates();
  const create = useOfferMutation((d: { name: string; body: string }) => offersApi.createTemplate(d));
  const [name, setName] = React.useState('');
  const [body, setBody] = React.useState(
    'Dear {{candidate_name}}, we offer you {{designation}} with salary {{salary}}.',
  );
  return (
    <div className="space-y-6">
      <PageHeader
        title="Offer Templates"
        description="Use candidate, designation, salary, joining date, company, team and manager placeholders."
      />
      <Card>
        <CardContent className="space-y-3 p-6">
          <Input placeholder="Template name" value={name} onChange={(e) => setName(e.target.value)} />
          <Textarea value={body} onChange={(e) => setBody(e.target.value)} />
          <Button onClick={() => create.mutate({ name, body })}>Create template</Button>
        </CardContent>
      </Card>
      {q.data?.map((t) => (
        <Card key={t.id}>
          <CardContent className="p-4">
            <b>{t.name}</b>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
async function downloadPdf(id: string) {
  const r = await apiClient.post(`/offers/${id}/pdf`, undefined, { responseType: 'blob' });
  const u = URL.createObjectURL(r.data as Blob);
  const a = document.createElement('a');
  a.href = u;
  a.download = 'offer.pdf';
  a.click();
  URL.revokeObjectURL(u);
}
const fieldPath = (index: number, name: string) =>
  `salary_components.${String(index)}.${name}` as FieldPath<FormValues>;
const label = (s: string) => s.replaceAll('_', ' ').replace(/^./, (x) => x.toUpperCase());
