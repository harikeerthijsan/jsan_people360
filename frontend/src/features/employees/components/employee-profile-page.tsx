'use client';

import { ArrowLeft, ArrowRightLeft, BadgeCheck, Pencil, TrendingUp, UserCog } from 'lucide-react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import * as React from 'react';

import { DetailSection, type DetailItem } from '@/components/common/detail-view';
import { EmploymentStatusBadge } from '@/components/common/employment-status-badge';
import { ErrorState } from '@/components/common/error-state';
import { LoadingState } from '@/components/common/loading-state';
import { MaskedValue } from '@/components/common/masked-value';
import { PageHeader } from '@/components/common/page-header';
import { ProfileCard } from '@/components/common/profile-card';
import { Tabs, type TabDefinition } from '@/components/common/tabs';
import { Timeline, type TimelineItem } from '@/components/common/timeline';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { LifecycleDialogs, type LifecycleKind } from '@/features/employees/components/lifecycle-dialogs';
import {
  useEmployee,
  useEmployeeSensitive,
  useEmploymentHistory,
  useEmployeeAudit,
} from '@/features/employees/hooks/use-employees';
import {
  CHANGE_TYPE_LABELS,
  EMPLOYMENT_STATUS_LABELS,
  MARITAL_STATUS_LABELS,
  WORK_MODE_LABELS,
  type EmployeeRecord,
  type EmploymentHistoryEntry,
} from '@/features/employees/types/employee.types';
import { GENDER_LABELS } from '@/types/user';
import { formatDate, formatDateTime } from '@/lib/utils';

const BASE_PATH = '/employees';

const TABS: TabDefinition[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'personal', label: 'Personal' },
  { id: 'employment', label: 'Employment' },
  { id: 'organization', label: 'Organization' },
  { id: 'bank', label: 'Bank' },
  { id: 'identifiers', label: 'Government IDs' },
  { id: 'history', label: 'Employment history' },
  { id: 'audit', label: 'Audit history' },
];

/** Format an amount without pretending to know the currency's minor units. */
function formatAmount(value: string | null): string | null {
  if (value === null) return null;
  const parsed = Number(value);
  return Number.isNaN(parsed) ? value : parsed.toLocaleString('en-IN');
}

interface EmployeeProfilePageProps {
  employeeId: string;
}

export function EmployeeProfilePage({ employeeId }: EmployeeProfilePageProps): React.JSX.Element {
  const router = useRouter();

  const employeeQuery = useEmployee(employeeId);
  const [lifecycle, setLifecycle] = React.useState<LifecycleKind | null>(null);

  if (employeeQuery.isPending) return <LoadingState message="Loading employee" />;
  if (employeeQuery.error) {
    return (
      <ErrorState
        error={employeeQuery.error}
        onRetry={() => {
          void employeeQuery.refetch();
        }}
      />
    );
  }

  const employee = employeeQuery.data;
  const isArchived = employee.deleted_at !== null;

  return (
    <div className="space-y-6">
      <PageHeader
        title={employee.full_name}
        description="Employee"
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="outline"
              onClick={() => {
                router.push(BASE_PATH);
              }}
            >
              <ArrowLeft aria-hidden="true" />
              Back
            </Button>

            {isArchived ? null : (
              <>
                {employee.employment_status === 'probation' ? (
                  <Button
                    variant="outline"
                    onClick={() => {
                      setLifecycle('confirm');
                    }}
                  >
                    <BadgeCheck aria-hidden="true" />
                    Confirm
                  </Button>
                ) : null}

                <Button
                  variant="outline"
                  onClick={() => {
                    setLifecycle('transfer');
                  }}
                >
                  <ArrowRightLeft aria-hidden="true" />
                  Transfer
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setLifecycle('promote');
                  }}
                >
                  <TrendingUp aria-hidden="true" />
                  Promote
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setLifecycle('manager');
                  }}
                >
                  <UserCog aria-hidden="true" />
                  Manager
                </Button>

                <Button asChild>
                  <Link href={`${BASE_PATH}/${employee.id}/edit`}>
                    <Pencil aria-hidden="true" />
                    Edit
                  </Link>
                </Button>
              </>
            )}
          </div>
        }
      />

      <ProfileCard
        name={employee.full_name}
        subtitle={employee.official_email}
        photoUrl={employee.photo_url}
        badges={
          <>
            <EmploymentStatusBadge status={employee.employment_status} archived={isArchived} />
            <Badge variant="outline" className="font-mono text-xs">
              {employee.employee_code}
            </Badge>
          </>
        }
        facts={[
          { label: 'Team', value: employee.organization.team?.name ?? '—' },
          { label: 'Designation', value: employee.organization.designation?.name ?? '—' },
          { label: 'Joined', value: formatDate(employee.joining_date) },
          { label: 'Manager', value: employee.reporting_manager?.full_name ?? '—' },
        ]}
      />

      <Tabs tabs={TABS} label="Employee profile sections" defaultTabId="overview">
        {(activeTab) => <ProfileTab tab={activeTab} employee={employee} />}
      </Tabs>

      <LifecycleDialogs
        employee={employee}
        openKind={lifecycle}
        onClose={() => {
          setLifecycle(null);
        }}
      />
    </div>
  );
}

