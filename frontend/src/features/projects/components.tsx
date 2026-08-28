'use client';
import { zodResolver } from '@hookform/resolvers/zod';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import * as React from 'react';
import { useForm } from 'react-hook-form';
import type { z } from 'zod';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { StatCard } from '@/components/common/stat-card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { toast } from '@/components/ui/sonner';
import { Textarea } from '@/components/ui/textarea';
import { projectsApi } from './api';
import {
  useBench,
  useClientDashboard,
  useClients,
  useProjectDashboard,
  useProjectMutation,
  useProjects,
  useResourceDashboard,
} from './hooks';
import { allocationSchema, clientSchema, projectSchema } from './schema';
import type { Allocation, BenchEmployee, Client, Project } from './types';
const human = (value: string) => value.replaceAll('_', ' ').replace(/^./, (x) => x.toUpperCase());
export function AllocationProgressBar({ value }: { value: number }) {
  const warning = value >= 90 && value <= 100;
  return (
    <div aria-label={`${String(value)} percent allocated`} className="space-y-1">
      <div className="flex justify-between text-sm">
        <span>Allocation</span>
        <b className={value > 100 ? 'text-destructive' : warning ? 'text-amber-600' : ''}>{value}%</b>
      </div>
      <div className="bg-muted h-2 rounded-full">
        <div
          className={`h-full rounded-full ${value > 100 ? 'bg-destructive' : warning ? 'bg-amber-500' : 'bg-primary'}`}
          style={{ width: `${String(Math.min(value, 100))}%` }}
        />
      </div>
    </div>
  );
}
export function UtilizationWidget({ utilization, billable }: { utilization: number; billable?: number }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Utilization</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <AllocationProgressBar value={utilization} />
        {billable === undefined ? null : (
          <p className="text-muted-foreground text-sm">Billable utilization: {billable}%</p>
        )}
      </CardContent>
    </Card>
  );
}
export function ResourceDashboard() {
  const q = useResourceDashboard();
  if (q.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} />;
  return (
    <div className="space-y-6">
      <PageHeader
        title="Project & Client Allocation"
        description="Project delivery capacity, utilization and allocation risk."
        actions={
          <Button asChild>
            <Link href="/projects/new">Create project</Link>
          </Button>
        }
      />
      <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
        {Object.entries(q.data)
          .filter(([, v]) => typeof v === 'number')
          .map(([key, value]) => (
            <StatCard key={key} label={human(key)} value={Number(value)} />
          ))}
      </div>
      <Card>
        <CardHeader>
          <CardTitle>Project-wise headcount</CardTitle>
        </CardHeader>
        <CardContent>
          {q.data.project_headcount.map((row) => (
            <div className="flex justify-between border-b py-2" key={row.project_id}>
              <Link href={`/projects/${row.project_id}`}>{row.project}</Link>
              <b>{row.headcount}</b>
            </div>
          ))}
        </CardContent>
      </Card>
    </div>
  );
}
export function ClientCard({ client }: { client: Client }) {
  return (
    <Link href={`/clients/${client.id}`}>
      <Card>
        <CardContent className="flex items-center p-4">
          <div className="flex-1">
            <b>
              {client.client_code} · {client.client_name}
            </b>
            <p className="text-muted-foreground text-sm">
              {client.company_name} · {client.industry}
            </p>
          </div>
          <Badge>{human(client.status)}</Badge>
        </CardContent>
      </Card>
    </Link>
  );
}
export function ClientList() {
  const q = useClients();
  return (
    <div className="space-y-6">
      <PageHeader
        title="Clients"
        description="Client organizations and delivery relationships."
        actions={
          <Button asChild>
            <Link href="/clients/new">Create client</Link>
          </Button>
        }
      />
      {q.isPending ? (
        <LoadingState />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : (
        q.data.items.map((client) => <ClientCard key={client.id} client={client} />)
      )}
    </div>
  );
}
export function ClientDetails({ id }: { id: string }) {
  const q = useClientDashboard(id);
  if (q.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} />;
  const d = q.data;
  return (
    <div className="space-y-6">
      <PageHeader
        title={`${d.client.client_code} — ${d.client.client_name}`}
        description={d.client.company_name}
      />
      <div className="grid gap-4 md:grid-cols-3">
        <StatCard label="Active projects" value={d.active_projects} />
        <StatCard label="Employees" value={d.total_employees} />
        <StatCard label="Billable employees" value={d.billable_employees} />
      </div>
      <Card>
        <CardContent className="grid gap-2 p-6 md:grid-cols-2">
          <p>Industry: {d.client.industry}</p>
          <p>Country: {d.client.country}</p>
          <p>Contact: {d.client.contact_person}</p>
          <p>Email: {d.client.email}</p>
        </CardContent>
      </Card>
    </div>
  );
}
type ClientValues = z.infer<typeof clientSchema>;
export function ClientForm() {
  const router = useRouter();
  const mutation = useProjectMutation((data: ClientValues) => projectsApi.createClient(data));
  const form = useForm<ClientValues>({
    resolver: zodResolver(clientSchema),
    defaultValues: {
      client_name: '',
      company_name: '',
      industry: '',
      contact_person: '',
      email: '',
      phone: '',
      country: '',
      address: '',
      website: null,
      status: 'active',
    },
  });
  return (
    <form
      className="space-y-6"
      onSubmit={form.handleSubmit((v) =>
        mutation.mutate(v, { onSuccess: (x) => router.push(`/clients/${x.id}`) }),
      )}
    >
      <PageHeader title="Create Client" description="Register a client and its primary delivery contact." />
      <Card>
        <CardContent className="grid gap-4 p-6 md:grid-cols-2">
          {(
            [
              'client_name',
              'company_name',
              'industry',
              'contact_person',
              'email',
              'phone',
              'country',
              'website',
            ] as const
          ).map((name) => (
            <Field key={name} label={human(name)}>
              <Input
                {...form.register(name, {
                  setValueAs: (value: unknown) => (name === 'website' && !value ? null : value),
                })}
              />
            </Field>
          ))}
          <div className="md:col-span-2">
            <Field label="Address">
              <Textarea {...form.register('address')} />
            </Field>
          </div>
          <Button className="md:col-span-2" type="submit" isLoading={mutation.isPending}>
            Create client
          </Button>
        </CardContent>
      </Card>
    </form>
  );
}
export function ProjectCard({ project }: { project: Project }) {
  const current = project.allocations
    .filter((x) => x.status === 'active')
    .reduce((n, x) => n + Number(x.allocation_percentage), 0);
  return (
    <Link href={`/projects/${project.id}`}>
      <Card>
        <CardContent className="flex items-center gap-4 p-4">
          <div className="flex-1">
            <b>
              {project.project_code} · {project.project_name}
            </b>
            <p className="text-muted-foreground text-sm">
              {project.client.client_name} · {project.technology_stack.join(', ')}
            </p>
          </div>
          <div className="w-40">
            <AllocationProgressBar value={current} />
          </div>
          <Badge>{human(project.status)}</Badge>
        </CardContent>
      </Card>
    </Link>
  );
}
export function ProjectList() {
  const q = useProjects();
  return (
    <div className="space-y-6">
      <PageHeader
        title="Projects"
        description="Delivery portfolio and employee allocation."
        actions={
          <Button asChild>
            <Link href="/projects/new">Create project</Link>
          </Button>
        }
      />
      {q.isPending ? (
        <LoadingState />
      ) : q.error ? (
        <ErrorState error={q.error} />
      ) : (
        q.data.items.map((project) => <ProjectCard key={project.id} project={project} />)
      )}
    </div>
  );
}
type ProjectValues = z.input<typeof projectSchema>;
export function ProjectForm() {
  const router = useRouter();
  const mutation = useProjectMutation((data: unknown) => projectsApi.createProject(data));
  const form = useForm<ProjectValues>({
    resolver: zodResolver(projectSchema),
    defaultValues: {
      project_name: '',
      client_id: '',
      description: '',
      start_date: '',
      end_date: null,
      status: 'planned',
      project_manager_id: '',
      delivery_manager_id: null,
      work_location_id: null,
      is_billable: true,
      technology_stack: '',
      priority: 'medium',
    },
  });
  const optional = new Set(['delivery_manager_id', 'work_location_id', 'end_date']);
  return (
    <form
      className="space-y-6"
      onSubmit={form.handleSubmit((v) =>
        mutation.mutate(projectSchema.parse(v), { onSuccess: (x) => router.push(`/projects/${x.id}`) }),
      )}
    >
      <PageHeader
        title="Create Project"
        description="Create a delivery project with a mandatory project manager."
      />
      <Card>
        <CardContent className="grid gap-4 p-6 md:grid-cols-2">
          {(
            [
              'project_name',
              'client_id',
              'start_date',
              'end_date',
              'project_manager_id',
              'delivery_manager_id',
              'work_location_id',
              'technology_stack',
            ] as const
          ).map((name) => (
            <Field key={name} label={human(name)}>
              <Input
                type={name.includes('date') ? 'date' : 'text'}
                {...form.register(name, {
                  setValueAs: (value: unknown) => (optional.has(name) && !value ? null : value),
                })}
              />
            </Field>
          ))}
          <Field label="Priority">
            <select
              className="bg-background h-10 w-full rounded-md border px-3"
              {...form.register('priority')}
            >
              {['low', 'medium', 'high', 'critical'].map((x) => (
                <option key={x}>{x}</option>
              ))}
            </select>
          </Field>
          <div className="md:col-span-2">
            <Field label="Description">
              <Textarea {...form.register('description')} />
            </Field>
          </div>
          <label className="flex items-center gap-2">
            <input type="checkbox" {...form.register('is_billable')} />
            Billable project
          </label>
          <Button className="md:col-span-2" type="submit" isLoading={mutation.isPending}>
            Create project
          </Button>
        </CardContent>
      </Card>
    </form>
  );
}
export function TeamTable({ allocations }: { allocations: Allocation[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Project team</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b text-left">
                <th className="p-2">Employee</th>
                <th>Allocation</th>
                <th>Dates</th>
                <th>Billable</th>
              </tr>
            </thead>
            <tbody>
              {allocations.map((x) => (
                <tr className="border-b" key={x.id}>
                  <td className="p-2">{x.employee_id}</td>
                  <td className="w-48">
                    <AllocationProgressBar value={Number(x.allocation_percentage)} />
                  </td>
                  <td>
                    {x.start_date} — {x.end_date ?? 'Ongoing'}
                  </td>
                  <td>{x.billable ? 'Yes' : 'No'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </CardContent>
    </Card>
  );
}
export function ProjectDetails({ id }: { id: string }) {
  const q = useProjectDashboard(id);
  if (q.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} />;
  const d = q.data;
  return (
    <div className="space-y-6">
      <PageHeader
        title={`${d.project.project_code} — ${d.project.project_name}`}
        description={`${d.project.client.client_name} · ${human(d.project.status)}`}
        actions={
          <Button asChild>
            <Link href={`/projects/${id}/allocate`}>Assign employee</Link>
          </Button>
        }
      />
      <div className="grid gap-4 md:grid-cols-3">
        <StatCard label="Headcount" value={d.headcount} />
        <UtilizationWidget utilization={d.utilization_percent} billable={d.billable_percent} />
        <StatCard label="Ending soon" value={d.upcoming_end_dates.length} />
      </div>
      <TeamTable allocations={d.team_members} />
      <AllocationTimeline allocations={d.project.allocations} />
    </div>
  );
}
export function AllocationTimeline({ allocations }: { allocations: Allocation[] }) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Allocation timeline</CardTitle>
      </CardHeader>
      <CardContent>
        {[...allocations]
          .sort((a, b) => b.start_date.localeCompare(a.start_date))
          .map((x) => (
            <div className="border-l-2 pb-4 pl-4" key={x.id}>
              <b>
                {x.start_date} · {x.allocation_percentage}%
              </b>
              <p className="text-muted-foreground text-sm">
                {human(x.status)} — {x.reason}
              </p>
            </div>
          ))}
      </CardContent>
    </Card>
  );
}
type AllocationValues = z.input<typeof allocationSchema>;
export function AllocationForm({ projectId }: { projectId: string }) {
  const router = useRouter();
  const mutation = useProjectMutation((data: unknown) => projectsApi.assign(projectId, data));
  const form = useForm<AllocationValues>({
    resolver: zodResolver(allocationSchema),
    defaultValues: {
      employee_id: '',
      role: '',
      allocation_percentage: 100,
      start_date: '',
      end_date: null,
      reporting_manager_id: null,
      billable: true,
      reason: '',
    },
  });
  return (
    <form
      className="space-y-6"
      onSubmit={form.handleSubmit((v) =>
        mutation.mutate(allocationSchema.parse(v), {
          onSuccess: () => router.push(`/projects/${projectId}`),
        }),
      )}
    >
      <PageHeader
        title="Allocate Employee"
        description="Overlapping allocations are validated against the 100% capacity limit."
      />
      <Card>
        <CardContent className="grid gap-4 p-6 md:grid-cols-2">
          {(
            [
              'employee_id',
              'role',
              'allocation_percentage',
              'start_date',
              'end_date',
              'reporting_manager_id',
              'reason',
            ] as const
          ).map((name) => (
            <Field key={name} label={human(name)}>
              <Input
                type={name.includes('date') ? 'date' : name === 'allocation_percentage' ? 'number' : 'text'}
                {...form.register(name, {
                  setValueAs: (value: unknown) =>
                    ['end_date', 'reporting_manager_id'].includes(name) && !value ? null : value,
                })}
              />
            </Field>
          ))}
          <label className="flex items-center gap-2">
            <input type="checkbox" {...form.register('billable')} />
            Billable allocation
          </label>
          <Button className="md:col-span-2" type="submit" isLoading={mutation.isPending}>
            Assign employee
          </Button>
          {mutation.error ? <p className="text-destructive">{mutation.error.message}</p> : null}
        </CardContent>
      </Card>
    </form>
  );
}
export function BenchStatusBadge({ days }: { days: number }) {
  return <Badge variant={days > 30 ? 'destructive' : 'secondary'}>{days} days on bench</Badge>;
}
export function BenchDashboard() {
  const q = useBench();
  if (q.isPending) return <LoadingState />;
  if (q.error) return <ErrorState error={q.error} />;
  return (
    <div className="space-y-6">
      <PageHeader
        title="Bench Management"
        description="Active employees with zero current allocation."
        actions={<ReportLinks report="bench" />}
      />
      {q.data.map((employee) => (
        <BenchCard key={employee.employee_id} employee={employee} />
      ))}
    </div>
  );
}
function BenchCard({ employee }: { employee: BenchEmployee }) {
  return (
    <Card>
      <CardContent className="flex items-center p-4">
        <div className="flex-1">
          <b>
            {employee.employee_code} · {employee.name}
          </b>
          <p className="text-muted-foreground text-sm">
            {employee.team ?? 'No team'} · Manager: {employee.manager ?? 'Unassigned'}
          </p>
          <p className="text-xs">{employee.skills.join(', ') || 'No recorded skills'}</p>
        </div>
        <BenchStatusBadge days={employee.bench_duration_days} />
      </CardContent>
    </Card>
  );
}
function ReportLinks({ report }: { report: string }) {
  const [downloading, setDownloading] = React.useState<'csv' | 'xlsx' | null>(null);
  const download = async (fmt: 'csv' | 'xlsx'): Promise<void> => {
    setDownloading(fmt);
    try {
      await projectsApi.exportReport(report, fmt);
    } catch {
      toast.error('The export could not be prepared.');
    } finally {
      setDownloading(null);
    }
  };
  return (
    <div className="flex gap-2">
      <Button variant="outline" isLoading={downloading === 'csv'} onClick={() => void download('csv')}>
        CSV
      </Button>
      <Button variant="outline" isLoading={downloading === 'xlsx'} onClick={() => void download('xlsx')}>
        Excel
      </Button>
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
