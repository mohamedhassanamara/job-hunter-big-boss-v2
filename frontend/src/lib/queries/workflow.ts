import { useEffect, useRef } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, qs } from '@/lib/api'
import type {
  CVApproveResult,
  CVReviewRow,
  CVPatchInput,
  CVStudio,
  CVTemplateInfo,
  CVVersion,
  CVViolation,
  DiscoveryStatus,
  Draft,
  DraftProgress,
  DraftGenerateInput,
  GenerationStatus,
  DraftHistoryItem,
  EmailMode,
  ExternalCheck,
  ExternalPrompt,
  FullListingResult,
  NavCounts,
  OutreachStep,
  Queue,
  RescorePreview,
  ScoringHealth,
  ScoringQuota,
  ApinexStatus,
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

/** A new summary for a draft (the CV model from Settings → Models); with feedback it edits the
 * current one toward it. Bullets and layout stay as they are. */
export function useRegenerateSummary() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ cvId, feedback, use }: { cvId: number; feedback?: string; use?: 'claude' | 'gemini' }) =>
      api.post<CVVersion>(`/cv/${cvId}/summary`, { feedback: feedback?.trim() || null, use: use ?? null }),
    onSettled: () => invalidateWork(qc),
  })
}

/** Go back to an earlier summary of the draft. */
export function useRestoreSummary() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ cvId, index }: { cvId: number; index: number }) => api.post<CVVersion>(`/cv/${cvId}/summary/restore`, { index }),
    onSettled: () => invalidateWork(qc),
  })
}

/** The checks on a summary text, live while typing (information only, no model call). */
export function useSummaryCheck(cvId: number, text: string, enabled: boolean) {
  return useQuery({
    queryKey: ['cv-summary-check', cvId, text],
    queryFn: () => api.post<{ warnings: CVViolation[] }>(`/cv/${cvId}/summary/check`, { text }),
    enabled: enabled && text.trim().length > 0,
    staleTime: 60_000,
    placeholderData: (previous) => previous,
  })
}

export function useGenerateCV() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ appId, template, use }: { appId: number; template?: string; use?: 'claude' | 'gemini' }) =>
      api.post<CVVersion>(`/applications/${appId}/cv/generate`, { template: template ?? null, use: use ?? null }),
    onSettled: () => invalidateWork(qc),
  })
}

/** Force items in/out, edit text or switch template: re-fits and re-renders (no Claude call). */
export function usePatchCV() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...patch }: CVPatchInput & { id: number }) =>
      api.patch<CVVersion>(`/cv/${id}`, patch as Record<string, unknown>),
    onSuccess: (version) => {
      void qc.invalidateQueries({ queryKey: keys.cv(version.application_id) })
      void qc.invalidateQueries({ queryKey: keys.cvReview })
    },
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
    mutationFn: (input?: DraftGenerateInput) => api.post<DraftProgress>(`/applications/${appId}/draft/generate`, input ?? {}),
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

export function useApinexStatus() {
  return useQuery({
    queryKey: ['apinex-status'],
    queryFn: () => api.get<ApinexStatus>('/scoring/apinex'),
    refetchInterval: 60_000,
    retry: false,
  })
}

export function useApinexCheckedIn() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<ApinexStatus>('/scoring/apinex/checked-in'),
    onSuccess: (data) => qc.setQueryData(['apinex-status'], data),
  })
}

export function useScoringHealth(model?: string) {
  return useQuery({
    queryKey: [...keys.scoringHealth, model ?? 'primary'],
    queryFn: () => api.get<ScoringHealth>(model ? `/scoring/health?model=${encodeURIComponent(model)}` : '/scoring/health'),
    retry: false,
  })
}

export type RescoreParams = Record<string, unknown> & {
  scope: 'stale' | 'failed' | 'unscored' | 'all' | 'outdated' | 'jobs'
  job_ids?: number[]
  confirm?: boolean
  track?: string
  since_days?: number
  limit?: number
  only_unscored?: boolean
}

export function useRescore() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: RescoreParams) =>
      api.post<{ enqueued: number }>('/scoring/rescore', body),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.scoringStatus }),
  })
}

export function useRescorePreview(
  params: {
    scope: 'all' | 'stale' | 'outdated' | 'unscored' | 'failed' | 'jobs'
    track?: string
    since_days?: number
    limit?: number
    only_unscored?: boolean
    job_ids?: number[]
  } | 'all' | 'stale' | 'outdated',
  enabled: boolean,
) {
  const queryObj = typeof params === 'string' ? { scope: params } : params
  const searchParams = new URLSearchParams()
  searchParams.set('scope', queryObj.scope)
  if (queryObj.track && queryObj.track !== 'all') searchParams.set('track', queryObj.track)
  if (queryObj.since_days !== undefined && queryObj.since_days > 0) searchParams.set('since_days', String(queryObj.since_days))
  if (queryObj.limit !== undefined && queryObj.limit > 0) searchParams.set('limit', String(queryObj.limit))
  if (queryObj.only_unscored) searchParams.set('only_unscored', 'true')
  if (queryObj.job_ids?.length) {
    for (const id of queryObj.job_ids) searchParams.append('job_ids', String(id))
  }

  return useQuery({
    queryKey: ['rescore-preview', queryObj],
    queryFn: () => api.get<RescorePreview>(`/scoring/rescore-preview?${searchParams.toString()}`),
    enabled,
    staleTime: 0,
  })
}