function ProfileTab({ tab, employee }: { tab: string; employee: EmployeeRecord }): React.JSX.Element {
  switch (tab) {
    case 'personal':
      return <PersonalTab employee={employee} />;
    case 'employment':
      return <EmploymentTab employee={employee} />;
    case 'organization':
      return <OrganizationTab employee={employee} />;
    case 'bank':
      return <BankTab employee={employee} />;
    case 'identifiers':
      return <IdentifiersTab employee={employee} />;
    case 'history':
      return <HistoryTab employeeId={employee.id} />;
    case 'audit':
      return <AuditTab employeeId={employee.id} />;
    default:
      return <OverviewTab employee={employee} />;
  }
}

// ---------------------------------------------------------------------------
function OverviewTab({ employee }: { employee: EmployeeRecord }): React.JSX.Element {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <DetailSection
        title="At a glance"
        items={[
          {
            label: 'Employee ID',
            value: <span className="font-mono text-xs">{employee.employee_code}</span>,
          },
          { label: 'Status', value: EMPLOYMENT_STATUS_LABELS[employee.employment_status] },
          { label: 'Official email', value: employee.official_email },
          { label: 'Mobile', value: employee.mobile_number },
          { label: 'Work mode', value: employee.work_mode ? WORK_MODE_LABELS[employee.work_mode] : null },
          { label: 'Joining date', value: formatDate(employee.joining_date) },
          {
            label: 'Confirmation date',
            value: employee.confirmation_date ? formatDate(employee.confirmation_date) : null,
          },
          { label: 'Reporting manager', value: employee.reporting_manager?.full_name },
        ]}
      />
      <DetailSection
        title="Placement"
        items={[
          { label: 'Business unit', value: employee.organization.business_unit?.name },
          { label: 'Team', value: employee.organization.team?.name },
          { label: 'Designation', value: employee.organization.designation?.name },
          { label: 'Grade', value: employee.organization.grade?.name },
          { label: 'Work location', value: employee.organization.work_location?.name },
          { label: 'Employment type', value: employee.organization.employment_type?.name },
        ]}
      />
    </div>
  );
}

function PersonalTab({ employee }: { employee: EmployeeRecord }): React.JSX.Element {
  const current = employee.addresses.find((address) => address.address_type === 'current');
  const permanent = employee.addresses.find((address) => address.address_type === 'permanent');

  const addressLine = (address: typeof current): string | null => {
    if (!address) return null;
    return [
      address.address_line1,
      address.address_line2,
      address.landmark,
      address.city,
      address.state,
      address.country,
      address.postal_code,
    ]
      .filter(Boolean)
      .join(', ');
  };

  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <DetailSection
        title="Personal information"
        items={[
          { label: 'First name', value: employee.first_name },
          { label: 'Last name', value: employee.last_name },
          { label: 'Gender', value: employee.gender ? GENDER_LABELS[employee.gender] : null },
          {
            label: 'Date of birth',
            value: employee.date_of_birth ? formatDate(employee.date_of_birth) : null,
          },
          { label: 'Blood group', value: employee.blood_group },
          {
            label: 'Marital status',
            value: employee.marital_status ? MARITAL_STATUS_LABELS[employee.marital_status] : null,
          },
          { label: 'Nationality', value: employee.nationality },
        ]}
      />
      <DetailSection
        title="Contact"
        items={[
          { label: 'Personal email', value: employee.personal_email },
          { label: 'Mobile number', value: employee.mobile_number },
          { label: 'Alternate number', value: employee.alternate_number },
          { label: 'Emergency contact', value: employee.emergency_contact_name },
          { label: 'Emergency number', value: employee.emergency_contact_number },
          { label: 'Relationship', value: employee.emergency_contact_relationship },
        ]}
      />
      <DetailSection
        className="lg:col-span-2"
        title="Address"
        items={[
          { label: 'Current address', value: addressLine(current), wide: true },
          { label: 'Permanent address', value: addressLine(permanent), wide: true },
        ]}
      />
    </div>
  );
}

