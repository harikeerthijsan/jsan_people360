'use client';
import { useQuery } from '@tanstack/react-query';
import { hrApi } from './api';
const root = ['hr'] as const;
export const useHrDashboard = (enabled = true) =>
  useQuery({ queryKey: [...root, 'dashboard'], queryFn: hrApi.dashboard, staleTime: 30_000, enabled });
export const useHrAnalytics = (enabled = true) =>
  useQuery({ queryKey: [...root, 'analytics'], queryFn: hrApi.analytics, staleTime: 60_000, enabled });
export const useHrEmployees = (params: Record<string, unknown>) =>
  useQuery({ queryKey: [...root, 'employees', params], queryFn: () => hrApi.employees(params) });
export const useHrEmployee = (id: string) =>
  useQuery({ queryKey: [...root, 'employee', id], queryFn: () => hrApi.employee(id), enabled: Boolean(id) });
export const useHrList = (
  kind: 'attendance' | 'leave' | 'timesheets' | 'documents',
  params: Record<string, unknown>,
) => useQuery({ queryKey: [...root, kind, params], queryFn: (): Promise<unknown> => hrApi[kind](params) });
export const useHrResource = (kind: 'policies' | 'reports') =>
  useQuery({ queryKey: [...root, kind], queryFn: (): Promise<unknown> => hrApi[kind]() });
export const useHrProjects = () =>
  useQuery({ queryKey: [...root, 'projects'], queryFn: hrApi.projects, staleTime: 30_000 });
export const useHrPerformance = () =>
  useQuery({ queryKey: [...root, 'performance'], queryFn: hrApi.performance, staleTime: 30_000 });
