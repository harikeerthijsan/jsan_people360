'use client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { recruitmentApi } from './api';
const root = ['recruitment'] as const;
export const useDashboard = () =>
  useQuery({ queryKey: [...root, 'dashboard'], queryFn: recruitmentApi.dashboard });
export const useReferences = () =>
  useQuery({ queryKey: [...root, 'references'], queryFn: recruitmentApi.references });
export const useOpenings = () =>
  useQuery({ queryKey: [...root, 'openings'], queryFn: recruitmentApi.openings });
export const useCandidates = (params: Record<string, unknown>) =>
  useQuery({ queryKey: [...root, 'candidates', params], queryFn: () => recruitmentApi.candidates(params) });
export const useCandidate = (id: string) =>
  useQuery({ queryKey: [...root, 'candidate', id], queryFn: () => recruitmentApi.candidate(id) });
export const usePools = () => useQuery({ queryKey: [...root, 'pools'], queryFn: recruitmentApi.pools });
export function useRecruitmentMutation<T, R>(fn: (data: T) => Promise<R>) {
  const q = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => void q.invalidateQueries({ queryKey: root }) });
}