function EmploymentTab({ employee }: { employee: EmployeeRecord }): React.JSX.Element {
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <DetailSection
        title="Employment"
        items={[
          {
            label: 'Employee ID',
            value: <span className="font-mono text-xs">{employee.employee_code}</span>,
          },
          { label: 'Joining date', value: formatDate(employee.joining_date) },
          {
            label: 'Confirmation date',
            value: employee.confirmation_date ? formatDate(employee.confirmation_date) : null,
          },
          { label: 'Status', value: EMPLOYMENT_STATUS_LABELS[employee.employment_status] },
          { label: 'Employment type', value: employee.organization.employment_type?.name },
          { label: 'Reporting manager', value: employee.reporting_manager?.full_name },
        ]}
      />
      <DetailSection
        title="Official"
        items={[
          { label: 'Official email', value: employee.official_email },
          { label: 'Official mobile', value: employee.official_mobile },
          { label: 'Extension', value: employee.extension_number },
          { label: 'Work mode', value: employee.work_mode ? WORK_MODE_LABELS[employee.work_mode] : null },
          { label: 'Work location', value: employee.organization.work_location?.name },
        ]}
      />
      <DetailSection
        title="Compensation"
        items={[
          { label: 'CTC', value: formatAmount(employee.ctc) },
          { label: 'Salary grade', value: employee.organization.salary_grade?.name },
        ]}
      />
      <DetailSection
        title="Record"
        items={[
          { label: 'Linked account', value: employee.user?.username },
          { label: 'Created', value: formatDateTime(employee.created_at) },
          { label: 'Last updated', value: formatDateTime(employee.updated_at) },
          { label: 'Notes', value: employee.notes, wide: true },
        ]}
      />
    </div>
  );
}

