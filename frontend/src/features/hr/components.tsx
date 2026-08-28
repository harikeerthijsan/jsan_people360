'use client';
import { useParams, useRouter } from 'next/navigation';
import * as React from 'react';
import { BarChart3, CalendarClock, FileText, UserRoundPlus, Users } from 'lucide-react';
import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { DetailSection } from '@/components/common/detail-view';
import { Timeline } from '@/components/common/timeline';
import { ErrorState } from '@/components/common/error-state';
import { PageHeader } from '@/components/common/page-header';
import { Pagination } from '@/components/common/pagination';
import { StatCard } from '@/components/common/stat-card';
import { Tabs } from '@/components/common/tabs';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { api } from '@/lib/api/client';
import type { PageMeta } from '@/lib/api/types';
import { toast } from '@/components/ui/sonner';
import {
  useHrAnalytics,
  useHrDashboard,
  useHrEmployee,
  useHrEmployees,
  useHrPerformance,
  useHrProjects,
  useHrList,
  useHrResource,
} from './hooks';
import type {
  AttendanceRow,
  DocumentRow,
  HrEmployee,
  LeavePolicy,
  LeaveRow,
  Report,
  TimesheetRow,
  Trend,
  HrBenchRow,
  HrProfile,
} from './types';

const text = (value: unknown): string =>
  value === null || value === undefined || value === '' ? '—' : String(value);
const minutes = (value: number): string => `${String(Math.floor(value / 60))}h ${String(value % 60)}m`;
const dateTime = (value: string | null): string =>
  value ? new Date(value).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' }) : '—';
const status = (value: string) => <Badge variant="outline">{value.replaceAll('_', ' ')}</Badge>;

