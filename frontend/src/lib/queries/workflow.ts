import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, qs } from '@/lib/api'
import type {
  CVApproveResult,
  CVContent,
  CVStudio,
  CVVersion,
  DiscoveryResult,
  Draft,
  NavCounts,
  Queue,
  SearchHit,
  Today,
} from '@/lib/types'
import { invalidateWork, keys } from './keys'

export function useToday() {
  return useQuery({ queryKey: keys.today, queryFn: () => api.get<Today>('/today') })
}

export function useNavCounts() {
  return useQuery({
    queryKey: keys.navCounts,
    queryFn: () => api.get<NavCounts>('/nav-counts'),
    retry: false,
  })
}

export function useSearch(q: string) {
  return useQuery({
    queryKey: keys.search(q),
    queryFn: () => api.get<{ hits: SearchHit[] }>(`/search${qs({ q })}`),
    enabled: q.trim().length > 1,
    placeholderData: (prev) => prev,
  })
}

export function useRunDiscovery() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<DiscoveryResult>('/discovery/run'),
    onSettled: () => {
      invalidateWork(qc)
      void qc.invalidateQueries({ queryKey: keys.settings })
    },
  })
}

// ---- CV ----------------------------------------------------------------------------------

export function useCVStudio(appId: number) {
  return useQuery({
    queryKey: keys.cv(appId),
    queryFn: () => api.get<CVStudio>(`/applications/${appId}/cv`),
    enabled: Number.isFinite(appId),
  })
}

export function useGenerateCV() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (appId: number) => api.post<CVVersion>(`/applications/${appId}/cv/generate`),
    onSettled: () => invalidateWork(qc),
  })
}

export function useSaveCV() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, content }: { id: number; content: CVContent }) =>
      api.patch<CVVersion>(`/cv/${id}`, { content: content as unknown as Record<string, unknown> }),
    onSuccess: (version) => {
      qc.setQueryData<CVStudio>(keys.cv(version.application_id), (old) =>
        old
          ? { ...old, versions: old.versions.map((v) => (v.id === version.id ? version : v)) }
          : old,
      )
    },
  })
}

export function useApproveCV() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.post<CVApproveResult>(`/cv/${id}/approve`),
    onSettled: () => invalidateWork(qc),
  })
}

// ---- Outreach ----------------------------------------------------------------------------

export function useDrafts(status: string) {
  return useQuery({
    queryKey: keys.drafts(status),
    queryFn: () => api.get<Draft[]>(`/outreach/drafts${qs({ status })}`),
    placeholderData: (prev) => prev,
  })
}

export function useSaveDraft() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, subject, body }: { id: number; subject?: string; body?: string }) =>
      api.patch<Draft>(`/outreach/drafts/${id}`, { subject, body }),
    onSuccess: (draft) => {
      qc.setQueriesData<Draft[]>({ queryKey: keys.draftsAll }, (old) =>
        old?.map((d) => (d.id === draft.id ? draft : d)),
      )
    },
  })
}

export function useDraftAction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'approve' | 'reject' | 'restore' }) =>
      api.post<Draft>(`/outreach/drafts/${id}/${action}`),
    onSettled: () => invalidateWork(qc),
  })
}

export function useGenerateDraft() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (appId: number) => api.post<Draft>(`/applications/${appId}/draft/generate`),
    onSettled: () => invalidateWork(qc),
  })
}

export function useQueue() {
  return useQuery({
    queryKey: keys.queue,
    queryFn: () => api.get<Queue>('/queue'),
    refetchInterval: 30_000,
  })
}

export function useQueueControl() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (action: 'pause' | 'resume') => api.post<Queue>(`/queue/${action}`),
    onSuccess: (queue) => qc.setQueryData(keys.queue, queue),
    onSettled: () => invalidateWork(qc),
  })
}

export function useRemoveQueueItem() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (itemId: number) => api.del<Queue>(`/queue/items/${itemId}`),
    onSuccess: (queue) => qc.setQueryData(keys.queue, queue),
    onSettled: () => invalidateWork(qc),
  })
}
