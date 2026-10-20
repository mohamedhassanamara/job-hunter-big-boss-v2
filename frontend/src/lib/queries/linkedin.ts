import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { InMailCredits, LinkedInCapture, LinkedInGroup, LinkedInImport, LinkedInLinks, LinkedInPanel, LinkedInPerson, LinkedInStatus, LinkedInSummary, PremiumReminder, ViewerLead, ViewerResult } from '@/lib/types'
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
    mutationFn: (body: { full_name: string; title?: string | null; linkedin_url?: string | null; group: LinkedInGroup | null; alumni: boolean; hiring_team?: boolean }) =>
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
  return usePersonMutation(appId, ({ id, kind }: { id: number; kind: 'note' | 'followup' | 'inmail' }) => api.post<LinkedInPerson>(`/linkedin/people/${id}/${kind}`))
}

export function useEditLinkedIn(appId: number) {
  return usePersonMutation(appId, ({ id, ...patch }: { id: number; note?: string; followup?: string; inmail_text?: string; inmail_subject?: string; group?: LinkedInGroup; alumni?: boolean }) =>
    api.patch<LinkedInPerson>(`/linkedin/people/${id}`, patch),
  )
}

/** Check every claim of the note or follow-up (Claude): Copy unlocks when it passes. */
export function useVerifyLinkedIn(appId: number) {
  return usePersonMutation(appId, ({ id, kind }: { id: number; kind: 'note' | 'followup' | 'inmail' }) => api.post<LinkedInPerson>(`/linkedin/people/${id}/verify?kind=${kind}`))
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

/** You sent the InMail on LinkedIn (uses a credit) / undo it (the credit comes back). */
export function useInMailSent(appId: number) {
  return usePersonMutation(appId, ({ id, sent }: { id: number; sent: boolean }) => api.post<LinkedInPerson>(`/linkedin/people/${id}/inmail/${sent ? 'sent' : 'unsent'}`))
}

export function useLinkedInCredits() {
  return useQuery({ queryKey: ['linkedin', 'credits'], queryFn: () => api.get<{ credits: InMailCredits; premium: PremiumReminder | null }>('/linkedin/credits') })
}

// ---- "viewed my profile" leads -----------------------------------------------------------

export function useLeads() {
  return useQuery({ queryKey: ['linkedin', 'leads'], queryFn: () => api.get<ViewerLead[]>('/linkedin/leads') })
}

function invalidateLinkedIn(qc: ReturnType<typeof useQueryClient>) {
  void qc.invalidateQueries({ queryKey: ['linkedin'] })
  invalidateWork(qc)
}

export function useAddViewer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { full_name: string; title?: string | null; company: string; linkedin_url?: string | null; viewed_on?: string | null }) => api.post<ViewerResult>('/linkedin/viewers', body),
    onSettled: () => invalidateLinkedIn(qc),
  })
}

export function useLinkLead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, application_id }: { id: number; application_id: number }) => api.post<{ row_id: number }>(`/linkedin/leads/${id}/link`, { application_id }),
    onSettled: () => invalidateLinkedIn(qc),
  })
}

export function useRemoveLead() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.del<void>(`/linkedin/leads/${id}`),
    onSettled: () => invalidateLinkedIn(qc),
  })
}
