'use client';

import * as React from 'react';

import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { useEmployeeList } from '@/features/employees/hooks/use-employees';
import type { EmploymentStatus } from '@/features/employees/types/employee.types';

/** People who have left. Everyone else still has attendance, leave and hours. */
const EX_EMPLOYEE_STATUSES = new Set<EmploymentStatus>(['resigned', 'inactive']);

/**
 * Whose record is being looked at.
 *
 * Most workforce screens are "one employee, one period", and every one of them
 * needs the same control. Until roles exist there is no signed-in employee to
 * default to, so the choice is explicit rather than guessed -- a guess here
 * would silently show one person's attendance under another person's name.
 */
export function useEmployeeOptions(): {
  options: { value: string; label: string }[];
  isPending: boolean;
} {
  const query = useEmployeeList({
    page: 1,
    page_size: 100,
    archived: false,
    sort_by: 'first_name',
    sort_order: 'asc',
  });

  const options = React.useMemo(
    () =>
      (query.data?.items ?? [])
        // Not filtered to `active`: a probationer marks attendance, a confirmed
        // employee applies for leave, and somebody on notice still fills in a
        // timesheet. Only the two statuses that mean "no longer working here"
        // are left out.
        .filter((employee) => !EX_EMPLOYEE_STATUSES.has(employee.employment_status))
        .map((employee) => ({
          value: employee.id,
          label: `${employee.employee_code} · ${employee.full_name}`,
        })),
    [query.data],
  );

  return { options, isPending: query.isPending };
}

interface EmployeePickerProps {
  value: string;
  onChange: (employeeId: string) => void;
  label?: string;
  id?: string;
}

export function EmployeePicker({
  value,
  onChange,
  label = 'Employee',
  id = 'workforce-employee',
}: EmployeePickerProps): React.JSX.Element {
  const { options, isPending } = useEmployeeOptions();

  return (
    <div className="w-full max-w-sm space-y-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Select disabled={isPending} onValueChange={onChange} value={value}>
        <SelectTrigger id={id}>
          <SelectValue placeholder={isPending ? 'Loading employees…' : 'Choose an employee'} />
        </SelectTrigger>
        <SelectContent>
          {options.map((option) => (
            <SelectItem key={option.value} value={option.value}>
              {option.label}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
