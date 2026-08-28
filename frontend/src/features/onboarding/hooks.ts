'use client';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { onboardingApi } from './api';
const root = ['onboarding'] as const;
export const useOnboardingDashboard = () =>
  useQuery({ queryKey: [...root, 'dashboard'], queryFn: onboardingApi.dashboard });
export const usePortal = (id: string) =>
  useQuery({ queryKey: [...root, 'portal', id], queryFn: () => onboardingApi.portal(id) });
export const useWelcome = (id: string) =>
  useQuery({ queryKey: [...root, 'welcome', id], queryFn: () => onboardingApi.welcome(id) });
export const useOnboardingCase = (id: string) =>
  useQuery({ queryKey: [...root, 'case', id], queryFn: () => onboardingApi.case(id) });
export function useOnboardingMutation<T, R>(fn: (data: T) => Promise<R>) {
  const client = useQueryClient();
  return useMutation({ mutationFn: fn, onSuccess: () => void client.invalidateQueries({ queryKey: root }) });
}
