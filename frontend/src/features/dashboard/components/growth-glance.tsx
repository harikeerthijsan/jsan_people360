'use client';

import { Globe, Headset, UserRoundPlus, Users, type LucideIcon } from 'lucide-react';
import * as React from 'react';

import { BarChart, LineChart } from '@/components/common/charts';
import { Card, CardContent } from '@/components/ui/card';
import { cn } from '@/lib/utils';

/**
 * "JSAN growth at a glance" -- the company story shown on every dashboard,
 * whatever the viewer's role.
 *
 * Built as a component rather than pasted as an image so it stays crisp on any
 * screen, follows the theme, reads to a screen reader and can be brought up
 * to date by editing the figures below. The numbers are the published
 * company figures, not live data.
 */

const FOUNDED = 2019;

/** Countries with a JSAN office, by year. */
const OFFICE_PRESENCE = [
  { year: 2019, countries: 3 },
  { year: 2020, countries: 5 },
  { year: 2021, countries: 8 },
  { year: 2022, countries: 12 },
  { year: 2023, countries: 18 },
  { year: 2024, countries: 21 },
  { year: 2025, countries: 22 },
];

/** People managed on the platform, by year. */
const WORKFORCE = [
  { year: 2020, people: 220 },
  { year: 2021, people: 320 },
  { year: 2022, people: 450 },
  { year: 2023, people: 650 },
  { year: 2024, people: 850 },
  { year: 2025, people: 1200 },
  { year: 2026, people: 5000 },
];

interface Highlight {
  icon: LucideIcon;
  value: string;
  label: string;
  hint: string;
}

const HIGHLIGHTS: Highlight[] = [
  { icon: Globe, value: '22+', label: 'Countries', hint: 'Global office presence' },
  { icon: Users, value: '5,000+', label: 'Workforce managed', hint: 'Across the globe' },
  { icon: Headset, value: '24/7', label: 'Global support', hint: 'Always on, every region' },
  { icon: UserRoundPlus, value: '50+', label: 'Recruitment solutions', hint: 'Hiring and delivery support' },
];

const formatCount = (value: number): string => value.toLocaleString('en-IN');

/** The last point on each series is an open-ended "and counting" figure. */
const formatOpenEnded =
  (last: number) =>
  (value: number): string =>
    value === last ? `${formatCount(value)}+` : formatCount(value);

function ChartHeading({ title, description }: { title: string; description: string }): React.JSX.Element {
  return (
    <div className="mb-3">
      <h3 className="text-sm font-semibold">{title}</h3>
      <p className="text-muted-foreground text-xs">{description}</p>
    </div>
  );
}

export function GrowthGlance({ className }: { className?: string }): React.JSX.Element {
  const years = new Date().getFullYear() - FOUNDED;
  const latestCountries = OFFICE_PRESENCE.at(-1)?.countries ?? 0;
  const latestWorkforce = WORKFORCE.at(-1)?.people ?? 0;

  return (
    <Card className={cn('overflow-hidden', className)}>
      <CardContent className="space-y-8 p-6 sm:p-8">
        {/* Title row */}
        <header className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
          <div className="space-y-1">
            <p className="text-primary text-[11px] font-semibold tracking-[0.14em] uppercase">
              Company overview
            </p>
            <h2 className="text-2xl font-semibold tracking-tight sm:text-3xl">JSAN growth at a glance</h2>
            <p className="text-muted-foreground text-sm">
              Driven by people. Powered by technology. Focused on excellence.
            </p>
          </div>
          <p className="text-muted-foreground text-xs">
            {years} years of excellence · {formatCount(latestWorkforce)}+ workforce managed ·{' '}
            {latestCountries}+ countries
          </p>
        </header>

        {/* Key figures */}
        <dl className="stagger divide-border/70 grid grid-cols-2 gap-y-6 lg:grid-cols-4 lg:divide-x">
          {HIGHLIGHTS.map((item) => (
            <div
              key={item.label}
              className="animate-rise flex flex-col gap-1 px-1 lg:px-6 lg:first:pl-0 lg:last:pr-0"
            >
              <dt className="text-muted-foreground flex items-center gap-2 text-xs font-medium">
                <item.icon className="text-primary size-3.5" aria-hidden="true" />
                {item.label}
              </dt>
              <dd className="text-3xl font-semibold tracking-tight tabular-nums">{item.value}</dd>
              <dd className="text-muted-foreground text-xs">{item.hint}</dd>
            </div>
          ))}
        </dl>

        {/* Trends */}
        <div className="grid gap-8 lg:grid-cols-2">
          <section aria-label="Global office presence, by year">
            <ChartHeading
              title="Global office presence"
              description="Countries with a JSAN office, expanding our footprint across the world"
            />
            <LineChart
              data={OFFICE_PRESENCE.map((point) => ({ label: String(point.year), value: point.countries }))}
              ariaLabel="Countries with a JSAN office, by year"
              area
              height={200}
              formatValue={formatOpenEnded(latestCountries)}
            />
          </section>

          <section aria-label="Workforce managed, by year">
            <ChartHeading title="Workforce managed" description="Building a strong global talent ecosystem" />
            <BarChart
              data={WORKFORCE.map((point) => ({ label: String(point.year), value: point.people }))}
              ariaLabel="Workforce managed, by year"
              height={200}
              formatValue={formatOpenEnded(latestWorkforce)}
            />
          </section>
        </div>
      </CardContent>
    </Card>
  );
}
