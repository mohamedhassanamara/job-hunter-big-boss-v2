import { PageHeader } from '@/components/app/PageHeader'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { Navigate } from 'react-router'
import { useMergeSuggestions } from '@/lib/queries/library'
import { CompaniesTab } from './CompaniesTab'
import { ImportTab } from './ImportTab'
import { MatchTab } from './MatchTab'
import { MergesTab } from './MergesTab'

export default function ContactsPage() {
  const url = useSearchParamState()
  const tab = url.get('tab') ?? 'companies'
  const merges = useMergeSuggestions()
  const setTab = (t: string) => url.set({ tab: t === 'companies' ? null : t })

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Contacts"
        description="Who to write to for each job: your Apollo contacts by company, imports and the match report. Finding and verifying contacts happens in Outreach → Contacts to get."
        className="pb-0"
      >
        <Tabs value={tab} onValueChange={(t) => url.set({ tab: t === 'companies' ? null : t, company: null, filter: null })}>
          <TabsList data-tour="contacts-tabs">
            <TabsTrigger value="companies">Companies</TabsTrigger>
            <TabsTrigger value="import">Import CSV</TabsTrigger>
            <TabsTrigger value="merges" count={merges.data?.length}>
              Merges
            </TabsTrigger>
            <TabsTrigger value="match">Match report</TabsTrigger>
          </TabsList>
        </Tabs>
      </PageHeader>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {tab === 'import' ? (
          <ImportTab />
        ) : tab === 'match' ? (
          <MatchTab />
        ) : tab === 'merges' ? (
          <MergesTab />
        ) : tab === 'lookups' ? (
          <Navigate to="/outreach?tab=contacts" replace /> // the old lookup queue moved there
        ) : (
          <CompaniesTab onImport={() => setTab('import')} />
        )}
      </div>
    </div>
  )
}
