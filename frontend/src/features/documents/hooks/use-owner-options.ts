'use client';

import * as React from 'react';

import type { SelectOption } from '@/components/common/select-field';
import { OWNER_TYPE_LABELS, type DocumentOwnerType } from '@/features/documents/types/document.types';
import { useEmployeeList } from '@/features/employees/hooks/use-employees';
import { useMasterOptions } from '@/features/organization/hooks/use-masters';
import { useCandidates } from '@/features/recruitment/hooks';
import type { Candidate } from '@/features/recruitment/types';
import { useUserList } from '@/features/users/hooks/use-users';
import type { Page } from '@/lib/api/types';

/**
 * The choices for "who does this document belong to", for one owner type.
 *
 * The vault is polymorphic, so every screen that names an owner faces the same
 * problem: four different modules supply the candidates for the answer. Solving
 * it once here keeps the upload form and the list filter from drifting apart —
 * and stops either of them falling back to asking for a raw UUID.
 *
 * All four queries are declared and only the relevant one is enabled. Hooks
 * cannot be called conditionally, and branching before the call would break the
 * rules of hooks.
 */
export interface OwnerOptions {
  options: SelectOption[];
  isLoading: boolean;
  /** What to show when the list came back empty. */
  emptyMessage: string;
}

const LIST_QUERY = { page: 1, page_size: 100, archived: false, sort_order: 'asc' as const };

export function useOwnerOptions(ownerType: DocumentOwnerType | undefined): OwnerOptions {
  const employees = useEmployeeList({ ...LIST_QUERY, sort_by: 'first_name' });
  const users = useUserList({ ...LIST_QUERY, sort_by: 'first_name' });
  const candidates = useCandidates({ page: 1, page_size: 100, sort_by: 'first_name', sort_order: 'asc' });
  const organizations = useMasterOptions(ownerType === 'organization' ? 'organizations' : undefined);

  const options: SelectOption[] = React.useMemo(() => {
    switch (ownerType) {
      case 'employee':
        return (employees.data?.items ?? []).map((item) => ({
          value: item.id,
          label: item.full_name,
          hint: item.employee_code,
        }));
      case 'user':
        return (users.data?.items ?? []).map((item) => ({
          value: item.id,
          label: item.full_name,
          hint: item.user_code,
        }));
      case 'candidate':
        // Candidates have no `full_name` column, so it is composed here, the
        // same way the API composes it for a document's owner reference.
        return ((candidates.data as Page<Candidate> | undefined)?.items ?? []).map((item) => ({
          value: item.id,
          label: `${item.first_name} ${item.last_name}`.trim(),
          hint: item.candidate_code,
        }));
      case 'organization':
        return (organizations.data?.items ?? []).map((item) => ({
          value: item.id,
          label: item.name,
          hint: item.code ?? undefined,
        }));
      default:
        return [];
    }
  }, [candidates.data, employees.data, organizations.data, ownerType, users.data]);

  const isLoading =
    ownerType === 'employee'
      ? employees.isPending
      : ownerType === 'user'
        ? users.isPending
        : ownerType === 'candidate'
          ? candidates.isPending
          : ownerType === 'organization'
            ? organizations.isPending
            : false;

  return {
    options,
    isLoading,
    emptyMessage:
      ownerType === undefined
        ? 'Choose what kind of owner first'
        : `No ${OWNER_TYPE_LABELS[ownerType].toLowerCase()} records to choose from`,
  };
}
