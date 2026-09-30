import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { ApplicationAnswer, CoverLetter, LetterPatchInput, LetterStudio } from '@/lib/types'
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
    mutationFn: ({ appId, language, format, question, char_limit }: { appId: number; language?: string; format?: string; question?: string; char_limit?: number }) =>
      api.post<CoverLetter>(`/applications/${appId}/letter/generate`, {
        language: language ?? null,
        format: format ?? 'pdf',
        question: question ?? null,
        char_limit: char_limit ?? null,
      }),
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

// ---- Application questions -----------------------------------------------------------------

export function useAnswers(appId: number) {
  return useQuery({
    queryKey: keys.answers(appId),
    queryFn: () => api.get<ApplicationAnswer[]>(`/applications/${appId}/answers`),
    enabled: Number.isFinite(appId),
  })
}

/** One Claude call for the batch, checks per answer, one retry for those that fail. */
export function useAnswerQuestions() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ appId, questions }: { appId: number; questions: { question: string; char_limit: number | null }[] }) =>
      api.post<ApplicationAnswer[]>(`/applications/${appId}/answers`, { questions }),
    onSuccess: (_rows, { appId }) => void qc.invalidateQueries({ queryKey: keys.answers(appId) }),
  })
}

export function usePatchAnswer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, ...patch }: { id: number; answer?: string; char_limit?: number; clear_limit?: boolean }) =>
      api.patch<ApplicationAnswer>(`/answers/${id}`, patch),
    onSuccess: (a) => void qc.invalidateQueries({ queryKey: keys.answers(a.application_id) }),
  })
}

export function useDeleteAnswer() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id }: { id: number; appId: number }) => api.del<void>(`/answers/${id}`),
    onSettled: (_r, _e, { appId }) => void qc.invalidateQueries({ queryKey: keys.answers(appId) }),
  })
}
