'use client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { projectsApi } from './api';
const root = ['projects'] as const;
export const useResourceDashboard = () =>
  useQuery({ queryKey: [...root, 'dashboard'], queryFn: projectsApi.dashboard });
export const useClients = () =>
  useQuery({
    queryKey: [...root, 'clients'],
    queryFn: () => projectsApi.clients({ page: 1, page_size: 100 }),
  });
export const useClientDashboard = (id: string) =>
  useQuery({ queryKey: [...root, 'client', id], queryFn: () => projectsApi.clientDashboard(id) });
export const useProjects = () =>
  useQuery({ queryKey: [...root, 'list'], queryFn: () => projectsApi.projects({ page: 1, page_size: 100 }) });
export const useProjectDashboard = (id: string) =>
  useQuery({ queryKey: [...root, 'project', id], queryFn: () => projectsApi.projectDashboard(id) });
export const useBench = () => useQuery({ queryKey: [...root, 'bench'], queryFn: projectsApi.bench });
export function useProjectMutation<T, R>(fn: (data: T) => Promise<R>) {
  const client = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => void client.invalidateQueries({ queryKey: root }) });
}
