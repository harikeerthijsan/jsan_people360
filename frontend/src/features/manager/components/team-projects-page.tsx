'use client';

import { Users2 } from 'lucide-react';
import * as React from 'react';

import { EmptyState } from '@/components/common/empty-state';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { TeamMemberCell, formatDay } from '@/features/manager/components/widgets';
import { useTeamProjects } from '@/features/manager/hooks';

/**
 * Team Projects.
 *
 * Projects the manager's own people are on today, with each person's share.
 * "Team size" counts this team's members, not everybody on the project: the
 * screen answers "where is my team working", and a figure that included other
 * teams' people would be read as though it did not.
 *
 * Read-only. Moving somebody between projects is a Project Allocation action
 * and needs `projects:update` there; this module has no endpoint that writes an
 * allocation at all.
 */
export function TeamProjectsPage(): React.JSX.Element {
  const projects = useTeamProjects();

  if (projects.isPending) return <LoadingState message="Loading your team's projects…" />;
  if (projects.error) {
    return <ErrorState error={projects.error} onRetry={() => void projects.refetch()} />;
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Team Projects"
        description="Where your direct reports are allocated today. Read-only: allocation is changed in Projects."
      />

      {projects.data.length === 0 ? (
        <EmptyState
          description="Nobody on your team has a live allocation today."
          icon={Users2}
          title="No projects"
        />
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          {projects.data.map((project) => (
            <Card key={project.project_id}>
              <CardHeader className="pb-3">
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <CardTitle className="truncate text-base">{project.project_name}</CardTitle>
                    <CardDescription className="truncate">
                      {project.client_name ?? 'No client recorded'} · {project.project_code}
                    </CardDescription>
                  </div>
                  <Badge variant="outline">{project.status}</Badge>
                </div>
              </CardHeader>

              <CardContent className="space-y-4">
                <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
                  <div>
                    <dt className="text-muted-foreground text-xs">My team on it</dt>
                    <dd className="font-medium tabular-nums">{project.team_size}</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground text-xs">Allocation</dt>
                    <dd className="font-medium tabular-nums">{project.total_allocation}%</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground text-xs">Billable</dt>
                    <dd className="font-medium tabular-nums">{project.billable_percentage}%</dd>
                  </div>
                  <div>
                    <dt className="text-muted-foreground text-xs">Dates</dt>
                    <dd className="font-medium tabular-nums">
                      {formatDay(project.start_date)}
                      {project.end_date ? ` → ${formatDay(project.end_date)}` : ' → open'}
                    </dd>
                  </div>
                </dl>

                <ul className="space-y-2 border-t pt-3">
                  {project.members.map((member) => (
                    <li className="flex items-center justify-between gap-3" key={member.employee.id}>
                      <TeamMemberCell
                        detail={member.billable ? 'Billable' : 'Non-billable'}
                        employee={member.employee}
                      />
                      <Badge variant="outline">{member.allocation_percentage}%</Badge>
                    </li>
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
