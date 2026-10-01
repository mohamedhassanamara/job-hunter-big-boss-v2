import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { LinkedInCapture, LinkedInImport, LinkedInLinks } from '@/lib/types'
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
