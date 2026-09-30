import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { CoverLetter, LetterPatchInput, LetterStudio } from '@/lib/types'
import { invalidateWork, keys } from './keys'

export function useLetterStudio(appId: number) {
  return useQuery({
    queryKey: keys.letter(appId),
    queryFn: () => api.get<LetterStudio>(`/applications/${appId}/letter`),
    enabled: Number.isFinite(appId),
  })
}

/** One Claude call (~30s), checks and one retry, then the PDF. */
export function useGenerateLetter() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ appId, language }: { appId: number; language?: string }) =>
      api.post<CoverLetter>(`/applications/${appId}/letter/generate`, { language: language ?? null }),
    onSettled: () => invalidateWork(qc),
  })
}

/** Your edits: re-checked and re-rendered, no Claude call. A locked letter gets a new draft. */
export function usePatchLetter() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...patch }: LetterPatchInput & { id: number }) =>
      api.patch<CoverLetter>(`/letters/${id}`, patch as Record<string, unknown>),
    onSuccess: (letter) => void qc.invalidateQueries({ queryKey: keys.letter(letter.application_id) }),
  })
}

export function useApproveLetter() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.post<CoverLetter>(`/letters/${id}/approve`),
    onSettled: () => invalidateWork(qc),
  })
}

export function useSetLetterLanguage() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ appId, language }: { appId: number; language: string }) =>
      api.put<LetterStudio>(`/applications/${appId}/letter/language`, { language }),
    onSuccess: (studio) => qc.setQueryData(keys.letter(studio.application_id), studio),
  })
}
