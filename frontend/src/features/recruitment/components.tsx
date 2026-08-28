'use client';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import * as React from 'react';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { LoadingState } from '@/components/common/loading-state';
import { ErrorState } from '@/components/common/error-state';
import { Timeline } from '@/components/common/timeline';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { candidateSchema } from './schema';
import { recruitmentApi } from './api';
import {
  useCandidate,
  useCandidates,
  useDashboard,
  useOpenings,
  usePools,
  useRecruitmentMutation,
  useReferences,
} from './hooks';
import type { Candidate } from './types';

export function RecruitmentDashboard() {
  const q = useDashboard();
  if (q.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} />;
  const d = q.data;
  return (
    <div className="space-y-6">
      <PageHeader
        title="Recruitment Dashboard"
        description="Applicant pipeline, recruiter capacity and hiring outcomes."
      />
      <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
        <StatCard label="Open jobs" value={d.open_jobs} />
        <StatCard label="Applicants" value={d.total_applicants} />
        <StatCard label="Offers released" value={d.offers_released} />
        <StatCard label="Offers accepted" value={d.offers_accepted} />
        <StatCard label="Joining pending" value={d.joining_pending} />
        <StatCard label="Time to hire" value={`${String(d.average_time_to_hire_days)}d`} />
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Metric title="Candidates by stage" rows={d.by_stage} />
        <Metric title="Recruiter workload" rows={d.recruiter_workload} />
      </div>
    </div>
  );
}
function Metric({ title, rows }: { title: string; rows: { label: string; count: number }[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        {rows.map((x) => (
          <div key={x.label} className="flex justify-between border-b py-2">
            <span>{x.label}</span>
            <b>{x.count}</b>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function OpeningsPage() {
  const q = useOpenings();
  const create = useRecruitmentMutation(
    (x: { requisition_id: string; recruiter_id: null; closing_date: null }) =>
      recruitmentApi.createOpening(x),
  );
  const action = useRecruitmentMutation(({ id, name }: { id: string; name: string }) =>
    recruitmentApi.openingAction(id, name),
  );
  const [req, setReq] = React.useState('');
  return (
    <div className="space-y-6">
      <PageHeader
        title="Job Openings"
        description="Only approved requisitions can be converted into openings."
      />
      <Card>
        <CardContent className="flex gap-2 p-4">
          <Input
            aria-label="Approved requisition UUID"
            placeholder="Approved requisition UUID"
            value={req}
            onChange={(e) => setReq(e.target.value)}
          />
          <Button
            onClick={() => create.mutate({ requisition_id: req, recruiter_id: null, closing_date: null })}
          >
            Create opening
          </Button>
        </CardContent>
      </Card>
      {q.isPending ? (
        <LoadingState />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : (
        <div className="grid gap-3">
          {q.data.map((x) => (
            <Card key={x.id}>
              <CardContent className="flex items-center gap-3 p-4">
                <div className="flex-1">
                  <b>{x.job_code}</b>
                  <p className="font-mono text-xs">{x.requisition_id}</p>
                </div>
                <Badge>{x.status}</Badge>
                {x.status === 'draft' ? (
                  <Button onClick={() => action.mutate({ id: x.id, name: 'publish' })}>Publish</Button>
                ) : null}
                {x.status === 'published' ? (
                  <Button variant="outline" onClick={() => action.mutate({ id: x.id, name: 'close' })}>
                    Close
                  </Button>
                ) : null}
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

export function CandidateList() {
  const [search, setSearch] = React.useState('');
  const [skill, setSkill] = React.useState('');
  const q = useCandidates({
    page: 1,
    page_size: 100,
    search: search || undefined,
    skill: skill || undefined,
  });
  return (
    <div className="space-y-6">
      <PageHeader
        title="Candidates"
        description="Search and manage applicant profiles."
        actions={
          <div className="flex gap-2">
            <Button asChild variant="outline">
              <Link href="/recruitment/pipeline">Pipeline</Link>
            </Button>
            <Button asChild>
              <Link href="/recruitment/candidates/new">Add candidate</Link>
            </Button>
          </div>
        }
      />
      <div className="grid gap-2 md:grid-cols-2">
        <Input
          aria-label="Candidate search"
          placeholder="Name, email or candidate ID"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <Input
          aria-label="Skill filter"
          placeholder="Filter by skill"
          value={skill}
          onChange={(e) => setSkill(e.target.value)}
        />
      </div>
      {q.isPending ? (
        <LoadingState />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : (
        <div className="grid gap-3">
          {q.data.items.map((c) => (
            <CandidateCard key={c.id} candidate={c} />
          ))}
        </div>
      )}
    </div>
  );
}
export function CandidateCard({ candidate: c }: { candidate: Candidate }) {
  return (
    <Link href={`/recruitment/candidates/${c.id}`}>
      <Card>
        <CardContent className="flex items-center gap-3 p-4">
          <div className="flex-1">
            <b>
              {c.first_name} {c.last_name}
            </b>
            <p className="text-muted-foreground text-xs">
              {c.candidate_code} · {c.email}
            </p>
            <div className="mt-2 flex gap-1">
              {c.skills.slice(0, 4).map((s) => (
                <Badge key={s.id} variant="outline">
                  {s.name}
                </Badge>
              ))}
            </div>
          </div>
          <Badge>{c.stage.name}</Badge>
        </CardContent>
      </Card>
    </Link>
  );
}

const fieldNames = [
  'job_opening_id',
  'source_id',
  'first_name',
  'last_name',
  'email',
  'mobile_number',
  'experience_years',
  'current_ctc',
  'expected_ctc',
  'notice_period_days',
  'current_company',
  'current_designation',
  'current_location',
  'preferred_location',
  'linkedin_url',
  'skills',
  'certifications',
  'tags',
  'resume_document_id',
] as const;
export function CandidateForm() {
  const router = useRouter();
  const refs = useReferences();
  const openings = useOpenings();
  const create = useRecruitmentMutation((x: unknown) => recruitmentApi.createCandidate(x));
  const [v, setV] = React.useState<Record<string, string>>({
    experience_years: '0',
    notice_period_days: '0',
  });
  const [error, setError] = React.useState('');
  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const nullable = (k: string) => v[k] || null;
    const data = {
      ...v,
      recruiter_id: null,
      linkedin_url: nullable('linkedin_url'),
      current_company: nullable('current_company'),
      current_designation: nullable('current_designation'),
      current_location: nullable('current_location'),
      preferred_location: nullable('preferred_location'),
      certifications: nullable('certifications'),
      tags: nullable('tags'),
      current_ctc: v.current_ctc ? Number(v.current_ctc) : null,
      expected_ctc: v.expected_ctc ? Number(v.expected_ctc) : null,
      skills: (v.skills || '')
        .split(',')
        .map((x) => x.trim())
        .filter(Boolean),
    };
    const parsed = candidateSchema.safeParse(data);
    if (!parsed.success) {
      setError(parsed.error.issues[0]?.message || 'Check fields');
      return;
    }
    create.mutate(parsed.data, { onSuccess: (x) => router.push(`/recruitment/candidates/${x.id}`) });
  };
  return (
    <form className="space-y-6" onSubmit={submit}>
      <PageHeader
        title="Add Candidate"
        description="A resume from Document Vault and a published opening are required."
      />
      <Card>
        <CardContent className="grid gap-4 p-6 md:grid-cols-2">
          {fieldNames.map((k) => (
            <div key={k}>
              <Label htmlFor={k}>{label(k)}</Label>
              {k === 'job_opening_id' ? (
                <select
                  id={k}
                  required
                  className="bg-background h-10 w-full rounded-md border px-3"
                  value={v[k] || ''}
                  onChange={(e) => setV((x) => ({ ...x, [k]: e.target.value }))}
                >
                  <option value="">Select published opening</option>
                  {openings.data
                    ?.filter((x) => x.status === 'published')
                    .map((x) => (
                      <option key={x.id} value={x.id}>
                        {x.job_code}
                      </option>
                    ))}
                </select>
              ) : k === 'source_id' ? (
                <select
                  id={k}
                  required
                  className="bg-background h-10 w-full rounded-md border px-3"
                  value={v[k] || ''}
                  onChange={(e) => setV((x) => ({ ...x, [k]: e.target.value }))}
                >
                  <option value="">Select source</option>
                  {refs.data?.sources.map((x) => (
                    <option key={x.id} value={x.id}>
                      {x.name}
                    </option>
                  ))}
                </select>
              ) : (
                <Input
                  id={k}
                  required={[
                    'first_name',
                    'last_name',
                    'email',
                    'mobile_number',
                    'experience_years',
                    'notice_period_days',
                    'skills',
                    'resume_document_id',
                  ].includes(k)}
                  type={
                    ['experience_years', 'current_ctc', 'expected_ctc', 'notice_period_days'].includes(k)
                      ? 'number'
                      : 'text'
                  }
                  value={v[k] || ''}
                  onChange={(e) => setV((x) => ({ ...x, [k]: e.target.value }))}
                />
              )}
            </div>
          ))}
          {error ? (
            <p role="alert" className="text-destructive md:col-span-2">
              {error}
            </p>
          ) : null}
          {create.error ? <p className="text-destructive md:col-span-2">{create.error.message}</p> : null}
          <Button className="md:col-span-2" type="submit" isLoading={create.isPending}>
            Create candidate
          </Button>
        </CardContent>
      </Card>
    </form>
  );
}

export function Pipeline() {
  const refs = useReferences();
  const q = useCandidates({ page: 1, page_size: 100 });
  const move = useRecruitmentMutation(({ id, stage }: { id: string; stage: string }) =>
    recruitmentApi.move(id, stage),
  );
  if (q.isPending || refs.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} />;
  return (
    <div className="space-y-6">
      <PageHeader title="Recruitment Pipeline" description="Drag candidates between configured stages." />
      <div className="flex gap-4 overflow-x-auto pb-4">
        {refs.data?.stages.map((stage) => (
          <section
            key={stage.id}
            className="bg-muted min-w-72 rounded-lg p-3"
            onDragOver={(e) => e.preventDefault()}
            onDrop={(e) => move.mutate({ id: e.dataTransfer.getData('candidate'), stage: stage.id })}
          >
            <h2 className="mb-3 font-semibold">{stage.name}</h2>
            <div className="space-y-2">
              {q.data.items
                .filter((x) => x.stage_id === stage.id)
                .map((c) => (
                  <div key={c.id} draggable onDragStart={(e) => e.dataTransfer.setData('candidate', c.id)}>
                    <CandidateCard candidate={c} />
                  </div>
                ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}

export function CandidateProfile({ id }: { id: string }) {
  const q = useCandidate(id);
  const refs = useReferences();
  const move = useRecruitmentMutation((stage: string) => recruitmentApi.move(id, stage));
  const note = useRecruitmentMutation((body: string) =>
    recruitmentApi.note(id, { body, is_internal: true, mentions: null }),
  );
  const doc = useRecruitmentMutation((x: { document_id: string; document_kind: string }) =>
    recruitmentApi.document(id, x),
  );
  const [noteText, setNote] = React.useState('');
  const [documentId, setDocument] = React.useState('');
  if (q.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} />;
  const c = q.data;
  return (
    <div className="space-y-6">
      <PageHeader
        title={`${c.first_name} ${c.last_name}`}
        description={`${c.candidate_code} · ${c.stage.name}`}
        actions={
          <div className="flex gap-2">
            <Button asChild variant="outline">
              <Link href={`/recruitment/candidates/${c.id}/edit`}>Edit</Link>
            </Button>
            <select
              aria-label="Move stage"
              className="bg-background h-10 rounded-md border px-3"
              value={c.stage_id}
              onChange={(e) => move.mutate(e.target.value)}
            >
              {refs.data?.stages.map((x) => (
                <option key={x.id} value={x.id}>
                  {x.name}
                </option>
              ))}
            </select>
          </div>
        }
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Overview</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <p>{c.email}</p>
            <p>{c.mobile_number}</p>
            <p>{c.experience_years} years experience</p>
            <p>Notice: {c.notice_period_days} days</p>
            <p>Source: {c.source.name}</p>
            <div className="flex gap-1">
              {c.skills.map((x) => (
                <Badge key={x.id}>{x.name}</Badge>
              ))}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Internal recruiter notes</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <Textarea value={noteText} onChange={(e) => setNote(e.target.value)} />
            <Button
              onClick={() => {
                note.mutate(noteText);
                setNote('');
              }}
            >
              Add note
            </Button>
            {c.notes.map((x) => (
              <div key={x.id} className="border-t py-2 text-sm">
                {x.body}
              </div>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Documents & resume versions</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {c.documents.map((x) => (
              <Link className="block underline" key={x.id} href={`/documents/${x.document_id}`}>
                {label(x.document_kind)}
              </Link>
            ))}
            <div className="flex gap-2">
              <Input
                placeholder="Document Vault UUID"
                value={documentId}
                onChange={(e) => setDocument(e.target.value)}
              />
              <Button onClick={() => doc.mutate({ document_id: documentId, document_kind: 'portfolio' })}>
                Link
              </Button>
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Activity timeline</CardTitle>
          </CardHeader>
          <CardContent>
            <Timeline
              items={c.stage_history.map((x) => ({
                id: x.id,
                title: 'Stage changed',
                timestamp: x.created_at,
                description: x.comments,
              }))}
            />
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export function TalentPools() {
  const q = usePools();
  const create = useRecruitmentMutation((name: string) =>
    recruitmentApi.createPool({ name, description: null }),
  );
  const [name, setName] = React.useState('');
  return (
    <div className="space-y-6">
      <PageHeader title="Talent Pools" description="Reusable candidate communities for future roles." />
      <div className="flex gap-2">
        <Input placeholder="Talent pool name" value={name} onChange={(e) => setName(e.target.value)} />
        <Button onClick={() => create.mutate(name)}>Create</Button>
      </div>
      {q.isPending ? (
        <LoadingState />
      ) : (
        <div className="grid gap-3 md:grid-cols-3">
          {q.data?.map((x) => (
            <Card key={x.id}>
              <CardContent className="p-4">
                <b>{x.name}</b>
                <p className="text-muted-foreground text-sm">
                  {x.description || 'Reusable talent community'}
                </p>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

export function CandidateEdit({ id }: { id: string }) {
  const router = useRouter();
  const q = useCandidate(id);
  const update = useRecruitmentMutation((data: unknown) => recruitmentApi.updateCandidate(id, data));
  const [values, setValues] = React.useState<Record<string, string>>({});
  React.useEffect(() => {
    if (q.data)
      setValues({
        first_name: q.data.first_name,
        last_name: q.data.last_name,
        mobile_number: q.data.mobile_number,
        current_company: q.data.current_company || '',
        current_designation: q.data.current_designation || '',
        experience_years: q.data.experience_years,
        notice_period_days: String(q.data.notice_period_days),
        current_location: q.data.current_location || '',
        preferred_location: q.data.preferred_location || '',
      });
  }, [q.data]);
  if (q.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} />;
  const fields = [
    'first_name',
    'last_name',
    'mobile_number',
    'current_company',
    'current_designation',
    'experience_years',
    'notice_period_days',
    'current_location',
    'preferred_location',
  ];
  return (
    <form
      className="space-y-6"
      onSubmit={(e) => {
        e.preventDefault();
        update.mutate(
          {
            ...values,
            experience_years: Number(values.experience_years),
            notice_period_days: Number(values.notice_period_days),
          },
          { onSuccess: () => router.push(`/recruitment/candidates/${id}`) },
        );
      }}
    >
      <PageHeader title="Edit Candidate" description={q.data.candidate_code} />
      <Card>
        <CardContent className="grid gap-4 p-6 md:grid-cols-2">
          {fields.map((key) => (
            <div key={key}>
              <Label htmlFor={key}>{label(key)}</Label>
              <Input
                id={key}
                value={values[key] || ''}
                onChange={(e) => setValues((old) => ({ ...old, [key]: e.target.value }))}
              />
            </div>
          ))}
          <Button type="submit" className="md:col-span-2" isLoading={update.isPending}>
            Save changes
          </Button>
        </CardContent>
      </Card>
    </form>
  );
}
const label = (s: string) => s.replaceAll('_', ' ').replace(/^./, (x) => x.toUpperCase());
