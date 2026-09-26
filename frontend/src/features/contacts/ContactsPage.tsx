import { PageHeader } from '@/components/app/PageHeader'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { useLookups } from '@/lib/queries/library'
import { CompaniesTab } from './CompaniesTab'
import { ImportTab } from './ImportTab'
import { LookupTab } from './LookupTab'

export default function ContactsPage() {
  const url = useSearchParamState()
  const tab = url.get('tab') ?? 'companies'
  const lookups = useLookups()
  const setTab = (t: string) => url.set({ tab: t === 'companies' ? null : t })

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Contacts"
        description="Your Apollo contacts, grouped by company. Used to route jobs to a cold email."
        className="pb-0"
      >
        <Tabs value={tab} onValueChange={setTab}>
          <TabsList data-tour="contacts-tabs">
            <TabsTrigger value="companies">Companies</TabsTrigger>
            <TabsTrigger value="lookups" count={lookups.data?.items.length}>
              Lookup queue
            </TabsTrigger>
            <TabsTrigger value="import">Import CSV</TabsTrigger>
          </TabsList>
        </Tabs>
      </PageHeader>
      <div className="min-h-0 flex-1 overflow-y-auto">
        {tab === 'import' ? (
          <ImportTab />
        ) : tab === 'lookups' ? (
          <LookupTab />
        ) : (
          <CompaniesTab onImport={() => setTab('import')} />
        )}
      </div>
    </div>
  )
}
