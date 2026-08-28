'use client';

import { useRouter } from 'next/navigation';
import * as React from 'react';
import type { FieldValues } from 'react-hook-form';

import { ErrorState } from '@/components/common/error-state';
import { FormSkeleton } from '@/components/common/loading-state';
import { PageHeader } from '@/components/common/page-header';
import { EmployeeForm } from '@/features/employees/components/employee-form';
import { useCreateEmployee, useEmployee, useUpdateEmployee } from '@/features/employees/hooks/use-employees';
import type { EmployeeRecord } from '@/features/employees/types/employee.types';

const BASE_PATH = '/employees';

export function EmployeeCreatePage(): React.JSX.Element {
  const router = useRouter();
  const create = useCreateEmployee();

  return (
    <div className="space-y-6">
      <PageHeader
        title="New employee"
        description="Record a person the organization employs. The employee ID is generated automatically."
      />

      <EmployeeForm
        isSubmitting={create.isPending}
        error={create.error}
        cancelHref={BASE_PATH}
        onSubmit={(values: FieldValues) => {
          create.mutate(values, {
            onSuccess: (employee: EmployeeRecord) => {
              router.push(`${BASE_PATH}/${employee.id}`);
            },
          });
        }}
      />
    </div>
  );
}

interface EmployeeEditPageProps {
  employeeId: string;
}

export function EmployeeEditPage({ employeeId }: EmployeeEditPageProps): React.JSX.Element {
  const router = useRouter();

  const employeeQuery = useEmployee(employeeId);
  const update = useUpdateEmployee(employeeId);

  if (employeeQuery.isPending) return <FormSkeleton fields={8} />;
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

  return (
    <div className="space-y-6">
      <PageHeader
        title={`Edit ${employee.full_name}`}
        description={`${employee.employee_code} · changing the placement records an employment-history entry.`}
      />

      <EmployeeForm
        employee={employee}
        isSubmitting={update.isPending}
        error={update.error}
        cancelHref={`${BASE_PATH}/${employee.id}`}
        onSubmit={(values: FieldValues) => {
          update.mutate(values, {
            onSuccess: () => {
              router.push(`${BASE_PATH}/${employee.id}`);
            },
          });
        }}
      />
    </div>
  );
}
