import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ConfirmationOut } from '@/lib/types'

const key = (jobId: number) => ['confirmation', jobId] as const

export function useConfirmation(jobId: number) {
  return useQuery({
    queryKey: key(jobId),
    queryFn: () => api.get<ConfirmationOut | null>(`/jobs/${jobId}/confirmation`),
    retry: false,
  })
}

/** Ask Claude (your subscription), falling back to Gemma. Takes 20-60 s: callers show progress. */
export function useAskClaude(jobId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<ConfirmationOut>(`/jobs/${jobId}/confirm`),
    onSuccess: (data) => qc.setQueryData(key(jobId), data),
  })
}

export function useConfirmationPrompt(jobId: number, enabled: boolean) {
  return useQuery({
    queryKey: ['confirmation-prompt', jobId],
    queryFn: () => api.get<{ prompt: string }>(`/jobs/${jobId}/confirmation/prompt`),
    enabled,
    staleTime: 0,
    retry: false,
  })
}

export function usePasteConfirmation(jobId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (text: string) => api.post<ConfirmationOut>(`/jobs/${jobId}/confirmation/paste`, { text }),
    onSuccess: (data) => qc.setQueryData(key(jobId), data),
  })
}
