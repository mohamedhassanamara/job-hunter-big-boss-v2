import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '@/lib/api'
import type { CopilotMessage, CopilotStatus, CopilotThread, CopilotThreadDetail } from '@/lib/types'
import { keys } from './keys'

export function useCopilotStatus() {
  return useQuery({ queryKey: keys.copilotStatus, queryFn: () => api.get<CopilotStatus>('/copilot/status'), staleTime: 30_000 })
}

/** The job's conversation (created on first use). */
export function useJobCopilot(appId: number, enabled = true) {
  return useQuery({
    queryKey: keys.jobCopilot(appId),
    queryFn: () => api.get<CopilotThreadDetail>(`/applications/${appId}/copilot`),
    enabled: enabled && Number.isFinite(appId),
  })
}

export function useCopilotThreads() {
  return useQuery({ queryKey: keys.copilotThreads, queryFn: () => api.get<CopilotThread[]>('/copilot/threads') })
}

export function useCopilotThread(id: number | null) {
  return useQuery({
    queryKey: keys.copilotThread(id ?? NaN),
    queryFn: () => api.get<CopilotThreadDetail>(`/copilot/threads/${id}`),
    enabled: id != null,
  })
}

export function useNewCopilotThread() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<CopilotThreadDetail>('/copilot/threads'),
    onSuccess: () => void qc.invalidateQueries({ queryKey: keys.copilotThreads }),
  })
}

export function useDeleteCopilotThread() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.del<void>(`/copilot/threads/${id}`),
    onSettled: () => void qc.invalidateQueries({ queryKey: ['copilot'] }),
  })
}

export function useClearJobCopilot() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (appId: number) => api.post<CopilotThreadDetail>(`/applications/${appId}/copilot/clear`),
    onSuccess: (thread, appId) => qc.setQueryData(keys.jobCopilot(appId), thread),
  })
}

/** Ask a question: the answer streams into `streaming`; the thread refreshes when it ends. */
export function useAskCopilot() {
  const qc = useQueryClient()
  const [streaming, setStreaming] = useState<{ question: string; answer: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const ask = async (threadId: number, question: string) => {
    setError(null)
    setStreaming({ question, answer: '' })
    try {
      await api.stream(`/copilot/threads/${threadId}/messages`, { question }, (chunk) =>
        setStreaming((s) => (s ? { ...s, answer: s.answer + chunk } : s)),
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      await qc.invalidateQueries({ queryKey: ['copilot'] })
      setStreaming(null)
    }
  }
  return { ask, streaming, error, pending: streaming !== null }
}

/** Rewrite an answer you'll send to people with Claude (claude -p); it's saved as a new answer. */
export function useRewriteAnswer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (messageId: number) => api.post<CopilotMessage>(`/copilot/messages/${messageId}/rewrite`),
    onSettled: () => void qc.invalidateQueries({ queryKey: ['copilot'] }),
  })
}
