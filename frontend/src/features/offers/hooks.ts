'use client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { offersApi } from './api';
const root = ['offers'] as const;
export const useOfferDashboard = () =>
  useQuery({ queryKey: [...root, 'dashboard'], queryFn: offersApi.dashboard });
export const useOffers = (p: Record<string, unknown>) =>
  useQuery({ queryKey: [...root, 'list', p], queryFn: () => offersApi.list(p) });
export const useOffer = (id: string) =>
  useQuery({ queryKey: [...root, id], queryFn: () => offersApi.get(id) });
export const useTemplates = () =>
  useQuery({ queryKey: [...root, 'templates'], queryFn: offersApi.templates });
export function useOfferMutation<T, R>(fn: (x: T) => Promise<R>) {
  const q = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => void q.invalidateQueries({ queryKey: root }) });
}
