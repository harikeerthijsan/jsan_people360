'use client';

import * as React from 'react';

import { EmptyState } from '@/components/common/empty-state';
import { PageHeader } from '@/components/common/page-header';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Textarea } from '@/components/ui/textarea';
import { useMyExitInterview, useMyOffboarding, useSubmitExitInterview } from '@/features/offboarding/hooks';
import type { ExitInterviewInput } from '@/features/offboarding/types';
import { cn } from '@/lib/utils';

/**
 * My Exit Interview.
 *
 * Available once the resignation has been approved, and submitted once. After
 * that the answers are shown back rather than the form: an exit interview that
 * could be edited after the fact is not evidence of anything.
 *
 * The ratings are optional on purpose. Somebody leaving on bad terms who
 * answers nothing but "reason for leaving" has still told HR something, and a
 * required five-star grid is how you get five threes.
 */

const DEFAULT_REASON = 'Career change';

const REASONS = [
  DEFAULT_REASON,
  'Better opportunity',
  'Compensation',
  'Work environment',
  'Management',
  'Relocation',
  'Personal reasons',
  'Higher studies',
  'Other',
];

interface RatingProps {
  label: string;
  value: number | null;
  onChange: (value: number) => void;
}

function Rating({ label, value, onChange }: RatingProps): React.JSX.Element {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <div className="flex gap-2">
        {[1, 2, 3, 4, 5].map((score) => (
          <button
            key={score}
            type="button"
            onClick={() => onChange(score)}
            aria-label={`${label}: ${String(score)} out of 5`}
            aria-pressed={value === score}
            className={cn(
              'h-9 w-9 rounded-md border text-sm font-medium transition-colors',
              value === score
                ? 'bg-primary text-primary-foreground border-primary'
                : 'border-input hover:bg-accent',
            )}
          >
            {score}
          </button>
        ))}
      </div>
    </div>
  );
}

export function MyExitInterviewPage(): React.JSX.Element {
  const existing = useMyExitInterview();
  const offboarding = useMyOffboarding();
  const submit = useSubmitExitInterview();

  const [form, setForm] = React.useState<ExitInterviewInput>({
    reason_for_leaving: DEFAULT_REASON,
    overall_experience: null,
    management_rating: null,
    work_environment_rating: null,
    career_growth_rating: null,
    compensation_rating: null,
    management_feedback: '',
    suggestions: '',
    would_recommend: null,
    would_rejoin: null,
  });

  const set = <K extends keyof ExitInterviewInput>(key: K, value: ExitInterviewInput[K]): void =>
    setForm((current) => ({ ...current, [key]: value }));

  if (existing.isLoading || offboarding.isLoading) {
    return <EmptyState title="Loading" description="Fetching your exit interview." />;
  }

  const submitted = existing.data;
  if (submitted?.submitted_at) {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Exit interview"
          description={`Submitted on ${new Date(submitted.submitted_at).toLocaleDateString()}. Thank you.`}
        />
        <Card className="max-w-2xl">
          <CardHeader>
            <CardTitle>Your answers</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <Answer label="Reason for leaving" value={submitted.reason_for_leaving} />
            <Answer label="Overall experience" value={rating(submitted.overall_experience)} />
            <Answer label="Management" value={rating(submitted.management_rating)} />
            <Answer label="Work environment" value={rating(submitted.work_environment_rating)} />
            <Answer label="Career growth" value={rating(submitted.career_growth_rating)} />
            <Answer label="Compensation" value={rating(submitted.compensation_rating)} />
            <Answer label="Would recommend" value={yesNo(submitted.would_recommend)} />
            <Answer label="Would rejoin" value={yesNo(submitted.would_rejoin)} />
            {submitted.suggestions ? <Answer label="Suggestions" value={submitted.suggestions} /> : null}
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!offboarding.data?.exit_interview_available) {
    return (
      <EmptyState
        title="Not available yet"
        description="Your exit interview opens once your resignation has been approved and your offboarding has started."
      />
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Exit interview"
        description="Your answers go to HR. This is submitted once and cannot be edited afterwards."
      />
      <Card className="max-w-2xl">
        <CardContent className="pt-6">
          <form
            className="space-y-6"
            onSubmit={(event) => {
              event.preventDefault();
              submit.mutate(form);
            }}
          >
            <div className="space-y-2">
              <Label htmlFor="reason">Reason for leaving</Label>
              <select
                id="reason"
                className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                value={form.reason_for_leaving}
                onChange={(event) => set('reason_for_leaving', event.target.value)}
              >
                {REASONS.map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <Rating
                label="Overall experience"
                value={form.overall_experience ?? null}
                onChange={(value) => set('overall_experience', value)}
              />
              <Rating
                label="Management"
                value={form.management_rating ?? null}
                onChange={(value) => set('management_rating', value)}
              />
              <Rating
                label="Work environment"
                value={form.work_environment_rating ?? null}
                onChange={(value) => set('work_environment_rating', value)}
              />
              <Rating
                label="Career growth"
                value={form.career_growth_rating ?? null}
                onChange={(value) => set('career_growth_rating', value)}
              />
              <Rating
                label="Compensation"
                value={form.compensation_rating ?? null}
                onChange={(value) => set('compensation_rating', value)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="management-feedback">Feedback on management (optional)</Label>
              <Textarea
                id="management-feedback"
                rows={3}
                value={form.management_feedback ?? ''}
                onChange={(event) => set('management_feedback', event.target.value)}
              />
            </div>

            <div className="space-y-2">
              <Label htmlFor="suggestions">Suggestions (optional)</Label>
              <Textarea
                id="suggestions"
                rows={3}
                value={form.suggestions ?? ''}
                onChange={(event) => set('suggestions', event.target.value)}
              />
            </div>

            <div className="grid gap-4 sm:grid-cols-2">
              <Choice
                label="Would you recommend this company?"
                value={form.would_recommend ?? null}
                onChange={(value) => set('would_recommend', value)}
              />
              <Choice
                label="Would you consider rejoining?"
                value={form.would_rejoin ?? null}
                onChange={(value) => set('would_rejoin', value)}
              />
            </div>

            <Button type="submit" disabled={submit.isPending}>
              {submit.isPending ? 'Submitting…' : 'Submit exit interview'}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}

function Choice({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean | null;
  onChange: (value: boolean) => void;
}): React.JSX.Element {
  return (
    <div className="space-y-2">
      <Label>{label}</Label>
      <div className="flex gap-2">
        {[true, false].map((option) => (
          <Button
            key={String(option)}
            type="button"
            variant={value === option ? 'default' : 'outline'}
            size="sm"
            onClick={() => onChange(option)}
          >
            {option ? 'Yes' : 'No'}
          </Button>
        ))}
      </div>
    </div>
  );
}

function Answer({ label, value }: { label: string; value: string }): React.JSX.Element {
  return (
    <div className="flex items-start justify-between gap-4">
      <span className="text-muted-foreground">{label}</span>
      <span className="text-right font-medium">{value}</span>
    </div>
  );
}

function rating(value: number | null): string {
  return value === null ? 'Not answered' : `${String(value)} / 5`;
}

function yesNo(value: boolean | null): string {
  if (value === null) return 'Not answered';
  return value ? 'Yes' : 'No';
}
