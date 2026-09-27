import { PageHeader } from '@/components/app/PageHeader'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { useSearchParamState } from '@/hooks/useSearchParamState'
import { useReadyToApply } from '@/lib/queries/tracking'
import { AppliedTab } from './AppliedTab'
import { ReadyTab } from './ReadyTab'
import { StatsTab } from './StatsTab'

type Tab = 'ready' | 'applied' | 'stats'

export default function ApplicationsPage() {
  const url = useSearchParamState()
  const raw = url.get('tab')
  const tab: Tab = raw === 'applied' || raw === 'stats' ? raw : 'ready'
  const ready = useReadyToApply()

  return (
    <div className="flex h-full flex-col">
      <PageHeader
        title="Applications"
        description="Apply with the approved CV, log replies and interviews, and see what's working."
        className="pb-0"
      >
        <Tabs data-tour="applications-tabs" value={tab} onValueChange={(v) => url.set({ tab: v === 'ready' ? null : v, app: null })}>
          <TabsList>
            <TabsTrigger value="ready" count={ready.data?.length}>
              Ready to apply
            </TabsTrigger>
            <TabsTrigger value="applied">Applied</TabsTrigger>
            <TabsTrigger value="stats">Stats</TabsTrigger>
          </TabsList>
        </Tabs>
      </PageHeader>
      <div className="flex min-h-0 flex-1 flex-col">
        {tab === 'ready' ? <ReadyTab /> : tab === 'applied' ? <AppliedTab /> : <StatsTab />}
      </div>
    </div>
  )
}
