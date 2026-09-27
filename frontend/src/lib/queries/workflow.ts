import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, qs } from '@/lib/api'
import type {
  CVApproveResult,
  CVContent,
  CVStudio,
  CVVersion,
  DiscoveryStatus,
  Draft,
  NavCounts,
  Queue,
  FullListingResult,
  ScoringHealth,
  ScoringStatus,
  SearchHit,
  Source,
  SourceInfo,
  SourceTestResult,
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

/** Polls fast (1s) while a run is active, slowly (30s) otherwise so scheduled runs show up. */
export function useDiscoveryStatus() {
  return useQuery({
    queryKey: keys.discoveryStatus,
    queryFn: () => api.get<DiscoveryStatus>('/discovery/status'),
    refetchInterval: (query) => (query.state.data?.running ? 1000 : 30_000),
    // Keep polling when the window is in the background: a run started before switching away
    // must still finish in the UI (it's a cheap local call).
    refetchIntervalInBackground: true,
    retry: false,
  })
}

export function useStartDiscovery() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ run_id: number }>('/discovery/run'),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.discoveryStatus }),
  })
}

export function useSources() {
  return useQuery({ queryKey: keys.sources, queryFn: () => api.get<SourceInfo[]>('/sources') })
}

export function useTestSource() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (source: Source) => api.post<SourceTestResult>(`/sources/${source}/test`),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.sources }),
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

// ---- Scoring -----------------------------------------------------------------------------

export function useScoringStatus() {
  return useQuery({
    queryKey: keys.scoringStatus,
    queryFn: () => api.get<ScoringStatus>('/scoring/status'),
    refetchInterval: (query) => (query.state.data?.running ? 2000 : 20_000),
    refetchIntervalInBackground: true,
    retry: false,
  })
}

export function useScoringHealth() {
  return useQuery({
    queryKey: keys.scoringHealth,
    queryFn: () => api.get<ScoringHealth>('/scoring/health'),
    retry: false,
  })
}

export function useRescore() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { scope: 'stale' | 'failed' | 'unscored' | 'all' | 'jobs'; job_ids?: number[] }) =>
      api.post<{ enqueued: number }>('/scoring/rescore', body),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.scoringStatus }),
  })
}

export function useRescoreJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (jobId: number) => api.post<{ enqueued: number }>(`/jobs/${jobId}/rescore`),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.scoringStatus }),
  })
}

export function useCancelScoring() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ enqueued: number }>('/scoring/cancel'),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.scoringStatus }),
  })
}

export function useStartScoring() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<{ enqueued: number }>('/scoring/start'),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: keys.scoringStatus })
      void qc.invalidateQueries({ queryKey: keys.scoringHealth })
    },
  })
}

export function useFetchFullListing() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (jobId: number) => api.post<FullListingResult>(`/jobs/${jobId}/fetch-full`),
    onSettled: (_d, _e, jobId) => {
      void qc.invalidateQueries({ queryKey: keys.job(jobId) })
      void qc.invalidateQueries({ queryKey: keys.scoringStatus })
    },
  })
}

export function usePasteDescription() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ jobId, description }: { jobId: number; description: string }) =>
      api.put<FullListingResult>(`/jobs/${jobId}/description`, { description }),
    onSettled: (_d, _e, { jobId }) => {
      void qc.invalidateQueries({ queryKey: keys.job(jobId) })
      void qc.invalidateQueries({ queryKey: keys.scoringStatus })
    },
  })
}
