import { PageHeader } from '@/components/app/PageHeader'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { useLookups } from '@/lib/queries/library'
import { CompaniesTab } from './CompaniesTab'
import { ImportTab } from './ImportTab'
import { LookupTab } from './LookupTab'
import { MatchTab } from './MatchTab'

export default function ContactsPage() {
  const url = useSearchParamState()
  const tab = url.get('tab') ?? 'companies'
  const lookups = useLookups()
  const setTab = (t: string) => url.set({ tab: t === 'companies' ? null : t })

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Contacts"
        description="Who to write to for each job: your Apollo contacts by company, the manual lookup queue, and the match report."
        className="pb-0"
      >
        <Tabs value={tab} onValueChange={(t) => url.set({ tab: t === 'companies' ? null : t, company: null, filter: null })}>
          <TabsList data-tour="contacts-tabs">
            <TabsTrigger value="companies">Companies</TabsTrigger>
            <TabsTrigger value="lookups" count={lookups.data?.total}>
              Lookup queue
            </TabsTrigger>
            <TabsTrigger value="import">Import CSV</TabsTrigger>
            <TabsTrigger value="match">Match report</TabsTrigger>
          </TabsList>
        </Tabs>
      </PageHeader>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {tab === 'import' ? (
          <ImportTab />
        ) : tab === 'match' ? (
          <MatchTab />
        ) : tab === 'lookups' ? (
          <LookupTab />
        ) : (
          <CompaniesTab onImport={() => setTab('import')} />
        )}
      </div>
    </div>
  )
}
