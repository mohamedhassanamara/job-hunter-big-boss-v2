import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { InterviewContent, InterviewPrep, InterviewStudio } from '@/lib/types'
import { invalidateWork, keys } from './keys'

export function useInterviewPrep(appId: number) {
  return useQuery({
    queryKey: keys.interview(appId),
    queryFn: () => api.get<InterviewStudio>(`/applications/${appId}/interview-prep`),
    enabled: Number.isFinite(appId),
  })
}

/** One Claude call (~30-60s), code checks and one retry. */
export function useGenerateInterviewPrep() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ appId, language }: { appId: number; language?: string }) =>
      api.post<InterviewPrep>(`/applications/${appId}/interview-prep/generate`, { language: language ?? null }),
    onSettled: () => invalidateWork(qc),
  })
}

/** Your edits: re-checked in code, no Claude call; the claim check must pass again. */
export function usePatchInterviewPrep() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, content }: { id: number; content: InterviewContent }) => api.patch<InterviewPrep>(`/interview-prep/${id}`, { content }),
    onSuccess: (prep) => void qc.invalidateQueries({ queryKey: keys.interview(prep.application_id) }),
  })
}

export function useApproveInterviewPrep() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.post<InterviewPrep>(`/interview-prep/${id}/approve`),
    onSettled: () => invalidateWork(qc),
  })
}

export function useVerifyInterviewPrep() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.post<InterviewPrep>(`/interview-prep/${id}/verify`),
    onSettled: () => void qc.invalidateQueries({ queryKey: ['interview'] }),
  })
}
