import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { LinkedInCapture, LinkedInGroup, LinkedInImport, LinkedInLinks, LinkedInPanel, LinkedInPerson, LinkedInStatus, LinkedInSummary } from '@/lib/types'
import { invalidateWork } from './keys'

export function useLinkedInLinks(remote: boolean, easy: boolean) {
  return useQuery({
    queryKey: ['linkedin-links', remote, easy],
    queryFn: () => api.get<LinkedInLinks>(`/linkedin/links?remote=${remote}&easy=${easy}`),
  })
}

export function useOpenLink() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (key: string) => api.post<void>('/linkedin/links/open', { key }),
    onSettled: () => qc.invalidateQueries({ queryKey: ['linkedin-links'] }),
  })
}

type CaptureBody = Partial<Omit<LinkedInCapture, 'missing' | 'warnings' | 'existing'>>

/** The import window's preview (nothing saved). */
export function useCheckCapture() {
  return useMutation({ mutationFn: (body: CaptureBody) => api.post<LinkedInCapture>('/linkedin/capture', body) })
}

export function useCheckPaste() {
  return useMutation({ mutationFn: ({ url, text }: { url: string; text: string }) => api.post<LinkedInCapture>('/linkedin/paste', { url, text }) })
}

export function useImportJob() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: CaptureBody) => api.post<LinkedInImport>('/linkedin/import', body),
    onSettled: () => invalidateWork(qc),
  })
}

// ---- the LinkedIn messages track --------------------------------------------------------


const panelKey = (appId: number) => ['linkedin', 'panel', appId] as const

export function useLinkedInPanel(appId: number) {
  return useQuery({ queryKey: panelKey(appId), queryFn: () => api.get<LinkedInPanel>(`/applications/${appId}/linkedin`) })
}

export function useAddLinkedInPerson(appId: number) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { full_name: string; title?: string | null; linkedin_url?: string | null; group: LinkedInGroup; alumni: boolean }) =>
      api.post<LinkedInPanel>(`/applications/${appId}/linkedin/people`, body),
    onSuccess: (panel) => qc.setQueryData(panelKey(appId), panel),
    onSettled: () => invalidateWork(qc),
  })
}

function usePersonMutation<V>(appId: number, fn: (v: V) => Promise<LinkedInPerson | void>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: panelKey(appId) })
      invalidateWork(qc)
    },
  })
}

export function useDraftLinkedIn(appId: number) {
  return usePersonMutation(appId, ({ id, kind }: { id: number; kind: 'note' | 'followup' }) => api.post<LinkedInPerson>(`/linkedin/people/${id}/${kind}`))
}

export function useEditLinkedIn(appId: number) {
  return usePersonMutation(appId, ({ id, ...patch }: { id: number; note?: string; followup?: string; group?: LinkedInGroup; alumni?: boolean }) =>
    api.patch<LinkedInPerson>(`/linkedin/people/${id}`, patch),
  )
}

export function useLinkedInStatus(appId: number) {
  return usePersonMutation(appId, ({ id, status }: { id: number; status: LinkedInStatus }) => api.post<LinkedInPerson>(`/linkedin/people/${id}/status`, { status }))
}

export function useRemoveLinkedInPerson(appId: number) {
  return usePersonMutation(appId, (id: number) => api.del<void>(`/linkedin/people/${id}`))
}

export function useLinkedInSummary() {
  return useQuery({ queryKey: ['linkedin', 'summary'], queryFn: () => api.get<LinkedInSummary>('/linkedin/summary') })
}
