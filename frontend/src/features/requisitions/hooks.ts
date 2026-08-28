'use client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { requisitionsApi } from './api';
import { queryKeys } from '@/lib/query-client';
import type { AppError } from '@/lib/errors';
import type { Dashboard, Requisition } from './types';
import type { Page } from '@/lib/api/types';
export const useRequisitions = (params: Record<string, unknown>) =>
  useQuery<Page<Requisition>, AppError>({
    queryKey: queryKeys.requisitions.list(params),
    queryFn: () => requisitionsApi.list(params),
  });
export const useRequisition = (id: string) =>
  useQuery<Requisition, AppError>({
    queryKey: queryKeys.requisitions.detail(id),
    queryFn: () => requisitionsApi.get(id),
  });
export const useRequisitionDashboard = () =>
  useQuery<Dashboard, AppError>({
    queryKey: queryKeys.requisitions.dashboard(),
    queryFn: requisitionsApi.dashboard,
  });
export function useRequisitionMutation<TVariables>(fn: (v: TVariables) => Promise<Requisition>) {
  const qc = useQueryClient();
  return useMutation<Requisition, AppError, TVariables>({
    mutationFn: fn,
    onSuccess: (r) => {
      qc.setQueryData(queryKeys.requisitions.detail(r.id), r);
      void qc.invalidateQueries({ queryKey: queryKeys.requisitions.root });
    },
  });
}
