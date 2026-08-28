'use client';
import { zodResolver } from '@hookform/resolvers/zod';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import * as React from 'react';
import { useFieldArray, useForm } from 'react-hook-form';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { EmployeePicker } from '@/features/workforce/components/employee-picker';
import { StatCard } from '@/components/common/stat-card';
import { Timeline } from '@/components/common/timeline';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from '@/components/ui/sonner';
import { Textarea } from '@/components/ui/textarea';
import { apiClient } from '@/lib/api/client';
import { interviewsApi } from './api';
import { useInterview, useInterviewDashboard, useInterviewMutation, useInterviews } from './hooks';
import { feedbackSchema, scheduleSchema, type ScheduleValues } from './schema';
import type { Interview } from './types';

export function InterviewDashboard() {
  const q = useInterviewDashboard();
  if (q.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} />;
  const d = q.data;
  return (
    <div className="space-y-6">
      <PageHeader
        title="Interview Dashboard"
        description="Schedules, pending feedback, panel workload and selection outcomes."
      />
      <div className="grid gap-4 md:grid-cols-3 xl:grid-cols-5">
        <StatCard label="Today" value={d.todays_interviews} />
        <StatCard label="Upcoming" value={d.upcoming_interviews} />
        <StatCard label="Completed" value={d.completed_interviews} />
        <StatCard label="Cancelled" value={d.cancelled_interviews} />
        <StatCard label="Pending feedback" value={d.pending_feedback} />
        <StatCard label="Average score" value={d.average_score} />
        <StatCard label="Selection ratio" value={`${String(d.selection_ratio)}%`} />
        <StatCard label="Completion" value={`${String(d.completion_rate)}%`} />
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Breakdown title="Candidate interview status" rows={d.candidate_status} />
        <Breakdown title="Interviewer workload" rows={d.interviewer_workload} />
      </div>
    </div>
  );
}
function Breakdown({ title, rows }: { title: string; rows: { label: string; count: number }[] }) {
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

export function InterviewCard({ item }: { item: Interview }) {
  return (
    <Link href={`/interviews/${item.id}`}>
      <Card>
        <CardContent className="flex items-center gap-3 p-4">
          <div className="flex-1">
            <b>{item.interview_round}</b>
            <p className="text-muted-foreground text-xs">
              {item.interview_code} · {new Date(item.starts_at).toLocaleString()}
            </p>
          </div>
          <Badge variant="outline">{label(item.mode)}</Badge>
          <Badge>{label(item.status)}</Badge>
        </CardContent>
      </Card>
    </Link>
  );
}
export function InterviewList() {
  const [search, setSearch] = React.useState('');
  const [status, setStatus] = React.useState('');
  const q = useInterviews({
    page: 1,
    page_size: 100,
    search: search || undefined,
    status: status || undefined,
  });
  return (
    <div className="space-y-6">
      <PageHeader
        title="Interviews"
        description="Interview schedule and feedback progress."
        actions={
          <div className="flex gap-2">
            <Button variant="outline" onClick={() => void downloadReport()}>
              Export Excel
            </Button>
            <Button asChild variant="outline">
              <Link href="/interviews/calendar">Calendar</Link>
            </Button>
            <Button asChild>
              <Link href="/interviews/new">Schedule interview</Link>
            </Button>
          </div>
        }
      />
      <div className="grid gap-2 md:grid-cols-2">
        <Input
          aria-label="Search interviews"
          placeholder="Interview ID or round"
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
          {['scheduled', 'rescheduled', 'feedback_completed', 'completed', 'cancelled'].map((x) => (
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
          {q.data.items.map((x) => (
            <InterviewCard key={x.id} item={x} />
          ))}
        </div>
      )}
    </div>
  );
}

export function ScheduleInterview() {
  const router = useRouter();
  const mutation = useInterviewMutation((data: unknown) => interviewsApi.schedule(data));
  const form = useForm<ScheduleValues>({
    resolver: zodResolver(scheduleSchema),
    defaultValues: {
      candidate_id: '',
      interview_type: 'technical',
      interview_round: 'Technical Round 1',
      starts_at: '',
      ends_at: '',
      time_zone: Intl.DateTimeFormat().resolvedOptions().timeZone,
      mode: 'online',
      meeting_link: null,
      location: null,
      recruiter_notes: null,
      panels: [{ employee_id: '', designation_id: null, panel_role: 'lead_interviewer' }],
    },
  });
  const panels = useFieldArray({ control: form.control, name: 'panels' });
  const submit = form.handleSubmit((values) =>
    mutation.mutate(
      {
        ...values,
        starts_at: new Date(values.starts_at).toISOString(),
        ends_at: new Date(values.ends_at).toISOString(),
      },
      { onSuccess: (x) => router.push(`/interviews/${x.id}`) },
    ),
  );
  return (
    <form className="space-y-6" onSubmit={submit}>
      <PageHeader
        title="Schedule Interview"
        description="Conflicts are checked for the candidate and every panel member."
      />
      <Card>
        <CardContent className="grid gap-4 p-6 md:grid-cols-2">
          <FormInput
            labelText="Candidate UUID"
            error={form.formState.errors.candidate_id?.message}
            {...form.register('candidate_id')}
          />
          <FormInput
            labelText="Interview round"
            error={form.formState.errors.interview_round?.message}
            {...form.register('interview_round')}
          />
          <SelectInput
            labelText="Interview type"
            {...form.register('interview_type')}
            options={['hr', 'technical', 'managerial', 'client', 'final_hr']}
          />
          <SelectInput
            labelText="Mode"
            {...form.register('mode')}
            options={['online', 'offline', 'hybrid']}
          />
          <FormInput
            labelText="Starts at"
            type="datetime-local"
            error={form.formState.errors.starts_at?.message}
            {...form.register('starts_at')}
          />
          <FormInput
            labelText="Ends at"
            type="datetime-local"
            error={form.formState.errors.ends_at?.message}
            {...form.register('ends_at')}
          />
          <FormInput labelText="Time zone" {...form.register('time_zone')} />
          <FormInput
            labelText="Meeting link"
            error={form.formState.errors.meeting_link?.message}
            {...form.register('meeting_link', {
              setValueAs: (v: unknown) => (typeof v === 'string' && v ? v : null),
            })}
          />
          <FormInput
            labelText="Location"
            {...form.register('location', {
              setValueAs: (v: unknown) => (typeof v === 'string' && v ? v : null),
            })}
          />
          <div className="md:col-span-2">
            <Label>Recruiter notes</Label>
            <Textarea
              {...form.register('recruiter_notes', {
                setValueAs: (v: unknown) => (typeof v === 'string' && v ? v : null),
              })}
            />
          </div>
          <div className="space-y-3 md:col-span-2">
            <div className="flex justify-between">
              <Label>Interview panel</Label>
              <Button
                type="button"
                variant="outline"
                onClick={() =>
                  panels.append({ employee_id: '', designation_id: null, panel_role: 'panel_member' })
                }
              >
                Add member
              </Button>
            </div>
            {panels.fields.map((field, index) => (
              <div key={field.id} className="grid gap-2 md:grid-cols-[1fr_1fr_auto]">
                <EmployeePicker
                  id={`panel-employee-${String(index)}`}
                  label={`Panel member ${String(index + 1)}`}
                  value={form.watch(`panels.${String(index)}.employee_id` as `panels.${number}.employee_id`)}
                  onChange={(employeeId) =>
                    form.setValue(
                      `panels.${String(index)}.employee_id` as `panels.${number}.employee_id`,
                      employeeId,
                      { shouldValidate: true },
                    )
                  }
                />
                <SelectInput
                  labelText="Panel role"
                  {...form.register(`panels.${String(index)}.panel_role` as `panels.${number}.panel_role`)}
                  options={['lead_interviewer', 'panel_member', 'observer']}
                />
                <Button type="button" variant="destructive" onClick={() => panels.remove(index)}>
                  Remove
                </Button>
              </div>
            ))}
            {form.formState.errors.panels?.message ? (
              <p className="text-destructive text-sm">{form.formState.errors.panels.message}</p>
            ) : null}
          </div>
          {mutation.error ? <p className="text-destructive md:col-span-2">{mutation.error.message}</p> : null}
          <Button type="submit" className="md:col-span-2" isLoading={mutation.isPending}>
            Schedule interview
          </Button>
        </CardContent>
      </Card>
    </form>
  );
}
const FormInput = React.forwardRef<
  HTMLInputElement,
  React.ComponentProps<'input'> & { labelText: string; error?: string }
>(({ labelText, error, ...props }, ref) => (
  <div>
    <Label>{labelText}</Label>
    <Input ref={ref} {...props} />
    {error ? <p className="text-destructive text-sm">{error}</p> : null}
  </div>
));
FormInput.displayName = 'FormInput';
const SelectInput = React.forwardRef<
  HTMLSelectElement,
  React.ComponentProps<'select'> & { labelText: string; options: string[] }
>(({ labelText, options, ...props }, ref) => (
  <div>
    <Label>{labelText}</Label>
    <select ref={ref} className="bg-background h-10 w-full rounded-md border px-3" {...props}>
      {options.map((x) => (
        <option key={x} value={x}>
          {label(x)}
        </option>
      ))}
    </select>
  </div>
));
SelectInput.displayName = 'SelectInput';

export function InterviewCalendar() {
  const [view, setView] = React.useState('week');
  const q = useInterviews({
    page: 1,
    page_size: 100,
    date_from: new Date(Date.now() - 86400000 * 31).toISOString(),
    date_to: new Date(Date.now() + 86400000 * 90).toISOString(),
  });
  const reschedule = useInterviewMutation(({ id, date }: { id: string; date: string }) => {
    const item = q.data?.items.find((x) => x.id === id);
    if (!item) throw new Error('Interview not found');
    const duration = new Date(item.ends_at).getTime() - new Date(item.starts_at).getTime();
    return interviewsApi.reschedule(id, {
      starts_at: new Date(date).toISOString(),
      ends_at: new Date(new Date(date).getTime() + duration).toISOString(),
      time_zone: item.time_zone,
      comments: 'Calendar drag-and-drop reschedule',
    });
  });
  return (
    <div className="space-y-6">
      <PageHeader
        title="Interview Calendar"
        description="Daily, weekly and monthly schedule views with drag-and-drop rescheduling."
        actions={
          <div className="flex gap-1">
            {['day', 'week', 'month'].map((x) => (
              <Button key={x} variant={view === x ? 'default' : 'outline'} onClick={() => setView(x)}>
                {label(x)}
              </Button>
            ))}
          </div>
        }
      />
      {q.isPending ? (
        <LoadingState />
      ) : (
        <div data-view={view} className="grid gap-3 md:grid-cols-3">
          {q.data?.items.map((item) => (
            <div
              key={item.id}
              draggable
              onDragStart={(e) => e.dataTransfer.setData('interview', item.id)}
              onDragOver={(e) => e.preventDefault()}
              onDrop={(e) => {
                const value = window.prompt('New start date and time (e.g. 2026-09-01T10:00)');
                if (value === null || !value.trim()) return;
                if (Number.isNaN(Date.parse(value))) {
                  toast.error('That is not a valid date and time. Use e.g. 2026-09-01T10:00.');
                  return;
                }
                reschedule.mutate({ id: e.dataTransfer.getData('interview'), date: value.trim() });
              }}
            >
              <InterviewCard item={item} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const categories = [
  'technical_skills',
  'communication',
  'problem_solving',
  'domain_knowledge',
  'attitude',
  'culture_fit',
];
export function InterviewDetail({ id }: { id: string }) {
  const q = useInterview(id);
  const cancel = useInterviewMutation((comments: string) => interviewsApi.cancel(id, comments));
  const decision = useInterviewMutation((name: string) =>
    interviewsApi.decision(id, {
      decision: name,
      target_stage_id: null,
      comments: 'Decision recorded from interview detail',
    }),
  );
  const feedback = useInterviewMutation((data: unknown) => interviewsApi.feedback(id, data));
  const [interviewer, setInterviewer] = React.useState('');
  const [comments, setComments] = React.useState('');
  const [recommendation, setRecommendation] = React.useState('hire');
  const [ratings, setRatings] = React.useState<Record<string, number>>(
    Object.fromEntries(categories.map((x) => [x, 5])),
  );
  const attachment = useInterviewMutation((document_id: string) =>
    interviewsApi.attachment(id, { document_id, attachment_kind: 'evaluation_sheet' }),
  );
  const [documentId, setDocumentId] = React.useState('');
  if (q.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} />;
  const item = q.data;
  const submitFeedback = () => {
    const data = {
      interviewer_id: interviewer,
      overall_comments: comments,
      recommendation,
      scores: categories.map((category) => ({ category, score: ratings[category], comments: null })),
    };
    const parsed = feedbackSchema.safeParse(data);
    if (parsed.success) feedback.mutate(parsed.data);
  };
  return (
    <div className="space-y-6">
      <PageHeader
        title={item.interview_round}
        description={`${item.interview_code} · ${label(item.status)}`}
        actions={
          <div className="flex gap-2">
            <Button asChild variant="outline">
              <Link href={`/interviews/${id}/edit`}>Edit</Link>
            </Button>
            {!['cancelled', 'completed'].includes(item.status) ? (
              <Button
                variant="destructive"
                onClick={() => {
                  // A cancellation needs a real reason; Escape or an empty answer aborts.
                  const reason = window.prompt('Cancellation reason')?.trim();
                  if (reason) cancel.mutate(reason);
                }}
              >
                Cancel
              </Button>
            ) : null}
          </div>
        }
      />
      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Interview details</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            <p>
              Candidate:{' '}
              <Link className="underline" href={`/recruitment/candidates/${item.candidate_id}`}>
                {item.candidate_id}
              </Link>
            </p>
            <p>
              {new Date(item.starts_at).toLocaleString()} – {new Date(item.ends_at).toLocaleTimeString()}
            </p>
            <p>
              {label(item.interview_type)} · {label(item.mode)}
            </p>
            <p>Time zone: {item.time_zone}</p>
            <p>Panel: {item.panels.length}</p>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Interview attachments</CardTitle>
          </CardHeader>
          <CardContent className="space-y-2">
            {item.attachments.map((x) => (
              <Link key={x.id} className="block underline" href={`/documents/${x.document_id}`}>
                {label(x.attachment_kind)}
              </Link>
            ))}
            <div className="flex gap-2">
              <Input
                placeholder="Document Vault UUID"
                value={documentId}
                onChange={(e) => setDocumentId(e.target.value)}
              />
              <Button onClick={() => attachment.mutate(documentId)}>Link</Button>
            </div>
          </CardContent>
        </Card>
        <Scorecard item={item} />
        <Card className="lg:col-span-2">
          <CardHeader>
            <CardTitle>Submit structured feedback</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <EmployeePicker
              id="feedback-interviewer"
              label="Interviewer"
              value={interviewer}
              onChange={setInterviewer}
            />
            <div className="grid gap-3 md:grid-cols-3">
              {categories.map((x) => (
                <div key={x}>
                  <Label>
                    {label(x)}: {ratings[x]}
                  </Label>
                  <input
                    className="w-full"
                    type="range"
                    min="1"
                    max="10"
                    value={ratings[x]}
                    onChange={(e) => setRatings((old) => ({ ...old, [x]: Number(e.target.value) }))}
                  />
                </div>
              ))}
            </div>
            <Textarea
              placeholder="Overall comments"
              value={comments}
              onChange={(e) => setComments(e.target.value)}
            />
            <select
              className="bg-background h-10 rounded-md border px-3"
              value={recommendation}
              onChange={(e) => setRecommendation(e.target.value)}
            >
              {['strong_hire', 'hire', 'hold', 'reject'].map((x) => (
                <option key={x} value={x}>
                  {label(x)}
                </option>
              ))}
            </select>
            <Button onClick={submitFeedback}>Submit feedback</Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Decision</CardTitle>
          </CardHeader>
          <CardContent className="flex flex-wrap gap-2">
            {['next_round', 'reject', 'hold', 'shortlist', 'final_selection'].map((x) => (
              <Button key={x} variant="outline" onClick={() => decision.mutate(x)}>
                {label(x)}
              </Button>
            ))}
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Interview timeline</CardTitle>
          </CardHeader>
          <CardContent>
            <Timeline
              items={item.history.map((x) => ({
                id: x.id,
                title: label(x.action),
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
function Scorecard({ item }: { item: Interview }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Panel scorecard</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-bold">
          {item.overall_score ?? '—'}
          <span className="text-muted-foreground text-sm"> / 10</span>
        </p>
        <p>{item.overall_recommendation ? label(item.overall_recommendation) : 'Feedback pending'}</p>
        {item.feedback.map((x) => (
          <div key={x.id} className="mt-3 border-t pt-2">
            <b>{label(x.recommendation)}</b>
            <p className="text-sm">{x.overall_comments}</p>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

export function InterviewEdit({ id }: { id: string }) {
  const q = useInterview(id);
  const router = useRouter();
  const update = useInterviewMutation((data: unknown) => interviewsApi.update(id, data));
  const [round, setRound] = React.useState('');
  const [notes, setNotes] = React.useState('');
  React.useEffect(() => {
    if (q.data) {
      setRound(q.data.interview_round);
      setNotes(q.data.recruiter_notes || '');
    }
  }, [q.data]);
  if (q.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} />;
  return (
    <form
      className="space-y-6"
      onSubmit={(e) => {
        e.preventDefault();
        update.mutate(
          { interview_round: round, recruiter_notes: notes },
          { onSuccess: () => router.push(`/interviews/${id}`) },
        );
      }}
    >
      <PageHeader title="Edit Interview" description={q.data.interview_code} />
      <Card>
        <CardContent className="space-y-4 p-6">
          <Label>Interview round</Label>
          <Input value={round} onChange={(e) => setRound(e.target.value)} />
          <Label>Recruiter notes</Label>
          <Textarea value={notes} onChange={(e) => setNotes(e.target.value)} />
          <Button type="submit">Save interview</Button>
        </CardContent>
      </Card>
    </form>
  );
}

export function CandidateInterviewTimeline({ candidateId }: { candidateId: string }) {
  const q = useInterviews({ page: 1, page_size: 100, candidate_id: candidateId });
  if (q.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} />;
  return (
    <div className="space-y-6">
      <PageHeader
        title="Candidate Interview Timeline"
        description={`Complete interview history for candidate ${candidateId}`}
      />
      <Timeline
        items={q.data.items.flatMap((item) =>
          item.history.map((event) => ({
            id: event.id,
            title: `${item.interview_code}: ${label(event.action)}`,
            timestamp: event.created_at,
            description: event.comments,
          })),
        )}
      />
    </div>
  );
}

async function downloadReport(): Promise<void> {
  const response = await apiClient.get('/interviews/export?format=xlsx', { responseType: 'blob' });
  const url = URL.createObjectURL(response.data as Blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = 'interviews.xlsx';
  anchor.click();
  URL.revokeObjectURL(url);
}
const label = (value: string) => value.replaceAll('_', ' ').replace(/^./, (x) => x.toUpperCase());
