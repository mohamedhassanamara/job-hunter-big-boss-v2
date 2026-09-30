import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, qs } from '@/lib/api'
import type {
  CVApproveResult,
  CVPatchInput,
  CVStudio,
  CVTemplateInfo,
  CVVersion,
  DiscoveryStatus,
  Draft,
  DraftProgress,
  FullListingResult,
  NavCounts,
  OutreachStep,
  Queue,
  RescorePreview,
  ScoringHealth,
  ScoringStatus,
  SearchHit,
  SendLogEntry,
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

/** A new summary for a draft; bullets and layout stay as they are. */
export function useRegenerateSummary() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (cvId: number) => api.post<CVVersion>(`/cv/${cvId}/summary`),
    onSettled: () => invalidateWork(qc),
  })
}

export function useGenerateCV() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ appId, template }: { appId: number; template?: string }) =>
      api.post<CVVersion>(`/applications/${appId}/cv/generate`, { template: template ?? null }),
    onSettled: () => invalidateWork(qc),
  })
}

/** Force items in/out, edit text or switch template: re-fits and re-renders (no Claude call). */
export function usePatchCV() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...patch }: CVPatchInput & { id: number }) =>
      api.patch<CVVersion>(`/cv/${id}`, patch as Record<string, unknown>),
    onSuccess: (version) => void qc.invalidateQueries({ queryKey: keys.cv(version.application_id) }),
  })
}

export function useCVTemplates() {
  return useQuery({ queryKey: keys.cvTemplates, queryFn: () => api.get<CVTemplateInfo[]>('/cv/templates') })
}

export function useAddCVTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { name: string; tex: string; config: string }) => api.post<CVTemplateInfo>('/cv/templates', body),
    onSettled: () => void qc.invalidateQueries({ queryKey: keys.cvTemplates }),
  })
}

export function useValidateCVTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => api.post<CVTemplateInfo>(`/cv/templates/${encodeURIComponent(name)}/validate`),
    onSettled: () => void qc.invalidateQueries({ queryKey: keys.cvTemplates }),
  })
}

export function useDeleteCVTemplate() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (name: string) => api.del<void>(`/cv/templates/${encodeURIComponent(name)}`),
    onSettled: () => void qc.invalidateQueries({ queryKey: keys.cvTemplates }),
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

/** Add or remove "I have also applied through your careers page on …" (fixed wording). */
export function useMentionApplication() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, include }: { id: number; include: boolean }) =>
      api.post<Draft>(`/outreach/drafts/${id}/mention-application`, { include }),
    onSettled: () => invalidateWork(qc),
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

/** The email draft step: research the company (fresh signals are reused), then write the
 * draft, in the background. `state` is polled every second while it runs; views refresh at the
 * end and `onDone` gets the new draft id (or the error). */
export function useDraftRun(appId: number | undefined, onDone?: (result: { draftId?: number | null; error?: string | null }) => void) {
  const qc = useQueryClient()
  const key = ['draft-progress', appId]
  const progress = useQuery({
    queryKey: key,
    queryFn: () => api.get<DraftProgress>(`/applications/${appId}/draft/progress`),
    enabled: appId != null && Number.isFinite(appId),
    refetchInterval: (q) => (q.state.data?.status === 'running' ? 1000 : false),
  })
  const last = useRef<string | undefined>(undefined)
  const status = progress.data?.status
  useEffect(() => {
    if (last.current === 'running' && status && status !== 'running') {
      invalidateWork(qc)
      onDone?.({ draftId: progress.data?.draft_id, error: progress.data?.error })
    }
    last.current = status
  }, [status, qc, onDone, progress.data?.draft_id, progress.data?.error])
  const start = useMutation({
    mutationFn: () => api.post<DraftProgress>(`/applications/${appId}/draft/generate`),
    onSuccess: (state) => qc.setQueryData(key, state),
  })
  return { start: start.mutate, starting: start.isPending, state: progress.data, running: status === 'running' || start.isPending, startError: start.error }
}

export function useOutreachStep(appId: number | undefined) {
  return useQuery({
    queryKey: ['outreach-step', appId],
    queryFn: () => api.get<OutreachStep>(`/applications/${appId}/outreach`),
    enabled: appId !== undefined,
  })
}

export function useQueueDraft() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (draftId: number) => api.post<Draft>(`/outreach/drafts/${draftId}/queue`),
    onSettled: () => invalidateWork(qc),
  })
}

export function useSentManually() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ appId, sent_on }: { appId: number; sent_on: string }) =>
      api.post<OutreachStep>(`/applications/${appId}/sent-manually`, { sent_on }),
    onSettled: () => invalidateWork(qc),
  })
}

export function useTestSend() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (draftId: number) => api.post<SendLogEntry>(`/outreach/drafts/${draftId}/test-send`),
    onSettled: () => invalidateWork(qc),
  })
}

export function useQueueItemAction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ itemId, action }: { itemId: number; action: 'retry' | 'mark-sent' }) =>
      api.post<Queue>(`/queue/items/${itemId}/${action}`),
    onSuccess: (queue) => qc.setQueryData(keys.queue, queue),
    onSettled: () => invalidateWork(qc),
  })
}

export function useSendLog() {
  return useQuery({ queryKey: ['send-log'], queryFn: () => api.get<SendLogEntry[]>('/outreach/send-log') })
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

export function useScoringHealth(model?: string) {
  return useQuery({
    queryKey: [...keys.scoringHealth, model ?? 'primary'],
    queryFn: () => api.get<ScoringHealth>(model ? `/scoring/health?model=${encodeURIComponent(model)}` : '/scoring/health'),
    retry: false,
  })
}

export function useRescore() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { scope: 'stale' | 'failed' | 'unscored' | 'all' | 'jobs'; job_ids?: number[]; confirm?: boolean }) =>
      api.post<{ enqueued: number }>('/scoring/rescore', body),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.scoringStatus }),
  })
}

export function useRescorePreview(scope: 'all' | 'stale', enabled: boolean) {
  return useQuery({
    queryKey: ['rescore-preview', scope],
    queryFn: () => api.get<RescorePreview>(`/scoring/rescore-preview?scope=${scope}`),
    enabled,
    staleTime: 0,
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
