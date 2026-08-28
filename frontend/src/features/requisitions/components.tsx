'use client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import * as React from 'react';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { LoadingState } from '@/components/common/loading-state';
import { ErrorState } from '@/components/common/error-state';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { Badge } from '@/components/ui/badge';
import { Timeline } from '@/components/common/timeline';
import { toast } from '@/components/ui/sonner';
import { formatDateTime } from '@/lib/utils';
import { requisitionsApi } from './api';
import { useRequisition, useRequisitionDashboard, useRequisitionMutation, useRequisitions } from './hooks';
import type { Requisition } from './types';
import { requisitionSchema } from './schema';
import { RichTextEditor } from '@/components/common/rich-text-editor';

export function WorkforceDashboard(): React.JSX.Element {
  const q = useRequisitionDashboard();
  if (q.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} />;
  const d = q.data;
  return (
    <div className="space-y-6">
      <PageHeader
        title="Workforce Planning"
        description="Manpower demand, approvals and upcoming hiring targets."
      />
      <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Open" value={d.total_open} />
        <StatCard label="Pending" value={d.pending_approvals} />
        <StatCard label="Approved" value={d.approved} />
        <StatCard label="Closed" value={d.closed} />
        <StatCard label="Expired" value={d.expired} />
        <StatCard label="Upcoming" value={d.upcoming_targets} />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Breakdown title="Hiring by business unit" items={d.by_business_unit} />
      </div>
    </div>
  );
}
function Breakdown({
  title,
  items,
}: {
  title: string;
  items: { label: string; count: number }[];
}): React.JSX.Element {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {items.map((x) => (
          <div key={x.label} className="flex justify-between border-b py-2">
            <span className="font-mono text-xs">{x.label}</span>
            <b>{x.count}</b>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
export function RequisitionList(): React.JSX.Element {
  const [search, setSearch] = React.useState('');
  const [status, setStatus] = React.useState('');
  const [priority, setPriority] = React.useState('');
  const [exporting, setExporting] = React.useState(false);
  const download = async (): Promise<void> => {
    setExporting(true);
    try {
      await requisitionsApi.exportExcel();
    } catch {
      toast.error('The export could not be prepared.');
    } finally {
      setExporting(false);
    }
  };
  const q = useRequisitions({
    page: 1,
    page_size: 100,
    search: search || undefined,
    status: status || undefined,
    priority: priority || undefined,
    sort_by: 'created_at',
    sort_order: 'desc',
  });
  return (
    <div className="space-y-6">
      <PageHeader
        title="Job Requisitions"
        description="Workforce requests and approval progress."
        actions={
          <div className="flex gap-2">
            <Button variant="outline" isLoading={exporting} onClick={() => void download()}>
              Export Excel
            </Button>
            <Button asChild>
              <Link href="/requisitions/new">New requisition</Link>
            </Button>
          </div>
        }
      />
      <div className="grid gap-3 md:grid-cols-3">
        <Input
          aria-label="Search requisitions"
          placeholder="Search ID or job title"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select
          aria-label="Status filter"
          className="bg-background h-10 rounded-md border px-3"
          value={status}
          onChange={(e) => setStatus(e.target.value)}
        >
          <option value="">All statuses</option>
          {[
            'draft',
            'pending_approval',
            'approved',
            'rejected',
            'open',
            'on_hold',
            'closed',
            'cancelled',
          ].map((x) => (
            <option key={x} value={x}>
              {label(x)}
            </option>
          ))}
        </select>
        <select
          aria-label="Priority filter"
          className="bg-background h-10 rounded-md border px-3"
          value={priority}
          onChange={(e) => setPriority(e.target.value)}
        >
          <option value="">All priorities</option>
          {['low', 'medium', 'high', 'critical'].map((x) => (
            <option key={x} value={x}>
              {label(x)}
            </option>
          ))}
        </select>
      </div>
      {q.isPending ? (
        <LoadingState />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : (
        <div className="grid gap-3">
          {q.data.items.map((r) => (
            <Link key={r.id} href={`/requisitions/${r.id}`}>
              <Card>
                <CardContent className="flex items-center gap-4 p-4">
                  <div className="flex-1">
                    <p className="font-medium">{r.job_title}</p>
                    <p className="text-muted-foreground font-mono text-xs">
                      {r.requisition_code} · {r.openings} openings
                    </p>
                  </div>
                  <Badge>{r.priority}</Badge>
                  <Badge variant="outline">{r.status.replaceAll('_', ' ')}</Badge>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}

const textFields = [
  'job_title',
  'education',
  'salary_from',
  'salary_to',
  'hiring_manager_id',
  'second_approver_id',
  'hr_approver_id',
  'recruiter_id',
  'business_unit_id',
  'team_id',
  'location_id',
  'designation_id',
  'grade_id',
  'employment_type_id',
  'target_joining_date',
] as const;
export function RequisitionForm({ record }: { record?: Requisition }): React.JSX.Element {
  const router = useRouter();
  const mutation = useRequisitionMutation<unknown>((data) =>
    record ? requisitionsApi.update(record.id, data) : requisitionsApi.create(data),
  );
  const [values, setValues] = React.useState<Record<string, unknown>>(
    record
      ? { ...record, skills: record.skills.join(', '), certifications: record.certifications.join(', ') }
      : {
          hiring_type: 'new_position',
          request_type: 'new_position',
          priority: 'medium',
          working_model: 'office',
          openings: 1,
          experience_min: 0,
          budget_approved: false,
        },
  );
  const [validationError, setValidationError] = React.useState<string | null>(null);
  const set = (k: string, v: unknown) => setValues((x) => ({ ...x, [k]: v }));
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const optionalString = (key: string): string | null => {
      const value = values[key];
      return typeof value === 'string' && value.length > 0 ? value : null;
    };
    const data = {
      ...values,
      openings: Number(values.openings),
      experience_min: Number(values.experience_min),
      experience_max: values.experience_max ? Number(values.experience_max) : null,
      salary_from: optionalString('salary_from'),
      salary_to: optionalString('salary_to'),
      team_id: optionalString('team_id'),
      grade_id: optionalString('grade_id'),
      recruiter_id: optionalString('recruiter_id'),
      skills: String(values.skills || '')
        .split(',')
        .map((x) => x.trim())
        .filter(Boolean),
      certifications: String(values.certifications || '')
        .split(',')
        .map((x) => x.trim())
        .filter(Boolean),
    };
    const parsed = requisitionSchema.safeParse(data);
    if (!parsed.success) {
      setValidationError(parsed.error.issues[0]?.message ?? 'Check the form fields.');
      return;
    }
    setValidationError(null);
    mutation.mutate(parsed.data, { onSuccess: (r) => router.push(`/requisitions/${r.id}`) });
  };
  return (
    <form className="space-y-6" onSubmit={submit}>
      <PageHeader
        title={record ? 'Edit requisition' : 'New requisition'}
        description="Fields ending in ID accept the UUID selected from the corresponding master or user directory."
      />
      <Card>
        <CardContent className="grid gap-4 p-6 md:grid-cols-2">
          {textFields.map((k) => (
            <Field
              key={k}
              name={k}
              value={String(values[k] ?? '')}
              type={k === 'target_joining_date' ? 'date' : 'text'}
              onChange={(v) => set(k, v)}
            />
          ))}
          <Field
            name="openings"
            value={String(values.openings ?? 1)}
            type="number"
            onChange={(v) => set('openings', v)}
          />
          <Field
            name="experience_min"
            value={String(values.experience_min ?? 0)}
            type="number"
            onChange={(v) => set('experience_min', v)}
          />
          <Field
            name="experience_max"
            value={String(values.experience_max ?? '')}
            type="number"
            onChange={(v) => set('experience_max', v)}
          />
          {['hiring_type', 'request_type', 'priority', 'working_model'].map((k) => (
            <Field key={k} name={k} value={String(values[k] ?? '')} onChange={(v) => set(k, v)} />
          ))}
          {['skills', 'certifications', 'business_justification'].map((k) => (
            <div key={k} className="space-y-1.5 md:col-span-2">
              <Label htmlFor={k}>{label(k)}</Label>
              <Textarea
                id={k}
                required={['responsibilities', 'requirements', 'business_justification'].includes(k)}
                value={String(values[k] ?? '')}
                onChange={(e) => set(k, e.target.value)}
              />
            </div>
          ))}
          {['responsibilities', 'requirements', 'benefits'].map((k) => (
            <div key={k} className="space-y-1.5 md:col-span-2">
              <Label htmlFor={k}>{label(k)}</Label>
              <RichTextEditor id={k} value={String(values[k] ?? '')} onChange={(value) => set(k, value)} />
            </div>
          ))}
          <label className="flex items-center gap-2">
            <input
              type="checkbox"
              checked={Boolean(values.budget_approved)}
              onChange={(e) => set('budget_approved', e.target.checked)}
            />{' '}
            Budget approved
          </label>
          {validationError ? (
            <p role="alert" className="text-destructive md:col-span-2">
              {validationError}
            </p>
          ) : null}
          {mutation.error ? (
            <p role="alert" className="text-destructive md:col-span-2">
              {mutation.error.message}
            </p>
          ) : null}
          <Button className="md:col-span-2" type="submit" isLoading={mutation.isPending}>
            Save requisition
          </Button>
        </CardContent>
      </Card>
    </form>
  );
}
function Field({
  name,
  value,
  onChange,
  type = 'text',
}: {
  name: string;
  value: string;
  onChange: (v: string) => void;
  type?: string;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={name}>{label(name)}</Label>
      <Input
        id={name}
        required={
          ![
            'education',
            'salary_from',
            'salary_to',
            'recruiter_id',
            'team_id',
            'grade_id',
            'experience_max',
          ].includes(name)
        }
        type={type}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
    </div>
  );
}
const label = (s: string) => s.replaceAll('_', ' ').replace(/^./, (x) => x.toUpperCase());

export function RequisitionDetail({ id }: { id: string }): React.JSX.Element {
  const q = useRequisition(id);
  const submit = useRequisitionMutation(() => requisitionsApi.submit(id));
  const action = useRequisitionMutation(({ name, comments }: { name: string; comments: string | null }) =>
    requisitionsApi.act(id, name, comments),
  );
  const [documentId, setDocumentId] = React.useState('');
  const [attachmentType, setAttachmentType] = React.useState('supporting_document');
  if (q.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} />;
  const r = q.data;
  const doAction = (name: string) => {
    // Escape means "never mind", not "proceed without comments".
    const comments = window.prompt('Comments');
    if (comments === null) return;
    action.mutate({ name, comments: comments.trim() || null });
  };
  return (
    <div className="space-y-6">
      <PageHeader
        title={r.job_title}
        description={`${r.requisition_code} · ${r.status.replaceAll('_', ' ')}`}
        actions={
          <div className="flex flex-wrap gap-2">
            {r.status === 'draft' ? (
              <>
                <Button asChild variant="outline">
                  <Link href={`/requisitions/${r.id}/edit`}>Edit</Link>
                </Button>
                <Button onClick={() => submit.mutate(undefined)}>Submit</Button>
              </>
            ) : null}
            {r.status === 'pending_approval' ? (
              <>
                {['approve', 'reject', 'send_back'].map((x) => (
                  <Button
                    key={x}
                    variant={x === 'reject' ? 'destructive' : 'outline'}
                    onClick={() => doAction(x)}
                  >
                    {label(x)}
                  </Button>
                ))}
              </>
            ) : null}
            {r.status === 'approved' ? <Button onClick={() => doAction('open')}>Open hiring</Button> : null}
            {r.status === 'open' ? (
              <Button variant="outline" onClick={() => doAction('hold')}>
                Put on hold
              </Button>
            ) : null}
            {r.status === 'on_hold' ? <Button onClick={() => doAction('resume')}>Resume</Button> : null}
            {['approved', 'open', 'on_hold'].includes(r.status) ? (
              <Button variant="outline" onClick={() => doAction('close')}>
                Close
              </Button>
            ) : null}
            {!['closed', 'cancelled'].includes(r.status) ? (
              <Button variant="destructive" onClick={() => doAction('cancel')}>
                Cancel
              </Button>
            ) : null}
          </div>
        }
      />
      <div className="grid gap-6 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Overview</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <p>Openings: {r.openings}</p>
            <p>Priority: {r.priority}</p>
            <p>Target: {r.target_joining_date}</p>
            <p>
              Experience: {r.experience_min}–{r.experience_max ?? 'Any'} years
            </p>
            <p>Working model: {r.working_model}</p>
            <p>Justification: {r.business_justification}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Approval history</CardTitle>
          </CardHeader>
          <CardContent>
            <Timeline
              items={r.approvals.map((a) => ({
                id: a.id,
                title: `${String(a.sequence)}. ${a.role_name} — ${a.status}`,
                timestamp: a.acted_at ? formatDateTime(a.acted_at) : 'Waiting',
                description: a.comments,
              }))}
            />
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Activity timeline</CardTitle>
          </CardHeader>
          <CardContent>
            <Timeline
              items={r.history.map((h) => ({
                id: h.id,
                title: h.action,
                timestamp: formatDateTime(h.created_at),
                description: h.comments ?? `${h.from_status ?? 'new'} → ${h.to_status}`,
              }))}
            />
          </CardContent>
        </Card>
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Attachments</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="grid gap-2 md:grid-cols-[1fr_220px_auto]">
              <Input
                aria-label="Document ID"
                placeholder="Document Vault UUID"
                value={documentId}
                onChange={(event) => setDocumentId(event.target.value)}
              />
              <select
                aria-label="Attachment type"
                className="rounded-md border px-3"
                value={attachmentType}
                onChange={(event) => setAttachmentType(event.target.value)}
              >
                <option value="job_description">Job description</option>
                <option value="budget_approval">Budget approval</option>
                <option value="supporting_document">Supporting document</option>
              </select>
              <Button
                onClick={() => {
                  void requisitionsApi.attach(id, documentId, attachmentType).then(() => {
                    setDocumentId('');
                    void q.refetch();
                  });
                }}
              >
                Attach
              </Button>
            </div>
            {r.attachments.map((attachment) => (
              <Link
                className="block rounded border p-3 font-mono text-xs"
                key={attachment.id}
                href={`/documents/${attachment.document_id}`}
              >
                {attachment.attachment_type} · {attachment.document_id}
              </Link>
            ))}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
