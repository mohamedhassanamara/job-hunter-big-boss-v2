import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { api } from '@/lib/api'
import type { CompanyDomains, ContactBatchPreview, ContactFields, ContactSearch, FindContactResult, GetContactView, HunterCredits, HunterFound, HunterVerified, PasteParsed, ToGetQueue } from '@/lib/types'
import { invalidateWork, keys } from './keys'

/** Contacts to get: jobs past New that need a contact or a verification, best fit first. */
export function useToGet() {
  return useQuery({ queryKey: keys.toGet, queryFn: () => api.get<ToGetQueue>('/contacts/to-get') })
}

/** The Get contact step for one job (who to look for, links, verify first…). */
export function useGetContact(appId: number | null) {
  return useQuery({
    queryKey: keys.getContact(appId ?? 0),
    queryFn: () => api.get<GetContactView>(`/applications/${appId}/get-contact`),
    enabled: appId !== null,
  })
}

/** Actions return the job's new view: it's written straight into the cache, then work refreshes. */
function useViewMutation<V>(fn: (vars: V) => Promise<GetContactView | null>) {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: fn,
    onSuccess: (view) => {
      if (view) qc.setQueryData(keys.getContact(view.application_id), view)
    },
    onSettled: () => invalidateWork(qc),
  })
}

export function useVerifyContact() {
  return useViewMutation(({ appId, action }: { appId: number; action: 'still_there' | 'left' | 'wrong_person' }) =>
    api.post<GetContactView>(`/applications/${appId}/contact/verify`, { action }),
  )
}

export function useFoundContact() {
  return useViewMutation(({ appId, fields, via = 'found' }: { appId: number; fields: ContactFields; via?: 'found' | 'hunter' }) =>
    api.post<GetContactView>(`/applications/${appId}/contact/found`, {
      full_name: fields.full_name,
      title: fields.title || null,
      email: fields.email,
      linkedin_url: fields.linkedin_url || null,
      via,
    }),
  )
}

/** The contact waterfall: cache, then Hunter, Prospeo, Apollo, Apify, local pattern. One click. */
export function useFindContact() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ appId, requery = false, domain, emailDomain }: { appId: number; requery?: boolean; domain?: string; emailDomain?: string }) =>
      api.post<FindContactResult>(`/applications/${appId}/contact/find`, { requery, domain: domain || null, email_domain: emailDomain || null }),
    onSuccess: (res) => qc.setQueryData(keys.getContact(res.view.application_id), res.view),
    onSettled: () => {
      void qc.invalidateQueries({ queryKey: keys.providers })
      invalidateWork(qc)
    },
  })
}

/** Pick one of the waterfall's saved contacts for this job (it still asks "still there?"). */
export function useUseFoundContact() {
  return useViewMutation(({ appId, contactId }: { appId: number; contactId: number }) =>
    api.post<GetContactView>(`/applications/${appId}/contact/use`, { contact_id: contactId }),
  )
}

export function useEditContact() {
  return useViewMutation(({ appId, contactId, fields }: { appId: number; contactId: number; fields: Partial<ContactFields> }) =>
    api.patch<GetContactView | null>(`/contacts/${contactId}?application_id=${appId}`, fields),
  )
}

/** Nobody found / never look up (a job board) / back to normal. */
export function useContactSearch() {
  return useViewMutation(({ companyId, status, appId, notes = '' }: { companyId: number; status: ContactSearch; appId?: number; notes?: string }) =>
    api.post<GetContactView | null>(`/companies/${companyId}/contact-search`, { status, notes, application_id: appId ?? null }),
  )
}

export function useNotAggregator() {
  return useViewMutation(({ companyId, appId }: { companyId: number; appId: number }) =>
    api.post<GetContactView | null>(`/companies/${companyId}/not-aggregator?application_id=${appId}`),
  )
}

export function useParsePaste() {
  return useMutation({ mutationFn: (text: string) => api.post<PasteParsed>('/contacts/parse', { text }) })
}

/** Hunter's remaining credits (reading them is free). */
export function useHunterCredits(enabled = true) {
  return useQuery({ queryKey: keys.hunterCredits, queryFn: () => api.get<HunterCredits>('/hunter/credits'), enabled, staleTime: 60_000 })
}

export function useHunterFind() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ appId, fullName }: { appId: number; fullName: string }) => api.post<HunterFound>('/hunter/find', { application_id: appId, full_name: fullName }),
    onSuccess: (r) => qc.setQueryData(keys.hunterCredits, r.credits),
  })
}

export function useHunterVerify() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: (email: string) => api.post<HunterVerified>('/hunter/verify', { email }),
    onSuccess: (r) => qc.setQueryData(keys.hunterCredits, r.credits),
  })
}

/** Every domain known for a company and whether it receives email (a free DNS lookup). */
export function useCompanyDomains(companyId: number, enabled: boolean) {
  return useQuery({ queryKey: keys.companyDomains(companyId), queryFn: () => api.get<CompanyDomains>(`/companies/${companyId}/domains`), enabled })
}

/** Ask the providers about this domain from now on (null: back to the website's). */
export function useSetEmailDomain() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: ({ companyId, emailDomain }: { companyId: number; emailDomain: string | null }) =>
      api.put<CompanyDomains>(`/companies/${companyId}/domains`, { email_domain: emailDomain }),
    onSuccess: (data) => qc.setQueryData(keys.companyDomains(data.company_id), data),
  })
}

/** Find contacts for this batch, step 1: the shortlisted jobs without a contact and the most the
 * waterfall could spend on them (read-only; nothing is queried). */
export function useBatchPreview(enabled = true) {
  return useQuery({
    queryKey: ['contact-batch-preview'],
    queryFn: () => api.get<ContactBatchPreview>('/contacts/batch-preview'),
    enabled,
    staleTime: 0,
  })
}
