'use client';

import { useRouter } from 'next/navigation';
import * as React from 'react';

import { DataTable, type DataTableColumn } from '@/components/common/data-table';
import { PageHeader } from '@/components/common/page-header';
import { Pagination } from '@/components/common/pagination';
import { SearchBar } from '@/components/common/search-bar';
import { Badge } from '@/components/ui/badge';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { routes } from '@/config/site';
import { TeamAttendanceBadge, TeamMemberCell } from '@/features/manager/components/widgets';
import { useTeam, useTeamProjects } from '@/features/manager/hooks';
import { EMPLOYMENT_STATUS_LABELS, type TeamMember } from '@/features/manager/types';
import { useMasterOptions } from '@/features/organization/hooks/use-masters';
import type { MasterSlug } from '@/features/organization/types/organization.types';

/**
 * My Team.
 *
 * Every filter is sent to the server and applied *inside* the reporting line.
 * Nothing is filtered in the browser, which is why searching for somebody on
 * another manager's team returns an empty table rather than a row that has been
 * hidden — the row was never fetched.
 *
 * "Practice" and "Department" are not columns on this platform: migration 0012
 * removed both levels of the hierarchy, leaving Business Unit → Team. Those are
 * the two shown here.
 */

const EMPLOYMENT_STATUSES = [
  'probation',
  'confirmed',
  'active',
  'notice_period',
  'resigned',
  'inactive',
] as const;

/** One master-backed picker in the filter row. */
function MasterFilter({
  label,
  master,
  value,
  onChange,
}: {
  label: string;
  master: MasterSlug;
  value: string;
  onChange: (value: string) => void;
}): React.JSX.Element {
  const query = useMasterOptions(master);

  return (
    <Select
      onValueChange={(next) => {
        onChange(next === 'all' ? '' : next);
      }}
      value={value === '' ? 'all' : value}
    >
      <SelectTrigger aria-label={label} className="w-full sm:w-44">
        <SelectValue placeholder={label} />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="all">All {label.toLowerCase()}</SelectItem>
        {(query.data?.items ?? []).map((record) => (
          <SelectItem key={record.id} value={record.id}>
            {record.name}
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  );
}

export function TeamPage(): React.JSX.Element {
  const router = useRouter();

  const [page, setPage] = React.useState(1);
  const [search, setSearch] = React.useState('');
  const [businessUnit, setBusinessUnit] = React.useState('');
  const [team, setTeam] = React.useState('');
  const [location, setLocation] = React.useState('');
  const [project, setProject] = React.useState('');
  const [status, setStatus] = React.useState('');

  // The project picker is built from the team's own allocations rather than the
  // project master: offering a project nobody on this team is on would produce
  // a filter that can only ever return nothing.
  const projects = useTeamProjects();

  const params = React.useMemo(
    () => ({
      page,
      page_size: 20,
      ...(search ? { search } : {}),
      ...(businessUnit ? { business_unit_id: businessUnit } : {}),
      ...(team ? { team_id: team } : {}),
      ...(location ? { work_location_id: location } : {}),
      ...(project ? { project_id: project } : {}),
      ...(status ? { employment_status: status } : {}),
    }),
    [page, search, businessUnit, team, location, project, status],
  );

  const roster = useTeam(params);

  const reset =
    <T,>(setter: (value: T) => void) =>
    (value: T) => {
      setter(value);
      setPage(1);
    };

  const columns: DataTableColumn<TeamMember>[] = [
    {
      id: 'employee',
      header: 'Employee',
      cell: (row) => <TeamMemberCell employee={row} />,
    },
    { id: 'designation', header: 'Designation', cell: (row) => row.designation?.name ?? '—' },
    { id: 'business_unit', header: 'Business unit', cell: (row) => row.business_unit?.name ?? '—' },
    { id: 'team', header: 'Team', cell: (row) => row.team?.name ?? '—' },
    { id: 'location', header: 'Location', cell: (row) => row.work_location?.name ?? '—' },
    { id: 'employment_type', header: 'Employment', cell: (row) => row.employment_type?.name ?? '—' },
    {
      id: 'project',
      header: 'Project',
      cell: (row) =>
        row.allocations.length === 0 ? (
          <span className="text-muted-foreground">Bench</span>
        ) : (
          <div className="space-y-0.5">
            {row.allocations.map((allocation) => (
              <p className="truncate text-sm" key={allocation.project_id}>
                {allocation.project_name}
              </p>
            ))}
          </div>
        ),
    },
    {
      id: 'allocation',
      header: 'Allocation',
      align: 'right',
      cell: (row) =>
        row.allocations.length === 0 ? (
          '—'
        ) : (
          <Badge variant={Number(row.allocated_percentage) > 100 ? 'destructive' : 'outline'}>
            {row.allocated_percentage}%
          </Badge>
        ),
    },
    {
      id: 'attendance',
      header: 'Today',
      cell: (row) => <TeamAttendanceBadge status={row.attendance_status} />,
    },
    {
      id: 'leave',
      header: 'Leave',
      cell: (row) =>
        row.on_leave_type ? (
          <Badge variant="secondary">{row.on_leave_type}</Badge>
        ) : (
          <span className="text-muted-foreground">—</span>
        ),
    },
    {
      id: 'status',
      header: 'Status',
      cell: (row) => <Badge variant="outline">{EMPLOYMENT_STATUS_LABELS[row.employment_status]}</Badge>,
    },
  ];

  return (
    <div className="space-y-6">
      <PageHeader
        title="My Team"
        description="Your direct reports, with where they are today and what they are allocated to."
      />

      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
        <SearchBar
          className="sm:w-64"
          label="Search your team"
          onChange={reset(setSearch)}
          placeholder="Name, staff code or email…"
          value={search}
        />
        <MasterFilter
          label="Business unit"
          master="business-units"
          onChange={reset(setBusinessUnit)}
          value={businessUnit}
        />
        <MasterFilter label="Team" master="teams" onChange={reset(setTeam)} value={team} />
        <MasterFilter label="Location" master="locations" onChange={reset(setLocation)} value={location} />

        <Select
          onValueChange={(next) => {
            reset(setProject)(next === 'all' ? '' : next);
          }}
          value={project === '' ? 'all' : project}
        >
          <SelectTrigger aria-label="Project" className="w-full sm:w-44">
            <SelectValue placeholder="Project" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All projects</SelectItem>
            {(projects.data ?? []).map((row) => (
              <SelectItem key={row.project_id} value={row.project_id}>
                {row.project_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          onValueChange={(next) => {
            reset(setStatus)(next === 'all' ? '' : next);
          }}
          value={status === '' ? 'all' : status}
        >
          <SelectTrigger aria-label="Employment status" className="w-full sm:w-44">
            <SelectValue placeholder="Status" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">All statuses</SelectItem>
            {EMPLOYMENT_STATUSES.map((value) => (
              <SelectItem key={value} value={value}>
                {EMPLOYMENT_STATUS_LABELS[value]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      <DataTable
        caption="Direct reports"
        columns={columns}
        emptyDescription="Nobody on your team matches these filters."
        emptyTitle="No team members"
        error={roster.error}
        getRowId={(row) => row.id}
        isLoading={roster.isPending}
        onRetry={() => void roster.refetch()}
        onRowClick={(row) => {
          router.push(`${routes.managerTeam}/${row.id}`);
        }}
        rows={roster.data?.items ?? []}
      />

      {roster.data ? (
        <Pagination itemLabel="team members" meta={roster.data.meta} onPageChange={setPage} />
      ) : null}
    </div>
  );
}
