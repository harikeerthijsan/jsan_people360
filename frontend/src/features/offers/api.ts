import { api } from '@/lib/api/client';
import type { Page } from '@/lib/api/types';
import type { Offer, OfferDashboard, OfferTemplate } from './types';
const root = '/offers';
export const offersApi = {
  dashboard: () => api.get<OfferDashboard>(`${root}/dashboard`),
  list: (p: Record<string, unknown>) => api.get<Page<Offer>>(root, { params: p }),
  get: (id: string) => api.get<Offer>(`${root}/${id}`),
  create: (d: unknown) => api.post<Offer>(root, d),
  update: (id: string, d: unknown) => api.put<Offer>(`${root}/${id}`, d),
  submit: (id: string) => api.post<Offer>(`${root}/${id}/submit`),
  approval: (id: string, a: string, c: string | null) =>
    api.post<Offer>(`${root}/${id}/approval/${a}`, { comments: c }),
  release: (id: string) => api.post<Offer>(`${root}/${id}/release`),
  action: (id: string, a: string, reason?: string) =>
    api.post<Offer>(
      `${root}/${id}/${a}`,
      a === 'accept' ? undefined : a === 'clarification' ? { message: reason } : { reason },
    ),
  templates: () => api.get<OfferTemplate[]>(`${root}/templates`),
  createTemplate: (d: unknown) => api.post<OfferTemplate>(`${root}/templates`, d),
};