function OrganizationTab({ employee }: { employee: EmployeeRecord }): React.JSX.Element {
  const { organization } = employee;

  return (
    <div className="space-y-6">
      <DetailSection
        title="Organizational placement"
        items={[
          { label: 'Business unit', value: organization.business_unit?.name },
          { label: 'Team', value: organization.team?.name },
          { label: 'Designation', value: organization.designation?.name },
          { label: 'Grade', value: organization.grade?.name },
          { label: 'Work location', value: organization.work_location?.name },
          { label: 'Employment type', value: organization.employment_type?.name },
        ]}
      />

      {employee.reporting_manager ? (
        <Card>
          <CardContent className="p-6">
            <p className="text-muted-foreground mb-3 text-xs font-medium tracking-wide uppercase">
              Reports to
            </p>
            <Link
              href={`${BASE_PATH}/${employee.reporting_manager.id}`}
              className="hover:text-primary font-medium"
            >
              {employee.reporting_manager.full_name}
            </Link>
            <p className="text-muted-foreground font-mono text-xs">
              {employee.reporting_manager.employee_code}
            </p>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------
function BankTab({ employee }: { employee: EmployeeRecord }): React.JSX.Element {
  const [revealed, setRevealed] = React.useState(false);
  const sensitive = useEmployeeSensitive(employee.id, revealed);
  const bank = employee.bank_detail;

  if (!bank) {
    return (
      <Card>
        <CardContent className="text-muted-foreground p-6 text-sm">
          No bank details recorded for this employee.
        </CardContent>
      </Card>
    );
  }

  const items: DetailItem[] = [
    { label: 'Bank name', value: bank.bank_name },
    { label: 'Branch', value: bank.branch_name },
    { label: 'Account holder', value: bank.account_holder_name },
    { label: 'IFSC', value: <span className="font-mono text-sm">{bank.ifsc_code}</span> },
    {
      label: 'Account number',
      value: (
        <MaskedValue
          label="account number"
          masked={bank.account_number}
          revealed={sensitive.data?.bank_detail?.account_number ?? null}
          isRevealed={revealed}
          isLoading={sensitive.isFetching}
          onToggle={() => {
            setRevealed((previous) => !previous);
          }}
        />
      ),
    },
  ];

  return (
    <div className="space-y-4">
      <DetailSection title="Bank details" items={items} />
      <p className="text-muted-foreground text-xs">
        Revealing the account number is recorded in the audit trail.
      </p>
    </div>
  );
}

function IdentifiersTab({ employee }: { employee: EmployeeRecord }): React.JSX.Element {
  const [revealed, setRevealed] = React.useState(false);
  const sensitive = useEmployeeSensitive(employee.id, revealed);
  const identification = employee.identification;

  if (!identification) {
    return (
      <Card>
        <CardContent className="text-muted-foreground p-6 text-sm">
          No government identifiers recorded for this employee.
        </CardContent>
      </Card>
    );
  }

  const full = sensitive.data?.identification;
  const toggle = () => {
    setRevealed((previous) => !previous);
  };

  /** The masked fields share one reveal, so one decision uncovers one screen. */
  const masked = (
    label: string,
    maskedValue: string | null,
    revealedValue: string | null | undefined,
  ): DetailItem => ({
    label,
    value: (
      <MaskedValue
        label={label.toLowerCase()}
        masked={maskedValue}
        revealed={revealedValue ?? null}
        isRevealed={revealed}
        isLoading={sensitive.isFetching}
        onToggle={toggle}
      />
    ),
  });

  return (
    <div className="space-y-4">
      <DetailSection
        title="Government identifiers"
        items={[
          masked('Aadhaar', identification.aadhaar_number, full?.aadhaar_number),
          masked('PAN', identification.pan_number, full?.pan_number),
          masked('Passport', identification.passport_number, full?.passport_number),
          masked('Driving licence', identification.driving_license_number, full?.driving_license_number),
          { label: 'Passport expiry', value: identification.passport_expiry },
          { label: 'UAN', value: identification.uan_number },
          { label: 'PF number', value: identification.pf_number },
          { label: 'ESI number', value: identification.esi_number },
        ]}
      />
      <p className="text-muted-foreground text-xs">
        Revealing these values is recorded in the audit trail. UAN, PF and ESI numbers are employer-side
        references and are shown in full.
      </p>
    </div>
  );
}

// ---------------------------------------------------------------------------
function HistoryTab({ employeeId }: { employeeId: string }): React.JSX.Element {
  const history = useEmploymentHistory(employeeId);

  if (history.isPending) return <LoadingState message="Loading employment history" />;
  if (history.error) {
    return (
      <ErrorState
        error={history.error}
        onRetry={() => {
          void history.refetch();
        }}
      />
    );
  }

  if (history.data.length === 0) {
    return (
      <Card>
        <CardContent className="text-muted-foreground p-6 text-sm">
          No employment history recorded yet.
        </CardContent>
      </Card>
    );
  }

  const items: TimelineItem[] = history.data.map((entry: EmploymentHistoryEntry) => ({
    id: entry.id,
    title: CHANGE_TYPE_LABELS[entry.change_type],
    timestamp: formatDate(entry.effective_date),
    description: entry.summary,
    // Promotions and confirmations are the entries a reader scans for.
    highlighted: entry.change_type === 'promotion' || entry.change_type === 'confirmation',
    meta: (
      <div className="space-y-1">
        {entry.reason ? <p>Reason: {entry.reason}</p> : null}
        {entry.notes ? <p>{entry.notes}</p> : null}
        <p className="text-muted-foreground/70">Recorded {formatDateTime(entry.created_at)}</p>
      </div>
    ),
  }));

  return (
    <Card>
      <CardContent className="p-6">
        <Timeline items={items} />
      </CardContent>
    </Card>
  );
}

function AuditTab({ employeeId }: { employeeId: string }): React.JSX.Element {
  const audit = useEmployeeAudit(employeeId);

  if (audit.isPending) return <LoadingState message="Loading audit history" />;
  if (audit.error) {
    return (
      <ErrorState
        error={audit.error}
        onRetry={() => {
          void audit.refetch();
        }}
      />
    );
  }

  if (audit.data.length === 0) {
    return (
      <Card>
        <CardContent className="text-muted-foreground p-6 text-sm">
          Nothing recorded against this employee yet.
        </CardContent>
      </Card>
    );
  }

  const items: TimelineItem[] = audit.data.map((entry) => ({
    id: entry.id,
    title: <span className="font-mono text-xs">{entry.action}</span>,
    timestamp: formatDateTime(entry.created_at),
    description: entry.description,
    meta: entry.actor_email ? <p>By {entry.actor_email}</p> : null,
    highlighted: entry.action === 'employee.sensitive.viewed',
  }));

  return (
    <Card>
      <CardContent className="p-6">
        <Timeline items={items} />
      </CardContent>
    </Card>
  );
}
