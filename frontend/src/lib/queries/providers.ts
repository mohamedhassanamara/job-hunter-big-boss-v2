import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ProvidersStatus } from '@/lib/types'
import { keys } from './keys'

/** Credits left per key and this month's Apify spend (local counts; reading them is free). */
export function useProviders() {
  return useQuery({ queryKey: keys.providers, queryFn: () => api.get<ProvidersStatus>('/providers/status'), staleTime: 30_000 })
}

/** Read the real limits from Hunter, Prospeo and Apify (their free account endpoints). */
export function useSyncProviders() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<ProvidersStatus>('/providers/sync'),
    onSuccess: (data) => qc.setQueryData(keys.providers, data),
  })
}

export function useEnableKey() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ provider, label }: { provider: string; label: string }) => api.post<ProvidersStatus>(`/providers/${provider}/${encodeURIComponent(label)}/enable`),
    onSuccess: (data) => qc.setQueryData(keys.providers, data),
  })
}
