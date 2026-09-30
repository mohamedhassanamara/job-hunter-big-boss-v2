import { useQuery } from '@tanstack/react-query'
import { api, qs } from '@/lib/api'
import type { StudioDocument, StudioList } from '@/lib/types'

export function useStudioDocuments(filters: { kind?: string; status?: string; q?: string }) {
  return useQuery({
    queryKey: ['studio', filters],
    queryFn: () => api.get<StudioList>(`/studio/documents${qs({ ...filters })}`),
    placeholderData: (prev) => prev,
  })
}

/** Where a document opens: the CV studio or the letter studio (form text tab for forms). */
export function studioHref(d: StudioDocument): string {
  if (d.kind === 'cv') return `/jobs/${d.job_id}/cv`
  return `/jobs/${d.job_id}/letter${d.kind === 'form' ? '?format=form' : ''}`
}
