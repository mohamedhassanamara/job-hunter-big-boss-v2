import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { CVFit, Critique } from '@/lib/types'

export type CritiqueKind = 'cv' | 'letter' | 'email' | 'linkedin_note' | 'linkedin_followup'

/** One Claude call: what's still weak from the reader's side (never a rewrite). */
export function useCritique() {
  return useMutation({ mutationFn: ({ kind, id }: { kind: CritiqueKind; id: number }) => api.post<Critique>('/critique', { kind, id }) })
}

/** Fit before/after for an approved CV (polls while the model runs). */
export function useCVFit(cvId: number | null) {
  return useQuery({
    queryKey: ['cv-fit', cvId],
    queryFn: () => api.get<CVFit | null>(`/cv/${cvId}/fit`),
    enabled: cvId !== null,
    refetchInterval: (q) => (q.state.data == null || q.state.data.status === 'pending' ? 2000 : false),
  })
}

export function useRerunCVFit() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (cvId: number) => api.post<{ started: boolean }>(`/cv/${cvId}/fit`),
    onSettled: (_d, _e, cvId) => qc.invalidateQueries({ queryKey: ['cv-fit', cvId] }),
  })
}
