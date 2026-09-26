import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, qs } from '@/lib/api'
import type {
  ApplicationPatch,
  JobDetail,
  JobList,
  JobListItem,
  PipelineCard,
  Stage,
} from '@/lib/types'
import { invalidateWork, keys } from './keys'

export interface JobFilters {
  stage?: 'new' | 'open' | 'all'
  q?: string
  source?: string[]
  remote?: string[]
  country?: string[]
  min_score?: number | null
  posted_within?: number | null
  hide_duplicates?: boolean
  sort?: 'fit' | 'newest'
}

export function useJobs(filters: JobFilters) {
  return useQuery({
    queryKey: keys.jobs(filters as Record<string, unknown>),
    queryFn: () => api.get<JobList>(`/jobs${qs({ ...filters })}`),
    placeholderData: (prev) => prev,
  })
}

export function useJob(id: number) {
  return useQuery({
    queryKey: keys.job(id),
    queryFn: () => api.get<JobDetail>(`/jobs/${id}`),
    enabled: Number.isFinite(id),
  })
}

export function useApplications() {
  return useQuery({
    queryKey: keys.applications,
    queryFn: () => api.get<PipelineCard[]>('/applications'),
  })
}

/** Optimistically move a job's stage inside every cached job list. */
function patchCachedStage(qc: ReturnType<typeof useQueryClient>, jobId: number, stage: Stage) {
  qc.setQueriesData<JobList>({ queryKey: keys.jobsAll }, (old) =>
    old
      ? {
          ...old,
          items: old.items.map((j) =>
            j.id === jobId ? { ...j, application: { ...j.application, stage } } : j,
          ),
        }
      : old,
  )
}

export function useTriage() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ jobId, action }: { jobId: number; action: 'shortlist' | 'dismiss' }) =>
      api.post<JobListItem>(`/jobs/${jobId}/${action}`),
    onMutate: async ({ jobId, action }) => {
      await qc.cancelQueries({ queryKey: keys.jobsAll })
      patchCachedStage(qc, jobId, action === 'shortlist' ? 'shortlisted' : 'closed')
    },
    onSettled: () => invalidateWork(qc),
  })
}

export function usePatchApplication() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: ApplicationPatch }) =>
      api.patch<PipelineCard>(`/applications/${id}`, { ...patch }),
    onMutate: async ({ id, patch }) => {
      if (!patch.stage) return
      await qc.cancelQueries({ queryKey: keys.applications })
      const prev = qc.getQueryData<PipelineCard[]>(keys.applications)
      qc.setQueryData<PipelineCard[]>(keys.applications, (old) =>
        old?.map((c) =>
          c.application_id === id
            ? {
                ...c,
                stage: patch.stage!,
                close_reason: patch.stage === 'closed' ? (patch.close_reason ?? 'dismissed') : null,
                stage_changed_at: new Date().toISOString(),
              }
            : c,
        ),
      )
      return { prev }
    },
    onError: (_err, _vars, ctx) => {
      if (ctx?.prev) qc.setQueryData(keys.applications, ctx.prev)
    },
    onSettled: () => invalidateWork(qc),
  })
}

export function useQueueLookup() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (appId: number) => api.post<JobDetail>(`/applications/${appId}/lookup`),
    onSettled: () => invalidateWork(qc),
  })
}