/** Gemini quota per key and pooled. `model`: the pool of that model (scoring, CV and email
 * generation normally share one); default is the scoring model's. */
export function useScoringQuota(model?: string) {
  return useQuery({
    queryKey: ['scoring-quota', model ?? null],
    queryFn: () => api.get<ScoringQuota>(`/scoring/quota${model ? `?model=${encodeURIComponent(model)}` : ''}`),
    refetchInterval: 30_000,
    retry: false,
  })
}

export function useContinueWith() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (model: string | null) => api.post<{ enqueued: number }>('/scoring/continue-with', { model }),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: keys.scoringStatus })
      void qc.invalidateQueries({ queryKey: ['scoring-quota'] })
    },
  })
}

/** The pause switch: no Gemini request at all, CV and email generation use Claude. */
export function usePauseGemini() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (paused: boolean) => api.post<{ paused: boolean }>('/scoring/gemini/pause', { paused }),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ['scoring-quota'] })
      void qc.invalidateQueries({ queryKey: keys.settings })
    },
  })
}

export function useEnableGeminiKey() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (label: string) => api.post<{ ok: boolean }>(`/scoring/keys/${encodeURIComponent(label)}/enable`),
    onSettled: () => qc.invalidateQueries({ queryKey: ['scoring-quota'] }),
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

/** Check every claim of the email now (Claude, ~20-60 s), without approving. */
export function useVerifyDraft() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.post<Draft>(`/outreach/drafts/${id}/verify`),
    onSettled: () => invalidateWork(qc),
  })
}

/** Every version of a job's email with the feedback that made it (go back with Restore). */
export function useDraftHistory(appId: number | undefined) {
  return useQuery({
    queryKey: ['draft-history', appId],
    queryFn: () => api.get<DraftHistoryItem[]>(`/applications/${appId}/draft/history`),
    enabled: appId !== undefined,
  })
}

/** Approve THIS draft without the claim verifier or the blocking checks (the dialog lists them). */
export function useApproveUnverified() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.post<Draft>(`/outreach/drafts/${id}/approve-unverified`, { confirm: true }),
    onSettled: () => invalidateWork(qc),
  })
}

/** One prompt for another AI (Gemini, ChatGPT…): the listing, the recipient, the relevant experience, the rules. */
export function useExternalPrompt(appId: number) {
  return useMutation({
    mutationFn: (input: { mode?: EmailMode; language?: 'en' | 'fr' }) => api.post<ExternalPrompt>(`/applications/${appId}/external-prompt`, input),
  })
}

/** The checks and the claim verifier (Claude, ~20-60 s) on a draft pasted from another AI. */
export function useExternalCheck(appId: number) {
  return useMutation({
    mutationFn: (input: { text: string; mode?: EmailMode }) => api.post<ExternalCheck>(`/applications/${appId}/external-draft/check`, input),
  })
}

export function useExternalSave(appId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (input: { text: string; mode?: EmailMode }) => api.post<Draft>(`/applications/${appId}/external-draft`, input),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: ['draft-history', appId] })
      invalidateWork(qc)
    },
  })
}

/** Background drafting (CV on shortlist, email when ready): polled lightly, and the cards refresh
 * exactly when a task finishes or fails. Silent: no toasts. */
export function useGenerationStatus() {
  const qc = useQueryClient()
  const status = useQuery({
    queryKey: ['generation-status'],
    queryFn: () => api.get<GenerationStatus>('/generation/status'),
    refetchInterval: (q) => ((q.state.data?.active ?? 0) > 0 ? 4000 : 30_000),
    retry: false,
  })
  const last = useRef<string | undefined>(undefined)
  const signature = status.data?.signature
  useEffect(() => {
    if (last.current !== undefined && signature !== undefined && signature !== last.current) invalidateWork(qc)
    last.current = signature
  }, [signature, qc])
  return status
}

/** CV drafts of shortlisted jobs with the Approve gate evaluated (Review CVs). */
export function useCVReview() {
  return useQuery({ queryKey: keys.cvReview, queryFn: () => api.get<CVReviewRow[]>('/cv/review') })
}

/** Take a queued email out of the send queue by its draft (it stays approved). */
export function useDequeueDraft() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (draftId: number) => {
      const queue = await api.get<Queue>('/queue')
      const item = queue.items.find((i) => i.draft_id === draftId && i.status === 'pending')
      if (!item) throw new Error('That email is no longer waiting in the queue')
      return api.del<Queue>(`/queue/items/${item.id}`)
    },
    onSettled: () => invalidateWork(qc),
  })
}

/** "Add all approved": one after another, stopping when the queue is full. */
export function useQueueAll() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: async (draftIds: number[]) => {
      let added = 0
      let stoppedBy: string | null = null
      for (const id of draftIds) {
        try {
          await api.post<Draft>(`/outreach/drafts/${id}/queue`)
          added += 1
        } catch (e) {
          stoppedBy = (e as Error).message
          break
        }
      }
      return { added, left: draftIds.length - added, stoppedBy }
    },
    onSettled: () => invalidateWork(qc),
  })
}
