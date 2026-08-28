import { api } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import type { Candidate, Dashboard, Opening, Source, Stage, TalentPool } from './types';
const root = '/recruitment';
export const recruitmentApi = {
  dashboard: () => api.get<Dashboard>(`${root}/dashboard`),
  references: () => api.get<{ sources: Source[]; stages: Stage[] }>(`${root}/references`),
  openings: () => api.get<Opening[]>(`${root}/openings`),
  createOpening: (data: unknown) => api.post<Opening>(`${root}/openings`, data),
  openingAction: (id: string, action: string) => api.post<Opening>(`${root}/openings/${id}/${action}`),
  candidates: (params: Record<string, unknown>) => api.get<Page<Candidate>>(`${root}/candidates`, { params }),
  candidate: (id: string) => api.get<Candidate>(`${root}/candidates/${id}`),
  createCandidate: (data: unknown) => api.post<Candidate>(`${root}/candidates`, data),
  updateCandidate: (id: string, data: unknown) => api.put<Candidate>(`${root}/candidates/${id}`, data),
  move: (id: string, stage_id: string, comments: string | null = null) =>
    api.post<Candidate>(`${root}/candidates/${id}/stage`, { stage_id, comments }),
  note: (id: string, data: unknown) => api.post(`${root}/candidates/${id}/notes`, data),
  document: (id: string, data: unknown) => api.post(`${root}/candidates/${id}/documents`, data),
  pools: () => api.get<TalentPool[]>(`${root}/talent-pools`),
  createPool: (data: unknown) => api.post<TalentPool>(`${root}/talent-pools`, data),
  addPoolMember: (id: string, candidate_id: string) =>
    api.post(`${root}/talent-pools/${id}/members`, { candidate_id }),
};