function TrendCard({ title, data }: { title: string; data: Trend[] }): React.JSX.Element {
  const max = Math.max(1, ...data.map((point) => point.count));
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex h-36 items-end gap-2" aria-label={title}>
          {data.map((point) => (
            <div className="flex min-w-0 flex-1 flex-col items-center gap-1" key={point.period}>
              <span className="text-xs font-medium">{point.count}</span>
              <div
                className="bg-primary w-full rounded-t"
                style={{ height: `${String(Math.max(4, (point.count / max) * 100))}px` }}
              />
              <span className="text-muted-foreground truncate text-[10px]">{point.label}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export function HrDashboardPage(): React.JSX.Element {
  const dashboard = useHrDashboard();
  const analytics = useHrAnalytics();
  if (dashboard.error) return <ErrorState error={dashboard.error} onRetry={() => void dashboard.refetch()} />;
  const d = dashboard.data;
  return (
    <div className="space-y-6">
      <PageHeader
        title="HR Dashboard"
        description="People operations, workforce health, and queues requiring HR attention."
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {d?.employees && (
          <>
            <StatCard icon={Users} label="Active employees" value={d.employees.total_active} />
            <StatCard icon={UserRoundPlus} label="New joiners" value={d.employees.new_joiners_this_month} />
            <StatCard label="On probation" value={d.employees.on_probation} />
            <StatCard label="Exiting" value={d.employees.exiting} />
          </>
        )}
        {d?.attendance && (
          <>
            <StatCard icon={CalendarClock} label="Present today" value={d.attendance.present} />
            <StatCard label="Absent today" value={d.attendance.absent} />
            <StatCard label="Late arrivals" value={d.attendance.late_arrivals} />
            <StatCard label="Employees on leave" value={d.attendance.on_leave} />
          </>
        )}
        {d?.recruitment && (
          <>
            <StatCard label="Open requisitions" value={d.recruitment.open_requisitions} />
            <StatCard label="Active candidates" value={d.recruitment.active_candidates} />
            <StatCard label="Interviews" value={d.recruitment.interviews_scheduled} />
            <StatCard label="Pending onboarding" value={d.recruitment.onboarding_in_progress} />
          </>
        )}
        {d?.documents && (
          <>
            <StatCard icon={FileText} label="Pending document reviews" value={d.documents.pending_review} />
            <StatCard label="Rejected documents" value={d.documents.rejected} />
          </>
        )}
        {d?.performance && (
          <>
            <StatCard label="Active cycles" value={d.performance.active_cycles} />
            <StatCard label="Review completion" value={`${String(d.performance.completion_percentage)}%`} />
          </>
        )}
        {d?.requests && (
          <StatCard
            label="Open HR requests"
            value={
              d.requests.documents_awaiting_review +
              d.requests.leave_without_a_manager +
              d.requests.regularizations_without_a_manager
            }
            hint={`Oldest: ${String(d.requests.oldest_waiting_days)} days`}
          />
        )}
      </div>
      {analytics.data && (
        <>
          <div className="grid gap-4 lg:grid-cols-2">
            <TrendCard title="Headcount trend" data={analytics.data.headcount_trend} />
            <TrendCard title="Hiring trend" data={analytics.data.hiring_trend} />
            <TrendCard title="Leave trend" data={analytics.data.leave_trend} />
            <TrendCard title="Attendance trend" data={analytics.data.attendance_trend} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <StatCard
              icon={BarChart3}
              label="Performance completion"
              value={`${String(analytics.data.performance_completion)}%`}
            />
            <StatCard label="Document compliance" value={`${String(analytics.data.document_compliance)}%`} />
          </div>
        </>
      )}
    </div>
  );
}

function Filters({
  search,
  setSearch,
  from,
  setFrom,
  to,
  setTo,
}: {
  search: string;
  setSearch: (v: string) => void;
  from?: string;
  setFrom?: (v: string) => void;
  to?: string;
  setTo?: (v: string) => void;
}) {
  return (
    <div className="flex flex-wrap gap-3">
      <Input
        className="max-w-sm"
        placeholder="Search or employee ID"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
      />
      {setFrom && (
        <Input
          aria-label="From date"
          className="w-44"
          type="date"
          value={from}
          onChange={(e) => setFrom(e.target.value)}
        />
      )}{' '}
      {setTo && (
        <Input
          aria-label="To date"
          className="w-44"
          type="date"
          value={to}
          onChange={(e) => setTo(e.target.value)}
        />
      )}
    </div>
  );
}

export function HrEmployeesPage(): React.JSX.Element {
  const router = useRouter();
  const [page, setPage] = React.useState(1);
  const [search, setSearch] = React.useState('');
  const query = useHrEmployees({ page, page_size: 20, ...(search ? { search } : {}) });
  const columns: DataTableColumn<HrEmployee>[] = [
    {
      id: 'employee',
      header: 'Employee',
      cell: (r) => (
        <div>
          <p className="font-medium">{r.full_name}</p>
          <p className="text-muted-foreground text-xs">{r.employee_code}</p>
        </div>
      ),
    },
    { id: 'designation', header: 'Designation', cell: (r) => text(r.designation?.name) },
    {
      id: 'unit',
      header: 'Business unit / team',
      cell: (r) => `${text(r.business_unit?.name)} / ${text(r.team?.name)}`,
    },
    { id: 'manager', header: 'Manager', cell: (r) => text(r.reporting_manager?.full_name) },
    { id: 'joining', header: 'Joined', cell: (r) => r.joining_date },
    { id: 'status', header: 'Status', cell: (r) => status(r.employment_status) },
  ];
  return (
    <ListShell
      title="HR Employees"
      description="Operational employee information. Sensitive financial, identity, and authentication data is excluded."
      filters={
        <Filters
          search={search}
          setSearch={(v) => {
            setSearch(v);
            setPage(1);
          }}
        />
      }
      query={query}
      columns={columns}
      rowId={(r) => r.id}
      page={page}
      setPage={setPage}
      onRow={(r) => router.push(`/hr/employees/${r.id}`)}
    />
  );
}

interface QueryLike<T> {
  data?: { items: T[]; meta: PageMeta };
  isLoading: boolean;
  isFetching: boolean;
  error: unknown;
  refetch: () => Promise<unknown>;
}
function ListShell<T>({
  title,
  description,
  filters,
  query,
  columns,
  rowId,
  setPage,
  onRow,
}: {
  title: string;
  description: string;
  filters?: React.ReactNode;
  query: QueryLike<T>;
  columns: DataTableColumn<T>[];
  rowId: (r: T) => string;
  page: number;
  setPage: (p: number) => void;
  onRow?: (r: T) => void;
}): React.JSX.Element {
  return (
    <div className="space-y-6">
      <PageHeader title={title} description={description} />
      {filters}
      <DataTable
        columns={columns}
        rows={query.data?.items ?? []}
        getRowId={rowId}
        isLoading={query.isLoading}
        error={query.error}
        onRetry={() => void query.refetch()}
        onRowClick={onRow}
      />
      {query.data && <Pagination meta={query.data.meta} onPageChange={setPage} disabled={query.isFetching} />}
    </div>
  );
}

export function HrAttendancePage(): React.JSX.Element {
  const [page, setPage] = React.useState(1),
    [employee, setEmployee] = React.useState(''),
    [from, setFrom] = React.useState(''),
    [to, setTo] = React.useState('');
  const q = useHrList('attendance', {
    page,
    page_size: 20,
    ...(employee ? { employee_id: employee } : {}),
    ...(from ? { from_date: from } : {}),
    ...(to ? { to_date: to } : {}),
  }) as QueryLike<AttendanceRow>;
  const c: DataTableColumn<AttendanceRow>[] = [
    { id: 'employee', header: 'Employee', cell: (r) => r.employee.full_name },
    { id: 'date', header: 'Date', cell: (r) => r.record.attendance_date },
    { id: 'in', header: 'Check in', cell: (r) => dateTime(r.record.check_in_at) },
    { id: 'out', header: 'Check out', cell: (r) => dateTime(r.record.check_out_at) },
    { id: 'hours', header: 'Working', cell: (r) => minutes(r.record.worked_minutes) },
    { id: 'status', header: 'Status', cell: (r) => status(r.record.status) },
    { id: 'late', header: 'Late', cell: (r) => minutes(r.record.late_minutes) },
    { id: 'early', header: 'Early exit', cell: (r) => minutes(r.record.early_exit_minutes) },
    { id: 'ot', header: 'Overtime', cell: (r) => minutes(r.record.overtime_minutes) },
  ];
  return (
    <ListShell
      title="HR Attendance"
      description="Organization attendance is read-only unless attendance administration is explicitly granted."
      filters={
        <Filters
          search={employee}
          setSearch={setEmployee}
          from={from}
          setFrom={setFrom}
          to={to}
          setTo={setTo}
        />
      }
      query={q}
      columns={c}
      rowId={(r) => r.record.id}
      page={page}
      setPage={setPage}
    />
  );
}

export function HrLeavePage(): React.JSX.Element {
  const [page, setPage] = React.useState(1),
    [employee, setEmployee] = React.useState('');
  const q = useHrList('leave', {
    page,
    page_size: 20,
    ...(employee ? { employee_id: employee } : {}),
  }) as QueryLike<LeaveRow>;
  const c: DataTableColumn<LeaveRow>[] = [
    { id: 'employee', header: 'Employee', cell: (r) => r.employee.full_name },
    { id: 'type', header: 'Leave type', cell: (r) => text(r.request.leave_type?.name) },
    { id: 'dates', header: 'Dates', cell: (r) => `${r.request.from_date} – ${r.request.to_date}` },
    { id: 'days', header: 'Days', cell: (r) => r.request.days },
    { id: 'manager', header: 'Approving manager', cell: (r) => text(r.reporting_manager?.full_name) },
    { id: 'status', header: 'Status', cell: (r) => status(r.request.status) },
  ];
  return (
    <ListShell
      title="HR Leave"
      description="Organization leave visibility. Normal decisions remain with each employee's manager."
      filters={<Filters search={employee} setSearch={setEmployee} />}
      query={q}
      columns={c}
      rowId={(r) => r.request.id}
      page={page}
      setPage={setPage}
    />
  );
}

export function HrTimesheetsPage(): React.JSX.Element {
  const [page, setPage] = React.useState(1),
    [employee, setEmployee] = React.useState('');
  const q = useHrList('timesheets', {
    page,
    page_size: 20,
    ...(employee ? { employee_id: employee } : {}),
  }) as QueryLike<TimesheetRow>;
  const c: DataTableColumn<TimesheetRow>[] = [
    { id: 'employee', header: 'Employee', cell: (r) => r.employee.full_name },
    { id: 'week', header: 'Week starting', cell: (r) => r.timesheet.week_start_date },
    { id: 'hours', header: 'Hours', cell: (r) => r.timesheet.total_hours },
    { id: 'billable', header: 'Billable', cell: (r) => r.timesheet.billable_hours },
    { id: 'status', header: 'Status', cell: (r) => status(r.timesheet.status) },
  ];
  return (
    <ListShell
      title="HR Timesheets"
      description="Organization timesheets are read-only; manager approval workflow remains unchanged."
      filters={<Filters search={employee} setSearch={setEmployee} />}
      query={q}
      columns={c}
      rowId={(r) => r.timesheet.id}
      page={page}
      setPage={setPage}
    />
  );
}

export function HrDocumentsPage(): React.JSX.Element {
  const [page, setPage] = React.useState(1),
    [search, setSearch] = React.useState('');
  const q = useHrList('documents', {
    page,
    page_size: 20,
    ...(search ? { search } : {}),
  }) as QueryLike<DocumentRow>;
  const c: DataTableColumn<DocumentRow>[] = [
    {
      id: 'document',
      header: 'Document',
      cell: (r) => (
        <div>
          <p className="font-medium">{r.name}</p>
          <p className="text-muted-foreground text-xs">{r.document_code}</p>
        </div>
      ),
    },
    { id: 'owner', header: 'Employee', cell: (r) => text(r.owner_name) },
    { id: 'created', header: 'Uploaded', cell: (r) => new Date(r.created_at).toLocaleDateString() },
    { id: 'expiry', header: 'Expiry', cell: (r) => text(r.expiry_date) },
    { id: 'status', header: 'Status', cell: (r) => status(r.status) },
  ];
  return (
    <ListShell
      title="HR Documents"
      description="The employee document review queue, restricted by document permissions."
      filters={<Filters search={search} setSearch={setSearch} />}
      query={q}
      columns={c}
      rowId={(r) => r.id}
      page={page}
      setPage={setPage}
    />
  );
}

export function HrPoliciesPage(): React.JSX.Element {
  const q = useHrResource('policies');
  const rows = (q.data ?? []) as LeavePolicy[];
  const c: DataTableColumn<LeavePolicy>[] = [
    {
      id: 'policy',
      header: 'Leave type',
      cell: (r) => (
        <div>
          <p className="font-medium">{r.name}</p>
          <p className="text-muted-foreground text-xs">{r.code}</p>
        </div>
      ),
    },
    { id: 'credit', header: 'Credit', cell: (r) => `${text(r.credit_amount)} ${text(r.credit_frequency)}` },
    { id: 'max', header: 'Annual maximum', cell: (r) => r.annual_allocation },
    {
      id: 'carry',
      header: 'Carry forward',
      cell: (r) => (r.carry_forward ? `Yes (${r.max_carry_forward})` : 'No'),
    },
    {
      id: 'effective',
      header: 'Effective',
      cell: (r) => `${text(r.effective_from)} – ${text(r.effective_to)}`,
    },
    { id: 'status', header: 'Status', cell: (r) => status(r.status) },
  ];
  return (
    <div className="space-y-6">
      <PageHeader
        title="Leave Policies"
        description="Policies consumed by the existing leave accrual engine."
      />
      <DataTable
        columns={c}
        rows={rows}
        getRowId={(r) => r.id}
        isLoading={q.isLoading}
        error={q.error}
        onRetry={() => void q.refetch()}
      />
    </div>
  );
}

export function HrProjectsPage(): React.JSX.Element {
  const q = useHrProjects();
  if (q.error) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  const data = q.data;

  const benchColumns: DataTableColumn<HrBenchRow>[] = [
    {
      id: 'name',
      header: 'Employee',
      cell: (row) => (
        <div>
          <p className="font-medium">{row.name}</p>
          <p className="text-muted-foreground text-xs">
            {row.employee_code}
            {row.team ? ` · ${row.team}` : ''}
          </p>
        </div>
      ),
    },
    {
      id: 'since',
      header: 'On bench since',
      cell: (row) => (row.bench_since ? new Date(row.bench_since).toLocaleDateString() : '—'),
    },
    {
      id: 'days',
      header: 'Days',
      align: 'right',
      cell: (row) => (
        <span className={row.bench_duration_days > 30 ? 'text-destructive font-medium' : 'tabular-nums'}>
          {row.bench_duration_days}
        </span>
      ),
    },
    {
      id: 'skills',
      header: 'Skills',
      cell: (row) =>
        row.skills.length === 0 ? (
          <span className="text-muted-foreground text-xs">Not recorded</span>
        ) : (
          <div className="flex flex-wrap gap-1">
            {row.skills.slice(0, 4).map((skill) => (
              <Badge key={skill} variant="outline">
                {skill}
              </Badge>
            ))}
          </div>
        ),
    },
    { id: 'manager', header: 'Manager', cell: (row) => row.manager ?? '—' },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="Workforce Allocation"
        description="Who is allocated where, and who is waiting for a project. Read only — changing an allocation is the project module's job."
      />

      {data ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Active projects" value={data.allocation.active_projects} />
            <StatCard label="Allocated" value={data.allocation.employees_allocated} />
            <StatCard
              label="On bench"
              value={data.allocation.bench_employees}
              hint="No active allocation today"
            />
            <StatCard
              label="Utilization"
              value={`${String(Math.round(data.allocation.allocation_utilization_percent))}%`}
              hint={
                data.allocation.allocation_conflicts > 0
                  ? `${String(data.allocation.allocation_conflicts)} over-allocated`
                  : 'No over-allocations'
              }
            />
          </div>

          <div className="grid gap-6 lg:grid-cols-3">
            <Card className="lg:col-span-1">
              <CardHeader className="pb-3">
                <CardTitle className="text-base">Headcount by project</CardTitle>
              </CardHeader>
              <CardContent>
                {data.allocation.project_headcount.length === 0 ? (
                  <p className="text-muted-foreground text-sm">No live projects.</p>
                ) : (
                  <ul className="space-y-2">
                    {data.allocation.project_headcount.map((row) => (
                      <li key={row.project_id} className="flex items-center justify-between text-sm">
                        <span>{row.project}</span>
                        <span className="tabular-nums">{row.headcount}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </CardContent>
            </Card>

            <div className="lg:col-span-2">
              <DataTable
                rows={data.bench}
                columns={benchColumns}
                getRowId={(row) => row.employee_id}
                isLoading={q.isLoading}
                emptyTitle="Nobody on the bench"
                emptyDescription="Every active employee has a live allocation."
              />
            </div>
          </div>
        </>
      ) : (
        <p className="text-muted-foreground text-sm">Loading…</p>
      )}
    </div>
  );
}

export function HrPerformancePage(): React.JSX.Element {
  const q = useHrPerformance();
  if (q.error) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  const data = q.data;
  return (
    <div className="space-y-6">
      <PageHeader
        title="Performance Overview"
        description="Cycle progress and review completion across the organization."
      />
      {data ? (
        <>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <StatCard label="Active cycles" value={data.active_cycles} />
            <StatCard label="Goals assigned" value={data.goals_assigned} />
            <StatCard
              label="Completion"
              value={`${String(data.completion_percentage)}%`}
              hint="Reviews finalised against reviews due"
            />
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Self reviews pending" value={data.self_reviews_pending} />
            <StatCard label="Manager reviews pending" value={data.manager_reviews_pending} />
            <StatCard label="Final ratings" value={data.final_ratings} />
          </div>
        </>
      ) : (
        <p className="text-muted-foreground text-sm">Loading…</p>
      )}
    </div>
  );
}
export function HrReportsPage(): React.JSX.Element {
  const q = useHrResource('reports');
  const reports = (q.data ?? []) as Report[];
  const download = async (r: Report) => {
    try {
      const blob = await api.get<Blob>(`/hr/reports/${r.key}/export`, {
        params: { fmt: 'csv' },
        responseType: 'blob',
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${r.key}.csv`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error('The report could not be exported.');
    }
  };
  return (
    <div className="space-y-6">
      <PageHeader
        title="HR Reports"
        description="Availability and export are both enforced by backend permissions."
      />
      <div className="grid gap-4 md:grid-cols-2">
        {reports.map((r) => (
          <Card key={r.key}>
            <CardHeader>
              <CardTitle>{r.name}</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <p className="text-muted-foreground text-sm">{r.description}</p>
              <Button disabled={!r.available} onClick={() => void download(r)}>
                Export CSV
              </Button>
              {!r.available && (
                <p className="text-destructive text-xs">Requires: {r.required_permissions.join(', ')}</p>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}

export function HrRecruitmentPage(): React.JSX.Element {
  const router = useRouter();
  return (
    <div className="space-y-6">
      <PageHeader
        title="HR Recruitment"
        description="Recruitment retains its existing permission-scoped workflows."
      />
      <div className="grid gap-4 sm:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Recruitment workspace</CardTitle>
          </CardHeader>
          <CardContent>
            <Button onClick={() => router.push('/recruitment')}>Open recruitment</Button>
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Onboarding workspace</CardTitle>
          </CardHeader>
          <CardContent>
            <Button onClick={() => router.push('/onboarding')}>Open onboarding</Button>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

export function HrEmployeeProfilePage(): React.JSX.Element {
  const params = useParams<{ employeeId: string }>();
  const q = useHrEmployee(params.employeeId);
  if (q.error) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data) return <p>Loading…</p>;
  const profile = q.data;
  const e = profile.employee;

  const tabs = [
    { id: 'overview', label: 'Overview' },
    { id: 'attendance', label: 'Attendance' },
    { id: 'leave', label: 'Leave' },
    { id: 'timesheets', label: 'Timesheets' },
    { id: 'projects', label: 'Projects' },
    { id: 'performance', label: 'Performance' },
    { id: 'documents', label: 'Documents' },
    { id: 'activity', label: 'Activity' },
  ];

  const hours = (minutes: number): string => `${String(Math.floor(minutes / 60))}h ${String(minutes % 60)}m`;

  const projectColumns: DataTableColumn<HrProfile['projects'][number]>[] = [
    {
      id: 'project',
      header: 'Project',
      cell: (row) => (
        <div>
          <p className="font-medium">{row.project_name}</p>
          <p className="text-muted-foreground text-xs">
            {row.project_code}
            {row.client_name ? ` · ${row.client_name}` : ''}
          </p>
        </div>
      ),
    },
    {
      id: 'allocation',
      header: 'Allocation',
      align: 'right',
      cell: (row) => <span className="tabular-nums">{row.allocation_percentage}%</span>,
    },
    {
      id: 'billable',
      header: 'Billable',
      cell: (row) => (row.billable ? <Badge>Billable</Badge> : <Badge variant="outline">Internal</Badge>),
    },
    {
      id: 'window',
      header: 'Period',
      cell: (row) =>
        `${new Date(row.start_date).toLocaleDateString()} — ${
          row.end_date ? new Date(row.end_date).toLocaleDateString() : 'open'
        }`,
    },
  ];

  const documentColumns: DataTableColumn<HrProfile['documents'][number]>[] = [
    {
      id: 'name',
      header: 'Document',
      cell: (row) => (
        <div>
          <p className="font-medium">{row.name}</p>
          <p className="text-muted-foreground text-xs">{row.document_code}</p>
        </div>
      ),
    },
    { id: 'status', header: 'Status', cell: (row) => <Badge variant="secondary">{row.status}</Badge> },
    {
      id: 'expiry',
      header: 'Expires',
      cell: (row) => (row.expiry_date ? new Date(row.expiry_date).toLocaleDateString() : '—'),
    },
  ];

  const content = (tab: string): React.ReactNode => {
    if (tab === 'overview') {
      return (
        <Card>
          <CardContent className="pt-6">
            <DetailSection
              title="Identity"
              items={[
                { label: 'Employee code', value: e.employee_code },
                { label: 'Name', value: e.full_name },
                { label: 'Official email', value: e.official_email },
                { label: 'Mobile', value: e.official_mobile ?? e.mobile_number ?? '—' },
              ]}
            />
            <div className="mt-6">
              <DetailSection
                title="Employment"
                items={[
                  { label: 'Designation', value: e.designation?.name ?? '—' },
                  { label: 'Business unit', value: e.business_unit?.name ?? '—' },
                  { label: 'Team', value: e.team?.name ?? '—' },
                  { label: 'Location', value: e.work_location?.name ?? '—' },
                  { label: 'Manager', value: e.reporting_manager?.full_name ?? '—' },
                  { label: 'Joined', value: e.joining_date ?? '—' },
                  { label: 'Employment type', value: e.employment_type?.name ?? '—' },
                  { label: 'Status', value: <Badge variant="secondary">{e.employment_status}</Badge> },
                ]}
              />
            </div>
          </CardContent>
        </Card>
      );
    }
    if (tab === 'attendance') {
      const a = profile.attendance;
      return (
        <div className="space-y-4">
          <p className="text-muted-foreground text-sm">
            {new Date(a.from_date).toLocaleDateString()} to {new Date(a.to_date).toLocaleDateString()} — the
            current month.
          </p>
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Present" value={a.present_days} />
            <StatCard label="Absent" value={a.absent_days} />
            <StatCard label="On leave" value={a.leave_days} hint={`${String(a.half_days)} half days`} />
            <StatCard label="Late arrivals" value={a.late_arrivals} />
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <StatCard label="Hours worked" value={hours(a.worked_minutes)} />
            <StatCard label="Overtime" value={hours(a.overtime_minutes)} />
          </div>
        </div>
      );
    }
    if (tab === 'leave') {
      return (
        <DataTable
          rows={profile.leave}
          columns={[
            { id: 'type', header: 'Leave type', cell: (row) => row.leave_type_name },
            { id: 'year', header: 'Year', cell: (row) => row.year },
            { id: 'allocated', header: 'Allocated', align: 'right', cell: (row) => row.allocated },
            { id: 'used', header: 'Used', align: 'right', cell: (row) => row.used },
            { id: 'pending', header: 'Pending', align: 'right', cell: (row) => row.pending },
            {
              id: 'available',
              header: 'Available',
              align: 'right',
              cell: (row) => <span className="font-medium tabular-nums">{row.available}</span>,
            },
          ]}
          getRowId={(row) => `${row.leave_type_id}-${String(row.year)}`}
          emptyTitle="No balances"
          emptyDescription="Balances appear once a leave policy applies to this employee."
        />
      );
    }
    if (tab === 'timesheets') {
      const t = profile.timesheets;
      return (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <StatCard label="Draft" value={t.draft} />
          <StatCard label="Submitted" value={t.submitted} hint="Waiting on a decision" />
          <StatCard label="Approved" value={t.approved} hint={`${String(t.rejected)} rejected`} />
          <StatCard label="Total hours" value={t.total_hours} />
          <StatCard label="Billable hours" value={t.billable_hours} />
        </div>
      );
    }
    if (tab === 'projects') {
      return (
        <DataTable
          rows={profile.projects}
          columns={projectColumns}
          getRowId={(row) => row.project_id}
          emptyTitle="No allocations"
          emptyDescription="This employee is not allocated to any project."
        />
      );
    }
    if (tab === 'performance') {
      const perf = profile.performance;
      if (!perf) {
        return (
          <Card>
            <CardContent className="pt-6">
              <p className="text-muted-foreground text-sm">Not part of any performance cycle yet.</p>
            </CardContent>
          </Card>
        );
      }
      return (
        <div className="space-y-4">
          {perf.cycle_name ? (
            <p className="text-muted-foreground text-sm">Current cycle: {perf.cycle_name}</p>
          ) : null}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <StatCard label="Goals" value={perf.goals} hint={`${String(perf.goals_completed)} completed`} />
            <StatCard label="Goal progress" value={`${String(perf.goal_progress)}%`} />
            <StatCard label="Self review" value={perf.self_review_status ?? 'Not started'} />
            <StatCard label="Manager review" value={perf.manager_review_status ?? 'Not started'} />
          </div>
          {perf.current_rating !== null ? (
            <StatCard label="Current rating" value={perf.current_rating} className="max-w-xs" />
          ) : null}
        </div>
      );
    }
    if (tab === 'documents') {
      return (
        <DataTable
          rows={profile.documents}
          columns={documentColumns}
          getRowId={(row) => row.id}
          emptyTitle="No documents"
          emptyDescription="Nothing has been uploaded for this employee."
        />
      );
    }
    if (!profile.can_read_activity) {
      return (
        <Card>
          <CardContent className="pt-6">
            <p className="text-muted-foreground text-sm">
              Reading the activity trail requires the audit permission, which your role does not hold.
            </p>
          </CardContent>
        </Card>
      );
    }
    return (
      <Card>
        <CardContent className="pt-6">
          <Timeline
            items={profile.activity.map((entry) => ({
              id: entry.id,
              title: entry.action,
              description: entry.description ?? undefined,
              meta: entry.actor_email ?? undefined,
              timestamp: new Date(entry.created_at).toLocaleString(),
            }))}
          />
        </CardContent>
      </Card>
    );
  };

  return (
    <div className="space-y-6">
      <PageHeader title={e.full_name} description={`${e.employee_code} · HR employee profile`} />
      <Tabs tabs={tabs} label="Employee profile" defaultTabId="overview">
        {content}
      </Tabs>
    </div>
  );
}
