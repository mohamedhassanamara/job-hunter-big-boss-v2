import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api, qs } from '@/lib/api'
import type {
  CompanyDetail,
  CompanyFilter,
  CompanyList,
  ContactAlert,
  ContactCheck,
  Country,
  ExperienceInput,
  ExperienceItem,
  ExperienceKind,
  FilePreview,
  ImportRun,
  JobDetail,
  MatchReport,
  MergeSuggestion,
  NewContact,
  SearchProfile,
  SettingsView,
  VariantLang,
} from '@/lib/types'
import { invalidateWork, keys } from './keys'

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

export function useCompanies(q: string, filter: CompanyFilter, limit = 200) {
  return useQuery({
    queryKey: [...keys.companies(q), filter, limit],
    queryFn: () => api.get<CompanyList>(`/companies${qs({ q, filter, limit })}`),
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

export function useAddCompanyContact() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ companyId, ...body }: NewContact & { companyId: number }) =>
      api.post<CompanyDetail>(`/companies/${companyId}/contacts`, { ...body }),
    onSettled: () => invalidateWork(qc),
  })
}

export function useSetCompanySize() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ companyId, employees, employees_max }: { companyId: number; employees: number | null; employees_max: number | null }) =>
      api.patch<CompanyDetail>(`/companies/${companyId}/size`, { employees, employees_max }),
    onSettled: () => invalidateWork(qc),
  })
}

export function useMergeSuggestions() {
  return useQuery({ queryKey: ['company-merges'], queryFn: () => api.get<MergeSuggestion[]>('/company-merges') })
}

export function useMergeAction() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (body: { keep_id: number; merge_id: number } | { a_id: number; b_id: number }) =>
      'keep_id' in body ? api.post<MergeSuggestion[]>('/company-merges', body) : api.post<MergeSuggestion[]>('/company-merges/reject', body),
    onSuccess: (list) => qc.setQueryData(['company-merges'], list),
    onSettled: () => invalidateWork(qc),
  })
}

export function useImportPreview() {
  return useMutation({
    mutationFn: (files: File[]) => {
      const form = new FormData()
      files.forEach((f) => form.append('files', f))
      return api.post<FilePreview[]>('/contacts/import/preview', form)
    },
  })
}

export function useStartImport() {
  return useMutation({
    mutationFn: ({ file, mapping, force = false }: { file: File; mapping: Record<string, string | null>; force?: boolean }) => {
      const form = new FormData()
      form.append('file', file)
      form.append('mapping', JSON.stringify(mapping))
      form.append('force', String(force))
      return api.post<ImportRun>('/contacts/import', form)
    },
  })
}

/** Polls every second while the import runs; refreshes contacts views when it ends. */
export function useImportRun(id: number | null) {
  const qc = useQueryClient()
  return useQuery({
    queryKey: ['contact-import', id],
    queryFn: async () => {
      const run = await api.get<ImportRun>(`/contacts/imports/${id}`)
      if (run.status !== 'running') invalidateWork(qc)
      return run
    },
    enabled: id !== null,
    refetchInterval: (query) => (query.state.data?.status === 'running' || !query.state.data ? 1000 : false),
  })
}

export function useImports() {
  return useQuery({ queryKey: ['contact-imports'], queryFn: () => api.get<ImportRun[]>('/contacts/imports') })
}

export function useMatchReport() {
  return useQuery({ queryKey: ['match-report'], queryFn: () => api.get<MatchReport | null>('/contacts/match/report') })
}

export function useRunMatch() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.post<MatchReport>('/contacts/match'),
    onSuccess: (report) => qc.setQueryData(['match-report'], report),
    onSettled: () => invalidateWork(qc),
  })
}

export function useSetJobContact() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ appId, contactId, contact }: { appId: number; contactId?: number; contact?: NewContact }) =>
      api.post<JobDetail>(`/applications/${appId}/contact${contactId ? `?contact_id=${contactId}` : ''}`, contact ? { ...contact } : undefined),
    onSettled: () => invalidateWork(qc),
  })
}

/** "I verified them": dismiss a contact alert (dismissed: false undoes it). */
export function useDismissContactAlert() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ id, dismissed }: { id: number; dismissed: boolean }) =>
      api.post<ContactAlert>(`/contact-alerts/${id}/dismiss`, { dismissed }),
    onSettled: () => invalidateWork(qc),
  })
}

/** Search the news for the contact's name and rescan the company's pages (no model call). */
export function useCheckContact() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (contactId: number) => api.post<ContactCheck>(`/contacts/${contactId}/check`),
    onSettled: () => invalidateWork(qc),
  })
}

export function useClearJobContact() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (appId: number) => api.del<JobDetail>(`/applications/${appId}/contact`),
    onSettled: () => invalidateWork(qc),
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

export function useSuggestVariants() {
  return useMutation({
    mutationFn: (title: string) => api.post<Record<VariantLang, string[]>>('/roles/suggest', { title }),
  })
}

export function useCountries() {
  return useQuery({
    queryKey: keys.countries,
    queryFn: () => api.get<Country[]>('/countries'),
    staleTime: Infinity,
  })
}

export function useSaveSearchProfile() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (profile: SearchProfile) =>
      api.put<SearchProfile>('/search-profile', { ...profile }),
    onSuccess: (data) => {
      qc.setQueryData(keys.searchProfile, data)
      void qc.invalidateQueries({ queryKey: keys.sources })
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

/** Remove the test CV (experience items marked placeholder + the test candidate profile). */
export function useRemoveTestData() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: () => api.del<void>('/experience/placeholders'),
    onSuccess: () => {
      void qc.invalidateQueries({ queryKey: keys.experience })
      void qc.invalidateQueries({ queryKey: keys.settings })
    },
  })
}

export type AgencyOverride = 'employer' | 'agency' | null

/** "It's an employer" / "It's an agency" for a company (null: the rule decides again). */
export function useSetAgency() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ companyId, value }: { companyId: number; value: AgencyOverride }) =>
      api.put<{ company_id: number; agency_override: AgencyOverride; previous: AgencyOverride; detected: string[] }>(`/companies/${companyId}/agency`, { value }),
    onSettled: () => invalidateWork(qc),
  })
}
