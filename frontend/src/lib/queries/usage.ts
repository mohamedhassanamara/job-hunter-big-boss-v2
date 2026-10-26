import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { api } from '../api'
import type { UsageReportView } from '../types'

const key = ['usage', 'report'] as const

export function useUsageReport() {
  return useQuery({ queryKey: key, queryFn: () => api.get<UsageReportView>('/usage/report?last=1') })
}

export function useClearUsage() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.del<{ deleted: number }>('/usage'),
    onSuccess: (r) => {
      void qc.invalidateQueries({ queryKey: key })
      toast.success(`Usage log cleared (${r.deleted} entries)`)
    },
    onError: (e) => toast.error(e.message),
  })
}
