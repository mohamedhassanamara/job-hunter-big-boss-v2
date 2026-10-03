import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, apiUrl, qs } from '@/lib/api'
import type {
  ApplicationResponse,
  ApplyMethod,
  CloseReason,
  Interview,
  InterviewOutcome,
  InterviewType,
  PipelineCard,
  ReadyItem,
  ResponseKind,
  Stats,
  TrackedApplication,
  TrackingFilters,
} from '@/lib/types'
import { invalidateWork, keys } from './keys'

export function useReadyToApply() {
  return useQuery({ queryKey: keys.ready, queryFn: () => api.get<ReadyItem[]>('/applications/ready') })
}

export function useTracked(filters: TrackingFilters) {
  return useQuery({
    queryKey: keys.tracked({ ...filters }),
    queryFn: () => api.get<TrackedApplication[]>(`/applications/tracked${qs({ ...filters })}`),
    placeholderData: (prev) => prev,
  })
}

export function useStats(filters: TrackingFilters) {
  return useQuery({
    queryKey: keys.stats({ ...filters }),
    queryFn: () => api.get<Stats>(`/stats${qs({ ...filters })}`),
    placeholderData: (prev) => prev,
  })
}

/** A download link (can't send headers, so the workspace goes in the query string too). */
export function exportCsvUrl(filters: TrackingFilters): string {
  const base = apiUrl('/applications/export.csv')
  const query = qs({ ...filters }).slice(1)
  return query ? `${base}${base.includes('?') ? '&' : '?'}${query}` : base
}

export interface AppliedInput {
  appId: number
  applied_on: string
  method: ApplyMethod
  cv_version_id?: number
  cover_letter_id?: number | null
  form_letter_id?: number | null
  notes: string
}

export function useMarkApplied() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ appId, ...body }: AppliedInput) =>
      api.post<PipelineCard>(`/applications/${appId}/applied`, { ...body }),
    onSettled: () => invalidateWork(qc),
  })
}

/** Undo "Mark applied" (the toast's Undo): dates, stage and the locks it made go back. */
export function useUndoApplied() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (appId: number) => api.del<PipelineCard>(`/applications/${appId}/applied`),
    onSettled: () => invalidateWork(qc),
  })
}

export function useLogResponse() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ appId, ...body }: { appId: number; kind: ResponseKind; received_on: string; notes: string }) =>
      api.post<ApplicationResponse>(`/applications/${appId}/responses`, { ...body }),
    onSettled: () => invalidateWork(qc),
  })
}

export function useLogInterview() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ appId, ...body }: { appId: number; scheduled_at: string; type: InterviewType; notes: string }) =>
      api.post<Interview>(`/applications/${appId}/interviews`, { ...body }),
    onSettled: () => invalidateWork(qc),
  })
}

export function useUpdateInterview() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...patch }: { id: number; outcome?: InterviewOutcome; scheduled_at?: string; notes?: string }) =>
      api.patch<Interview>(`/interviews/${id}`, { ...patch }),
    onSettled: () => invalidateWork(qc),
  })
}

export function useCloseApplication() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ appId, reason, notes = '' }: { appId: number; reason: CloseReason; notes?: string }) =>
      api.post<PipelineCard>(`/applications/${appId}/close`, { reason, notes }),
    onSettled: () => invalidateWork(qc),
  })
}

export function useReminderAction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async ({ appId, key, action }: { appId: number; key: string; action: 'snooze' | 'dismiss' | 'confirm' }): Promise<void> => {
      if (action === 'confirm') await api.post<PipelineCard>(`/reminders/${appId}/ghost/confirm`)
      else await api.post<void>(`/reminders/${appId}/${encodeURIComponent(key)}/${action}`, action === 'snooze' ? { days: 3 } : undefined)
    },
    onSettled: () => invalidateWork(qc),
  })
}
