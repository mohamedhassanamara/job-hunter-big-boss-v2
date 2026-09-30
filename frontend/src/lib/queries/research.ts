import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { CompanyResearch, CompanySignal } from '@/lib/types'

const key = (companyId: number) => ['research', companyId]

/** A company's signals and last research run (polled while a manual run is going). */
export function useCompanyResearch(companyId: number | undefined) {
  return useQuery({
    queryKey: key(companyId ?? NaN),
    queryFn: () => api.get<CompanyResearch>(`/companies/${companyId}/research`),
    enabled: companyId != null,
    refetchInterval: (q) => (q.state.data?.progress?.status === 'running' ? 1000 : false),
  })
}

/** Research now / Refresh signals (the only trigger besides the email draft step). */
export function useResearchNow() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ companyId, force = true }: { companyId: number; force?: boolean }) =>
      api.post<CompanyResearch>(`/companies/${companyId}/research`, { force }),
    onSuccess: (data) => qc.setQueryData(key(data.company_id), data),
  })
}

export function usePatchSignal(companyId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...patch }: { id: number; selected?: boolean; dismissed?: boolean }) =>
      api.patch<CompanySignal>(`/signals/${id}`, patch),
    onSettled: () => void qc.invalidateQueries({ queryKey: key(companyId) }),
  })
}

export function useAddSignal(companyId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { fact: string; source_url: string; kind: string }) =>
      api.post<CompanySignal>(`/companies/${companyId}/signals`, body),
    onSettled: () => void qc.invalidateQueries({ queryKey: key(companyId) }),
  })
}

export function useSetWebsite(companyId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (website: string) => api.put<CompanyResearch>(`/companies/${companyId}/website`, { website }),
    onSuccess: (data) => qc.setQueryData(key(companyId), data),
  })
}
