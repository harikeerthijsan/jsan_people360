'use client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { interviewsApi } from './api';
const root = ['interviews'] as const;
export const useInterviewDashboard = () =>
  useQuery({ queryKey: [...root, 'dashboard'], queryFn: interviewsApi.dashboard });
export const useInterviews = (params: Record<string, unknown>) =>
  useQuery({ queryKey: [...root, 'list', params], queryFn: () => interviewsApi.list(params) });
export const useInterview = (id: string) =>
  useQuery({ queryKey: [...root, 'detail', id], queryFn: () => interviewsApi.get(id) });
export function useInterviewMutation<T, R>(fn: (value: T) => Promise<R>) {
  const q = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => void q.invalidateQueries({ queryKey: root }) });
}
