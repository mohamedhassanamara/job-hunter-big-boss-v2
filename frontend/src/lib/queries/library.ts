import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, qs } from '@/lib/api'
import type {
  CompanyDetail,
  CompanyListItem,
  ExperienceInput,
  ExperienceItem,
  ExperienceKind,
  ImportPreview,
  ImportResult,
  LookupQueue,
  SearchProfile,
  SettingsView,
} from '@/lib/types'
import { keys } from './keys'

// ---- Experience --------------------------------------------------------------------------

export function useExperience() {
  return useQuery({
    queryKey: keys.experience,
    queryFn: () => api.get<ExperienceItem[]>('/experience'),
  })
}

export function useSaveExperience() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, data }: { id?: number; data: Partial<ExperienceInput> }) =>
      id
        ? api.patch<ExperienceItem>(`/experience/${id}`, data)
        : api.post<ExperienceItem>('/experience', data),
    onSettled: () => qc.invalidateQueries({ queryKey: keys.experience }),
  })
}

export function useDeleteExperience() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (id: number) => api.del<void>(`/experience/${id}`),
    onMutate: async (id) => {
      await qc.cancelQueries({ queryKey: keys.experience })
      qc.setQueryData<ExperienceItem[]>(keys.experience, (old) => old?.filter((i) => i.id !== id))
    },
    onSettled: () => qc.invalidateQueries({ queryKey: keys.experience }),
  })
}

export function useReorderExperience() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ kind, ids }: { kind: ExperienceKind; ids: number[] }) =>
      api.post<ExperienceItem[]>('/experience/reorder', { kind, ids }),
    onMutate: async ({ ids }) => {
      await qc.cancelQueries({ queryKey: keys.experience })
      qc.setQueryData<ExperienceItem[]>(keys.experience, (old) =>
        old?.map((i) => (ids.includes(i.id) ? { ...i, position: ids.indexOf(i.id) } : i)),
      )
    },
    onSuccess: (items) => qc.setQueryData(keys.experience, items),
  })
}

// ---- Contacts ----------------------------------------------------------------------------

export function useCompanies(q: string) {
  return useQuery({
    queryKey: keys.companies(q),
    queryFn: () => api.get<CompanyListItem[]>(`/companies${qs({ q })}`),
    placeholderData: (prev) => prev,
  })
}

export function useCompany(id: number | null) {
  return useQuery({
    queryKey: keys.company(id ?? -1),
    queryFn: () => api.get<CompanyDetail>(`/companies/${id}`),
    enabled: id !== null,
  })
}

export function useLookups() {
  return useQuery({ queryKey: keys.lookups, queryFn: () => api.get<LookupQueue>('/contacts/lookups') })
}

export function useImportPreview() {
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api.post<ImportPreview>('/contacts/import/preview', form)
    },
  })
}

export function useImportContacts() {
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData()
      form.append('file', file)
      return api.post<ImportResult>('/contacts/import', form)
    },
  })
}

// ---- Settings ----------------------------------------------------------------------------

export function useSettings() {
  return useQuery({ queryKey: keys.settings, queryFn: () => api.get<SettingsView>('/settings') })
}

export function useSaveSetting() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ key, value }: { key: string; value: Record<string, unknown> }) =>
      api.put<SettingsView>(`/settings/${key}`, { value }),
    onSuccess: (data) => qc.setQueryData(keys.settings, data),
  })
}

export function useSearchProfile() {
  return useQuery({
    queryKey: keys.searchProfile,
    queryFn: () => api.get<SearchProfile>('/search-profile'),
  })
}

export function useSaveSearchProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (profile: SearchProfile) =>
      api.put<SearchProfile>('/search-profile', { ...profile }),
    onSuccess: (data) => {
      qc.setQueryData(keys.searchProfile, data)
      void qc.invalidateQueries({ queryKey: ['today'] })
    },
  })
}

/** Erase every real job, contact, CV and draft (keeps profile + settings). */
export function useEraseWorkspace() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (confirm: string) => api.post<void>('/workspace/erase', { confirm }),
    onSuccess: () => qc.invalidateQueries(),
  })
}
