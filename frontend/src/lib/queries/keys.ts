import type { QueryClient } from '@tanstack/react-query'

export const keys = {
  today: ['today'] as const,
  navCounts: ['nav-counts'] as const,
  jobs: (params: Record<string, unknown>) => ['jobs', params] as const,
  jobsAll: ['jobs'] as const,
  job: (id: number) => ['job', id] as const,
  applications: ['applications'] as const,
  cv: (appId: number) => ['cv', appId] as const,
  letter: (appId: number) => ['letter', appId] as const,
  cvTemplates: ['cv-templates'] as const,
  drafts: (status: string) => ['drafts', status] as const,
  draftsAll: ['drafts'] as const,
  queue: ['queue'] as const,
  experience: ['experience'] as const,
  companies: (q: string) => ['companies', q] as const,
  company: (id: number) => ['company', id] as const,
  lookups: ['lookups'] as const,
  settings: ['settings'] as const,
  searchProfile: ['search-profile'] as const,
  search: (q: string) => ['search', q] as const,
  discoveryStatus: ['discovery-status'] as const,
  sources: ['sources'] as const,
  countries: ['countries'] as const,
  scoringStatus: ['scoring-status'] as const,
  scoringHealth: ['scoring-health'] as const,
  ready: ['tracking', 'ready'] as const,
  tracked: (filters: Record<string, unknown>) => ['tracking', 'list', filters] as const,
  stats: (filters: Record<string, unknown>) => ['tracking', 'stats', filters] as const,
}

/** Workflow mutations touch many views; in a local single-user app we simply refresh them all. */
export function invalidateWork(qc: QueryClient) {
  for (const key of [
    'today',
    'nav-counts',
    'jobs',
    'job',
    'applications',
    'cv',
    'letter',
    'drafts',
    'queue',
    'lookups',
    'companies',
    'company',
    'scoring-status',
    'tracking',
    'match-report',
    'contact-imports',
    'company-merges',
    'send-log',
    'outreach-step',
  ]) {
    void qc.invalidateQueries({ queryKey: [key] })
  }
}
