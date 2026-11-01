import { useMutation, useQuery } from '@tanstack/react-query'
import { api } from '@/lib/api'

export interface TrackOption {
  value: string
  label: string
}

/** Mirrors TrackGenerateOut (app/schemas/cv.py). */
export interface TrackCV {
  id: string | null
  track: string
  status: 'running' | 'ready' | 'failed'
  error: string | null
  page_count: number | null
  model: string | null
  filename: string | null
  issues: { message?: string; severity?: string }[]
  summary: string
  skills: string[]
  job_id: number | null
  cv_id: number | null
}

export const useCvTracks = () =>
  useQuery({ queryKey: ['cv-tracks'], queryFn: () => api.get<TrackOption[]>('/cv/tracks') })

export const useGenerateTrackCv = () =>
  useMutation({
    mutationFn: (body: { track: string; target_job_id?: number | null }) => api.post<TrackCV>('/cv/generate', body),
  })

/** Polls the background worker every 1.5s until it is ready or failed. */
export function useTrackCvStatus(id: string | null) {
  return useQuery({
    queryKey: ['cv-track-status', id],
    enabled: !!id,
    queryFn: () => api.get<TrackCV>(`/cv/generate/${id}`),
    refetchInterval: (q) => (q.state.data?.status === 'running' ? 1500 : false),
    retry: false,
  })
}
